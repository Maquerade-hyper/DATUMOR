import json
"""DATUMOR worker: source resolution, extraction, and durable report generation."""
# Register all FK-referenced models in this worker process.
import apps.api.app.auth.user_model as _datumor_user_model
import apps.api.app.projects.project_model as _datumor_project_model
import apps.api.app.source_model as _datumor_source_model
import apps.api.app.jobs.job_model as _datumor_job_model

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from celery import shared_task
from apps.api.app.database import SessionLocal, engine
from apps.worker.job_runtime import add_event, get_job
from apps.worker.source_resolver import resolve_source, materialize_object
from apps.worker.execution_lease import claim_execution, renew_execution, release_execution, execution_is_owned, acknowledge_cancellation, finalize_execution, ExecutionHeartbeat

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def utcnow():
    return datetime.now(timezone.utc)

def _cancelled(db, job, execution_id):
    return acknowledge_cancellation(db, job.job_id, execution_id)

def _attach_source_identity(result: dict, source: dict, source_id: str, project_id: str):
    result.setdefault("source_id", str(source_id))
    result.setdefault("project_id", str(project_id))
    result.setdefault("source_filename", source["name"])
    metadata = result.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    source_meta = metadata.get("source")
    source_meta = dict(source_meta) if isinstance(source_meta, dict) else {}
    for key in ("media_type", "size_bytes", "checksum_sha256"):
        if source.get(key) is not None:
            source_meta.setdefault(key, source[key])
    source_meta.setdefault("filename", source["name"])
    metadata["source"] = source_meta
    identity = metadata.get("source_identity")
    identity = dict(identity) if isinstance(identity, dict) else {}
    identity.update({"source_id": str(source_id), "project_id": str(project_id)})
    metadata["source_identity"] = identity
    result["metadata"] = metadata
    return result

@shared_task(bind=True, name="datumor.process_job", max_retries=2)
def process_job(self, job_id: str):
    db = SessionLocal()
    heartbeat = None
    try:
        execution_id = claim_execution(db, job_id, self.request.id)
        if not execution_id:
            job = get_job(db, job_id)
            return {
                "status": job.status if job else "missing",
                "detail": "Execution not claimed; another worker may own this job.",
            }

        job = get_job(db, job_id)
        if not job:
            return {"status": "missing"}

        heartbeat = ExecutionHeartbeat(job_id, execution_id)

        from apps.api.app.extraction.document_extractor import extract_document
        from apps.api.app.extraction.report_generator import generate_extraction_report, write_extraction_report

        extracted = []
        failed_sources = []
        successful_source_ids = set()
        failed_source_ids = set()
        failed_file_count = 0
        skipped_file_count = 0

        supported_formats = {
            "pdf", "txt", "text", "md", "markdown",
            "json", "jsonl", "csv",
            "py", "pyw", "js", "mjs", "cjs", "jsx",
            "ts", "tsx", "java", "c", "h", "cc", "cpp",
            "cxx", "hpp", "cs", "go", "rs", "php", "rb",
        }

        unique_source_ids = list(dict.fromkeys(
            str(source_id) for source_id in job.source_ids
        ))

        with tempfile.TemporaryDirectory(prefix="datumor-job-") as temp_dir:
            for index, source_id in enumerate(unique_source_ids):
                if heartbeat.is_lost() or not renew_execution(db, job_id, execution_id):
                    logger.error("Execution lease lost for DATUMOR job %s", job_id)
                    return {"status": "lease_lost"}

                if _cancelled(db, job, execution_id):
                    release_execution(db, job_id, execution_id)
                    return {"status": "cancelled"}

                source_id = str(source_id)
                source = None
                source_successes = 0

                job.stage = "source_resolution"
                job.progress = 10 + int(
                    (index / max(1, len(unique_source_ids))) * 55
                )
                db.commit()

                try:
                    source = resolve_source(
                        engine, source_id, str(job.project_id)
                    )

                    if source.get("path"):
                        source_path = Path(source["path"])
                    else:
                        safe_name = Path(source["name"]).name or f"source-{index + 1}"
                        source_path = materialize_object(
                            source, Path(temp_dir) / f"{index}-{safe_name}"
                        )

                    if source_path.is_dir():
                        candidates = sorted(
                            path for path in source_path.rglob("*")
                            if path.is_file()
                            and not any(
                                part.lower() in {
                                    ".git", "node_modules", "__pycache__",
                                    ".venv", "venv"
                                }
                                for part in path.parts
                            )
                        )
                    else:
                        candidates = [source_path]

                    supported_files = [
                        path for path in candidates
                        if path.suffix.lower().lstrip(".") in supported_formats
                    ]
                    skipped_file_count += len(candidates) - len(supported_files)

                    if not supported_files:
                        raise ValueError(
                            "Source contains no supported extractable files."
                        )

                    for candidate in supported_files:
                        if heartbeat.is_lost() or not renew_execution(db, job_id, execution_id):
                            logger.error("Execution lease lost for DATUMOR job %s", job_id)
                            return {"status": "lease_lost"}

                        if _cancelled(db, job, execution_id):
                            release_execution(db, job_id, execution_id)
                            return {"status": "cancelled"}

                        relative_name = (
                            str(candidate.relative_to(source_path))
                            if source_path.is_dir()
                            else candidate.name
                        )

                        try:
                            result = extract_document(candidate)
                            if not isinstance(result, dict):
                                raise TypeError(
                                    "Document extractor returned a non-dictionary result."
                                )

                            result = _attach_source_identity(
                                result, source, source_id, str(job.project_id)
                            )

                            display_name = (
                                f"{source['name']}/{relative_name}"
                                if source_path.is_dir()
                                else source["name"]
                            )

                            extracted.append({
                                "source_id": source_id,
                                "source_name": display_name,
                                "extraction": result,
                            })
                            source_successes += 1

                        except Exception as file_exc:
                            failed_file_count += 1
                            failure = {
                                "source_id": source_id,
                                "source_name": source["name"],
                                "file": relative_name,
                                "error": (
                                    f"{type(file_exc).__name__}: {file_exc}"
                                )[:1000],
                            }
                            failed_sources.append(failure)
                            add_event(
                                db, job_id, "extraction",
                                f"File extraction failed: {relative_name}",
                                level="error", details=failure
                            )
                            db.commit()

                    if source_successes:
                        successful_source_ids.add(source_id)
                    else:
                        failed_source_ids.add(source_id)

                except Exception as source_exc:
                    failed_source_ids.add(source_id)
                    failure = {
                        "source_id": source_id,
                        "source_name": (
                            source.get("name", source_id)
                            if source else source_id
                        ),
                        "error": (
                            f"{type(source_exc).__name__}: {source_exc}"
                        )[:1000],
                    }
                    failed_sources.append(failure)
                    add_event(
                        db, job_id, "source_resolution",
                        f"Source failed: {source_id}",
                        level="error", details=failure
                    )
                    db.commit()

        if not extracted:
            message = "All sources failed; no extraction results were produced."
            failure_result = {
                "source_count": len(unique_source_ids),
                "successful_source_count": 0,
                "failed_source_count": len(failed_source_ids),
                "failed_file_count": failed_file_count,
                "skipped_file_count": skipped_file_count,
                "failed_sources": failed_sources,
            }
            finalized = finalize_execution(
                db, job_id, execution_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "progress": 100,
                    "error_message": message,
                    "result": failure_result,
                    "finished_at": utcnow(),
                },
            )
            if not finalized:
                return {"status": "lease_lost"}
            add_event(
                db, job_id, "failed", message,
                level="error",
                details={"failed_source_count": len(failed_source_ids)}
            )
            db.commit()
            return {"status": "failed", "job_id": job_id}

        if heartbeat.is_lost() or not renew_execution(db, job_id, execution_id):
            logger.error("Execution lease lost before report generation for job %s", job_id)
            return {"status": "lease_lost"}

        if _cancelled(db, job, execution_id):
            release_execution(db, job_id, execution_id)
            return {"status": "cancelled"}

        job.stage = "report_generation"
        job.progress = 85
        add_event(db, job_id, "report_generation", "Generating extraction report.")
        db.commit()

        report = generate_extraction_report(
            [item["extraction"] for item in extracted],
            project_id=str(job.project_id),
        )
        report_dir = PROJECT_ROOT / "data" / "jobs" / str(job.job_id) / "reports"
        report_files = write_extraction_report(report, report_dir, basename="extraction-report")

        # Persist the full extraction output separately from the summary report.
        artifact_dir = PROJECT_ROOT / "data" / "jobs" / str(job.job_id) / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        extraction_payload = {
            "schema_version": "1.0",
            "job_id": str(job.job_id),
            "project_id": str(job.project_id),
            "sources": [
                {
                    "source_id": item["source_id"],
                    "source_name": item["source_name"],
                    "extraction": item["extraction"],
                }
                for item in extracted
            ],
        }

        json_artifact = artifact_dir / "extracted-data.json"
        jsonl_artifact = artifact_dir / "extracted-data.jsonl"
        text_artifact = artifact_dir / "extracted-text.txt"

        json_tmp = json_artifact.with_suffix(".json.tmp")
        json_tmp.write_text(
            json.dumps(extraction_payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        json_tmp.replace(json_artifact)

        jsonl_lines = []
        text_sections = []

        for item in extracted:
            extraction = item["extraction"]
            records = extraction.get("records") or []

            for record_index, record in enumerate(records, 1):
                jsonl_lines.append(json.dumps({
                    "source_id": item["source_id"],
                    "source_name": item["source_name"],
                    "format": extraction.get("format"),
                    "record_index": record_index,
                    "record": record,
                }, ensure_ascii=False, default=str))

            content = extraction.get("content")
            if content is not None:
                if isinstance(content, str):
                    content_text = content
                else:
                    content_text = json.dumps(content, ensure_ascii=False, indent=2, default=str)

                text_sections.append(
                    f"Source: {item['source_name']}\n"
                    f"Source ID: {item['source_id']}\n"
                    f"Format: {extraction.get('format', 'unknown')}\n\n"
                    f"{content_text}"
                )

        jsonl_tmp = jsonl_artifact.with_suffix(".jsonl.tmp")
        jsonl_tmp.write_text(
            "\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""),
            encoding="utf-8",
        )
        jsonl_tmp.replace(jsonl_artifact)

        text_tmp = text_artifact.with_suffix(".txt.tmp")
        text_tmp.write_text(
            "\n\n".join(text_sections) + ("\n" if text_sections else ""),
            encoding="utf-8",
        )
        text_tmp.replace(text_artifact)

        extraction_artifacts = {
            "extracted_data_json": str(json_artifact.resolve()),
            "extracted_data_jsonl": str(jsonl_artifact.resolve()),
            "extracted_text": str(text_artifact.resolve()),
        }

        report_sources = report.get("sources") or []
        extracted_sources = []
        for index, item in enumerate(extracted):
            report_source = report_sources[index] if index < len(report_sources) else {}
            extracted_sources.append({
                "source_id": item["source_id"],
                "source_name": item["source_name"],
                "format": item["extraction"].get("format"),
                "record_count": report_source.get("record_count", 0),
                "status": report_source.get("status", "unknown"),
            })

        result_payload = {
            "pipeline": job.pipeline,
            "project_id": str(job.project_id),
            "source_count": len(unique_source_ids),
            "successful_source_count": len(successful_source_ids),
            "failed_source_count": len(failed_source_ids),
            "failed_file_count": failed_file_count,
            "skipped_file_count": skipped_file_count,
            "partial_success": bool(failed_sources),
            "failed_sources": failed_sources,
            "extracted_sources": extracted_sources,
            "extraction_report": report,
            "artifacts": {
                "extraction_report_json": str(Path(report_files["json_path"]).resolve()),
                "extraction_report_markdown": str(Path(report_files["markdown_path"]).resolve()),
                **extraction_artifacts,
            },
            "completed_stages": ["source_resolution", "extraction", "report_generation"],
            "not_run_stages": [] if job.pipeline == "extract_only" else [
                "understanding", "quality", "transformation", "optimization", "validation", "export"
            ],
        }
        finalized = finalize_execution(
            db, job_id, execution_id,
            {
                "status": "completed",
                "stage": "completed",
                "progress": 100,
                "result": result_payload,
                "error_message": None,
                "finished_at": utcnow(),
            },
        )
        if not finalized:
            return {"status": "lease_lost"}
        add_event(
            db, job_id, "completed",
            (
                "Extraction completed with partial failures."
                if failed_sources
                else "Extraction and report generation completed. Later stages are explicitly reported."
            ),
            details={
                "source_count": len(unique_source_ids),
                "successful_source_count": len(successful_source_ids),
                "failed_source_count": len(failed_source_ids),
                "failed_file_count": failed_file_count,
                "skipped_file_count": skipped_file_count,
                "record_count": report.get("summary", {}).get("total_records", 0),
            },
        )
        db.commit()
        return {"status": "completed", "job_id": job_id, "artifacts": result_payload["artifacts"]}

    except Exception as exc:
        db.rollback()
        try:
            job = get_job(db, job_id)
            if job and "execution_id" in locals() and execution_id:
                finalized = finalize_execution(
                    db, job_id, execution_id,
                    {
                        "status": "failed",
                        "stage": "failed",
                        "error_message": f"{type(exc).__name__}: {exc}"[:4000],
                        "finished_at": utcnow(),
                    },
                )
                if finalized:
                    add_event(
                        db, job_id, "failed", "Processing failed.",
                        level="error",
                        details={"error_type": type(exc).__name__},
                    )
                    db.commit()
                else:
                    logger.warning(
                        "Skipping failure update for job %s: execution lease no longer owned.",
                        job_id,
                    )
        except Exception:
            db.rollback()
            logger.exception("Could not persist failure state for DATUMOR job %s", job_id)
        logger.exception("DATUMOR processing job %s failed", job_id)
        raise
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        db.close()
