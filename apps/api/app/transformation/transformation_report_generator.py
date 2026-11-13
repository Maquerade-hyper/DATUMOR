"""Consolidated transformation reporting for DATUMOR."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from apps.api.app.transformation.profile_registry import validate_profile


REPORT_TYPE = "datumor.transformation_report"
REPORT_VERSION = "1.0.0"


def _json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _skip_reason(item: object) -> str:
    if isinstance(item, dict):
        return str(
            item.get("reason")
            or item.get("skip_reason")
            or item.get("code")
            or "unspecified"
        )
    return "unspecified"


def _source_ids(examples: list, skipped: list) -> list[str]:
    values = set()

    for item in examples + skipped:
        if not isinstance(item, dict):
            continue
        provenance = item.get("provenance")
        if isinstance(provenance, dict) and provenance.get("source_id"):
            values.add(str(provenance["source_id"]))

    return sorted(values)


def _provenance_summary(examples: list) -> dict:
    total = len(examples)
    with_provenance = 0
    with_source_id = 0
    with_evidence = 0
    missing_source_ids = []
    missing_evidence_ids = []

    for index, example in enumerate(examples):
        provenance = example.get("provenance")
        if isinstance(provenance, dict):
            with_provenance += 1
            if provenance.get("source_id"):
                with_source_id += 1
            else:
                missing_source_ids.append(example.get("example_id", str(index)))

            if provenance.get("evidence_text"):
                with_evidence += 1
            else:
                missing_evidence_ids.append(example.get("example_id", str(index)))
        else:
            missing_source_ids.append(example.get("example_id", str(index)))
            missing_evidence_ids.append(example.get("example_id", str(index)))

    return {
        "examples_total": total,
        "examples_with_provenance": with_provenance,
        "examples_with_source_id": with_source_id,
        "examples_with_evidence": with_evidence,
        "provenance_coverage": (
            round(with_provenance / total, 4) if total else None
        ),
        "source_identity_coverage": (
            round(with_source_id / total, 4) if total else None
        ),
        "evidence_coverage": (
            round(with_evidence / total, 4) if total else None
        ),
        "missing_source_id_example_ids": missing_source_ids,
        "missing_evidence_example_ids": missing_evidence_ids,
    }


def _export_summary(serialization_reports: list) -> dict:
    exports = []

    for report in serialization_reports:
        if not isinstance(report, dict):
            continue

        output = report.get("output") or {}
        integrity = report.get("integrity") or {}

        exports.append({
            "status": report.get("status", "unknown"),
            "format": output.get("format"),
            "path": output.get("path"),
            "size_bytes": output.get("size_bytes"),
            "sha256": output.get("sha256"),
            "examples_serialized": (
                report.get("summary") or {}
            ).get("examples_serialized"),
            "integrity": integrity,
        })

    successful = sum(item["status"] == "completed" for item in exports)
    failed = sum(item["status"] == "failed" for item in exports)

    return {
        "exports_total": len(exports),
        "exports_completed": successful,
        "exports_failed": failed,
        "exports": exports,
    }


def generate_transformation_report(
    dataset: dict,
    profile: dict,
    serialization_reports: list[dict] | None = None,
    quality_report: dict | None = None,
) -> dict:
    """Create a deterministic summary of transformation outcomes."""

    if not isinstance(dataset, dict):
        raise TypeError("dataset must be a dictionary")

    if dataset.get("report_type") != "datumor.generated_dataset":
        raise ValueError("Unsupported generated dataset report_type")

    validation = validate_profile(profile)
    if not validation["valid"]:
        raise ValueError(
            "Invalid transformation profile: "
            + "; ".join(validation["errors"])
        )

    dataset_profile = dataset.get("profile") or {}
    if dataset_profile.get("profile_id") != profile["profile_id"]:
        raise ValueError("Dataset profile does not match selected profile")

    if dataset_profile.get("profile_version") != profile["version"]:
        raise ValueError("Dataset profile version does not match selected profile")

    examples = dataset.get("examples")
    skipped = dataset.get("skipped", [])

    if not isinstance(examples, list) or not isinstance(skipped, list):
        raise ValueError("Dataset examples and skipped must be lists")

    if not all(isinstance(item, dict) for item in examples):
        raise ValueError("Every generated example must be an object")

    skip_counts = Counter(_skip_reason(item) for item in skipped)
    serialization_reports = serialization_reports or []

    if not isinstance(serialization_reports, list):
        raise TypeError("serialization_reports must be a list")

    export_summary = _export_summary(serialization_reports)

    dataset_status = dataset.get("status", "unknown")
    if dataset_status == "failed":
        status = "failed"
    elif dataset_status != "completed":
        status = "incomplete"
    elif skipped or export_summary["exports_failed"]:
        status = "incomplete"
    else:
        status = "completed"

    report = {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["version"],
            "task_type": profile.get("task_type"),
            "output_format": profile.get("output_format"),
            "normalization": profile.get("normalization"),
            "chunking": profile.get("chunking"),
            "target_model": profile.get("target_model"),
            "deduplicate": profile.get("deduplicate"),
            "preserve_provenance": profile.get("preserve_provenance"),
        },
        "summary": {
            "input_sources": len(_source_ids(examples, skipped)),
            "examples_generated": len(examples),
            "examples_skipped": len(skipped),
            "examples_total_processed": len(examples) + len(skipped),
            "empty_output": len(examples) == 0,
            "generation_status": dataset_status,
        },
        "skip_reasons": dict(sorted(skip_counts.items())),
        "provenance": _provenance_summary(examples),
        "source_ids": _source_ids(examples, skipped),
        "quality": (
            {"assessment_status": "provided", "report": quality_report}
            if quality_report is not None
            else {"assessment_status": "not_assessed", "report": None}
        ),
        "exports": export_summary,
        "warnings": list(dataset.get("warnings", [])),
        "integrity": {
            "source_dataset_modified": False,
            "dataset_snapshot_sha256": _json_hash(dataset),
        },
    }

    report["integrity"]["report_payload_sha256"] = _json_hash(report)
    return report


def render_transformation_report_markdown(report: dict) -> str:
    if report.get("report_type") != REPORT_TYPE:
        raise ValueError("Unsupported transformation report")

    summary = report["summary"]
    profile = report["profile"]
    provenance = report["provenance"]
    exports = report["exports"]

    lines = [
        "# DATUMOR Transformation Report",
        "",
        f"- **Status:** {report['status']}",
        f"- **Generated:** {report['generated_at']}",
        f"- **Profile:** {profile['profile_id']} ({profile['profile_version']})",
        "",
        "## Transformation Summary",
        "",
        f"- Input sources: {summary['input_sources']}",
        f"- Generated examples: {summary['examples_generated']}",
        f"- Skipped examples: {summary['examples_skipped']}",
        f"- Total processed: {summary['examples_total_processed']}",
        f"- Empty output: {summary['empty_output']}",
        "",
        "## Skipped Records",
        "",
    ]

    if report["skip_reasons"]:
        for reason, count in report["skip_reasons"].items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- No skipped records.")

    lines.extend([
        "",
        "## Provenance",
        "",
        f"- Examples with provenance: {provenance['examples_with_provenance']}/{provenance['examples_total']}",
        f"- Source identity coverage: {provenance['source_identity_coverage']}",
        f"- Evidence coverage: {provenance['evidence_coverage']}",
        f"- Source IDs: {', '.join(report['source_ids']) or 'None'}",
        "",
        "## Quality Assessment",
        "",
        f"- Assessment: {report['quality']['assessment_status']}",
    ])

    if report["quality"]["assessment_status"] == "not_assessed":
        lines.append("- Quality assessment: not assessed.")
        lines.append("- No quality report was supplied; no quality score is claimed.")

    lines.extend([
        "",
        "## Exports",
        "",
        f"- Total: {exports['exports_total']}",
        f"- Completed: {exports['exports_completed']}",
        f"- Failed: {exports['exports_failed']}",
    ])

    for item in exports["exports"]:
        lines.append(
            f"- {item['format'] or 'Unknown'}: {item['status']} | "
            f"{item['size_bytes']} bytes | SHA-256: {item['sha256'] or 'Unavailable'}"
        )

    lines.extend([
        "",
        "## Integrity",
        "",
        f"- Source dataset modified: {report['integrity']['source_dataset_modified']}",
        f"- Dataset SHA-256: {report['integrity']['dataset_snapshot_sha256']}",
        f"- Report payload SHA-256: {report['integrity']['report_payload_sha256']}",
        "",
        "## Warnings",
        "",
    ])

    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- None reported.")

    return "\n".join(lines) + "\n"


def export_transformation_report(
    report: dict,
    output_directory: str | Path,
    filename: str = "transformation_report",
) -> dict:
    """Export the same report as JSON and Markdown."""

    if report.get("report_type") != REPORT_TYPE:
        raise ValueError("Unsupported transformation report")

    if not filename or Path(filename).name != filename:
        raise ValueError("filename must be a simple file name")

    directory = Path(output_directory)
    json_path = directory / f"{filename}.json"
    markdown_path = directory / f"{filename}.md"

    json_content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown_content = render_transformation_report_markdown(report)

    _write_atomic(json_path, json_content)
    _write_atomic(markdown_path, markdown_content)

    return {
        "status": "completed",
        "json_path": str(json_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
        "json_sha256": sha256(json_content.encode("utf-8")).hexdigest(),
        "markdown_sha256": sha256(
            markdown_content.encode("utf-8")
        ).hexdigest(),
        "report_payload_sha256": report["integrity"]["report_payload_sha256"],
    }
