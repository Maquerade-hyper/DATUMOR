from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_TYPE = "datumor.optimization_report"
REPORT_VERSION = "1.0.0"


class OptimizationReportError(Exception):
    """Raised when an optimization report cannot be generated or validated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    return default


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _operation_status(result: Any, supplied: bool) -> str:
    if not supplied:
        return "skipped"

    if not isinstance(result, dict):
        return "failed"

    status = str(result.get("status", "")).lower()

    if status in {"completed", "success", "successful", "ready"}:
        return "completed"

    if status in {"skipped", "not_configured", "disabled"}:
        return "skipped"

    if status in {"failed", "error", "invalid"}:
        return "failed"

    validation = result.get("validation")
    if isinstance(validation, dict) and validation.get("valid") is False:
        return "failed"

    return "failed"


def _extract_warnings(result: Any, operation: str) -> list[dict[str, str]]:
    if not isinstance(result, dict):
        return []

    raw = result.get("warnings", [])
    if not isinstance(raw, list):
        return []

    warnings = []
    for item in raw:
        if isinstance(item, str):
            warnings.append({"operation": operation, "message": item})
        elif isinstance(item, dict):
            warnings.append({
                "operation": operation,
                "message": str(item.get("message", item.get("code", "Unspecified warning"))),
            })

    return warnings


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: str | None = None
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
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
        raise OptimizationReportError(f"Could not write report: {exc}") from exc


class OptimizationReportEngine:
    """Consolidates M7 optimization results into an auditable report."""

    def generate(
        self,
        *,
        tokenization: dict[str, Any] | None = None,
        chunking: dict[str, Any] | None = None,
        embedding: dict[str, Any] | None = None,
        indexing: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        dataset_id: str | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:

        operations = {
            "tokenization": tokenization,
            "chunking": chunking,
            "embedding": embedding,
            "indexing": indexing,
            "validation": validation,
        }

        statuses = {
            name: _operation_status(result, result is not None)
            for name, result in operations.items()
        }

        warnings = []
        for name, result in operations.items():
            warnings.extend(_extract_warnings(result, name))

        failures = [
            name for name, status in statuses.items()
            if status == "failed"
        ]

        skipped = [
            name for name, status in statuses.items()
            if status == "skipped"
        ]

        token_result = tokenization or {}
        chunk_result = chunking or {}
        embedding_result = embedding or {}
        indexing_result = indexing or {}
        validation_result = validation or {}

        token_summary = token_result.get("summary", {})
        if not isinstance(token_summary, dict):
            token_summary = {}

        chunk_summary = chunk_result.get("summary", {})
        if not isinstance(chunk_summary, dict):
            chunk_summary = {}

        embedding_summary = embedding_result.get("summary", {})
        if not isinstance(embedding_summary, dict):
            embedding_summary = {}

        token_count = _safe_int(
            token_summary.get("total_tokens", token_summary.get("token_count"))
        )

        chunk_count = _safe_int(
            chunk_summary.get(
                "chunk_count",
                chunk_summary.get("total_chunks", chunk_summary.get("chunks")),
            )
        )

        embedding_count = _safe_int(
            embedding_summary.get(
                "embedded_chunks",
                embedding_summary.get("embedding_count"),
            )
        )

        indexed_count = _safe_int(
            indexing_result.get(
                "indexed_points",
                indexing_result.get("indexed_count"),
            )
        )

        tokenizer_identity = {
            key: token_result.get(key)
            for key in ("tokenizer", "tokenizer_id", "tokenizer_fingerprint", "model")
            if token_result.get(key) is not None
        }

        chunk_identity = {
            key: chunk_result.get(key)
            for key in ("chunk_size", "overlap", "content_type")
            if chunk_result.get(key) is not None
        }

        embedding_provider = embedding_result.get("provider")
        if not isinstance(embedding_provider, dict):
            embedding_provider = None

        collection = indexing_result.get("collection")

        embedding_dimensions = embedding_summary.get(
            "dimensions",
            embedding_result.get("dimensions"),
        )

        validation_errors = []
        if isinstance(validation_result.get("errors"), list):
            validation_errors = [
                str(error) for error in validation_result["errors"]
            ]

        validation_valid = (
            validation_result.get("valid") is True
            if validation_result
            else None
        )

        # An indexing report is meaningful only when embeddings were produced.
        if statuses["indexing"] == "completed" and statuses["embedding"] != "completed":
            failures.append("indexing_dependency")
            warnings.append({
                "operation": "indexing",
                "message": "Indexing is marked completed but embedding generation is not completed.",
            })

        # Explicit validation failures must never produce a ready report.
        if validation_valid is False:
            if "validation" not in failures:
                failures.append("validation")

        required_pipeline = ("tokenization", "chunking")
        core_complete = all(statuses[name] == "completed" for name in required_pipeline)

        optional_operations_ok = all(
            statuses[name] != "failed"
            for name in ("embedding", "indexing")
        )

        readiness = (
            "ready"
            if core_complete
            and optional_operations_ok
            and validation_valid is not False
            else "not_ready"
        )

        report = {
            "report_type": REPORT_TYPE,
            "report_version": REPORT_VERSION,
            "report_id": str(uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_id": dataset_id,
            "profile": profile,
            "status": "completed" if not failures else "completed_with_failures",
            "readiness": readiness,
            "operations": {
                "tokenization": {
                    "status": statuses["tokenization"],
                    "summary": {
                        "total_tokens": token_count,
                        "tokenizer_identity": tokenizer_identity,
                    },
                },
                "chunking": {
                    "status": statuses["chunking"],
                    "summary": {
                        "chunk_count": chunk_count,
                        "configuration": chunk_identity,
                    },
                },
                "embedding": {
                    "status": statuses["embedding"],
                    "summary": {
                        "embedded_chunks": embedding_count,
                        "dimensions": embedding_dimensions,
                        "provider": embedding_provider,
                    },
                },
                "indexing": {
                    "status": statuses["indexing"],
                    "summary": {
                        "indexed_points": indexed_count,
                        "collection": collection,
                        "idempotent": indexing_result.get("idempotent"),
                    },
                },
                "validation": {
                    "status": statuses["validation"],
                    "valid": validation_valid,
                    "errors": validation_errors,
                },
            },
            "summary": {
                "token_count": token_count,
                "chunk_count": chunk_count,
                "embedded_chunks": embedding_count,
                "indexed_points": indexed_count,
                "completed_operations": sum(
                    value == "completed" for value in statuses.values()
                ),
                "skipped_operations": len(skipped),
                "failed_operations": len(set(failures)),
            },
            "skipped_operations": skipped,
            "failed_operations": list(dict.fromkeys(failures)),
            "warnings": warnings,
            "limitations": [
                "Readiness indicates optimization pipeline readiness, not proof of model-training quality.",
                "Skipped optional embedding and indexing operations do not invalidate an otherwise successful preparation pipeline.",
                "Token and chunk statistics are reported only when supplied by upstream results.",
            ],
            "provenance": {
                "upstream_result_hashes": {
                    name: _sha256(_canonical_json(result))
                    for name, result in operations.items()
                    if result is not None
                },
            },
        }

        report["report_sha256"] = _sha256(_canonical_json(report))
        return report


def validate_optimization_report(report: dict[str, Any]) -> dict[str, Any]:
    errors = []

    if not isinstance(report, dict):
        return {"valid": False, "errors": ["Report must be an object."]}

    if report.get("report_type") != REPORT_TYPE:
        errors.append("Invalid report_type.")

    if report.get("report_version") != REPORT_VERSION:
        errors.append("Unsupported report_version.")

    for field in (
        "report_id",
        "generated_at",
        "operations",
        "summary",
        "provenance",
        "report_sha256",
    ):
        if field not in report:
            errors.append(f"Missing required field: {field}")

    operations = report.get("operations")
    if isinstance(operations, dict):
        for name in ("tokenization", "chunking", "embedding", "indexing", "validation"):
            operation = operations.get(name)
            if not isinstance(operation, dict):
                errors.append(f"Missing operation: {name}")
                continue

            if operation.get("status") not in {"completed", "skipped", "failed"}:
                errors.append(f"Invalid status for {name}.")

    if report.get("readiness") not in {"ready", "not_ready"}:
        errors.append("Invalid readiness value.")

    if not errors:
        expected_hash = report.get("report_sha256")
        unhashed = {key: value for key, value in report.items() if key != "report_sha256"}
        actual_hash = _sha256(_canonical_json(unhashed))

        if expected_hash != actual_hash:
            errors.append("Report SHA-256 integrity check failed.")

    return {"valid": not errors, "errors": errors}


def export_optimization_report(
    report: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    validation = validate_optimization_report(report)
    if not validation["valid"]:
        raise OptimizationReportError(
            f"Refusing to export invalid report: {validation['errors']}"
        )

    path = Path(output_path)
    content = _canonical_json(report) + "\n"
    _atomic_write(path, content)

    return {
        "status": "completed",
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def load_optimization_report(path: str | Path) -> dict[str, Any]:
    try:
        report = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Invalid JSON constant: {value}")
            ),
            object_pairs_hook=lambda pairs: _reject_duplicate_keys(pairs),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise OptimizationReportError(f"Could not load report: {exc}") from exc

    validation = validate_optimization_report(report)
    if not validation["valid"]:
        raise OptimizationReportError(
            f"Loaded report is invalid: {validation['errors']}"
        )

    return report


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def render_optimization_markdown(report: dict[str, Any]) -> str:
    validation = validate_optimization_report(report)
    if not validation["valid"]:
        raise OptimizationReportError(
            f"Cannot render invalid report: {validation['errors']}"
        )

    summary = report["summary"]
    lines = [
        "# DATUMOR Optimization Report",
        "",
        f"- Report ID: `{report['report_id']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Dataset: `{report.get('dataset_id') or 'Not specified'}`",
        f"- Profile: `{report.get('profile') or 'Not specified'}`",
        f"- Status: **{report['status']}**",
        f"- Optimization readiness: **{report['readiness']}**",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Tokens | {summary['token_count']} |",
        f"| Chunks | {summary['chunk_count']} |",
        f"| Embedded chunks | {summary['embedded_chunks']} |",
        f"| Indexed points | {summary['indexed_points']} |",
        f"| Completed operations | {summary['completed_operations']} |",
        f"| Skipped operations | {summary['skipped_operations']} |",
        f"| Failed operations | {summary['failed_operations']} |",
        "",
        "## Operation details",
        "",
        "| Operation | Status |",
        "|---|---|",
    ]

    for name, operation in report["operations"].items():
        lines.append(f"| {name} | {operation['status']} |")

    lines.extend(["", "## Skipped operations", ""])
    lines.extend(
        [f"- {name}" for name in report["skipped_operations"]]
        or ["- None"]
    )

    lines.extend(["", "## Failed operations", ""])
    lines.extend(
        [f"- {name}" for name in report["failed_operations"]]
        or ["- None"]
    )

    lines.extend(["", "## Warnings", ""])
    lines.extend(
        [
            f"- **{item['operation']}**: {item['message']}"
            for item in report["warnings"]
        ]
        or ["- None"]
    )

    lines.extend(["", "## Limitations", ""])
    lines.extend([f"- {item}" for item in report["limitations"]])
    lines.extend(["", f"Report SHA-256: `{report['report_sha256']}`", ""])

    return "\n".join(lines)


def export_optimization_markdown(
    report: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    content = render_optimization_markdown(report)
    path = Path(output_path)
    _atomic_write(path, content)

    return {
        "status": "completed",
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
