import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPORT_SCHEMA_VERSION = "1.0"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _source_summary(result: dict, index: int) -> dict:
    status = result.get("status", "success")
    if status not in {"success", "failed", "partial"}:
        status = "failed"

    metadata = result.get("metadata") or {}
    source_metadata = metadata.get("source") or {}
    source_identity = metadata.get("source_identity") or {}

    records = result.get("records")
    record_count = len(records) if isinstance(records, list) else 0

    warnings = result.get("warnings") or []
    syntax_errors = result.get("syntax_errors") or []

    error = result.get("error")
    if error:
        status = "failed"

    source_name = (
        result.get("source_filename")
        or source_metadata.get("filename")
        or result.get("source")
        or f"source-{index + 1}"
    )

    return {
        "source_index": index + 1,
        "source_id": (
            source_identity.get("source_id")
            or result.get("source_id")
        ),
        "project_id": (
            source_identity.get("project_id")
            or result.get("project_id")
        ),
        "source_filename": source_name,
        "source_path": (
            source_metadata.get("path")
            or result.get("source_path")
        ),
        "format": result.get("format") or source_metadata.get("format"),
        "media_type": source_metadata.get("media_type"),
        "status": status,
        "size_bytes": source_metadata.get("size_bytes"),
        "checksum_sha256": source_metadata.get("checksum_sha256"),
        "record_count": record_count,
        "warning_count": len(warnings),
        "warnings": warnings,
        "syntax_error_count": len(syntax_errors),
        "syntax_errors": syntax_errors,
        "metadata": metadata,
        "error": _safe_text(error) if error else None,
    }


def generate_extraction_report(
    results: dict | Iterable[dict],
    *,
    report_id: str | None = None,
    project_id: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Build a JSON-serializable extraction report from extraction results.

    A failed source can be represented as:
    {
        "source_filename": "broken.pdf",
        "status": "failed",
        "error": "Invalid PDF"
    }
    """
    if isinstance(results, dict):
        results = [results]

    if isinstance(results, (str, bytes)):
        raise TypeError("results must be an extraction result or iterable of results")

    try:
        source_results = list(results)
    except TypeError as exc:
        raise TypeError("results must be an extraction result or iterable of results") from exc

    if not source_results:
        raise ValueError("At least one extraction result is required")

    if not all(isinstance(item, dict) for item in source_results):
        raise TypeError("Every extraction result must be a dictionary")

    sources = [
        _source_summary(item, index)
        for index, item in enumerate(source_results)
    ]

    successful = sum(item["status"] == "success" for item in sources)
    failed = sum(item["status"] == "failed" for item in sources)
    partial = sum(item["status"] == "partial" for item in sources)

    total_records = sum(item["record_count"] for item in sources)
    total_warnings = sum(item["warning_count"] for item in sources)
    total_syntax_errors = sum(
        item["syntax_error_count"] for item in sources
    )

    formats: dict[str, int] = {}
    for item in sources:
        fmt = item["format"] or "unknown"
        formats[fmt] = formats.get(fmt, 0) + 1

    if failed == 0 and partial == 0:
        overall_status = "success"
    elif successful == 0 and partial == 0:
        overall_status = "failed"
    else:
        overall_status = "partial"

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id or str(uuid.uuid4()),
        "project_id": project_id,
        "generated_at": generated_at or _timestamp(),
        "status": overall_status,
        "summary": {
            "total_sources": len(sources),
            "successful_sources": successful,
            "failed_sources": failed,
            "partial_sources": partial,
            "total_records": total_records,
            "total_warnings": total_warnings,
            "total_syntax_errors": total_syntax_errors,
            "formats": formats,
        },
        "sources": sources,
    }


def render_extraction_report_markdown(report: dict) -> str:
    """Render a human-readable Markdown version of a report."""
    summary = report["summary"]
    lines = [
        "# DATUMOR Extraction Report",
        "",
        f"- **Report ID:** {report['report_id']}",
        f"- **Project ID:** {report.get('project_id') or 'Not supplied'}",
        f"- **Generated at:** {report['generated_at']}",
        f"- **Overall status:** {report['status'].upper()}",
        "",
        "## Summary",
        "",
        f"- Sources processed: {summary['total_sources']}",
        f"- Successful: {summary['successful_sources']}",
        f"- Failed: {summary['failed_sources']}",
        f"- Partial: {summary['partial_sources']}",
        f"- Extracted records: {summary['total_records']}",
        f"- Warnings: {summary['total_warnings']}",
        f"- Syntax errors: {summary['total_syntax_errors']}",
        "",
        "## Formats",
        "",
    ]

    for fmt, count in sorted(summary["formats"].items()):
        lines.append(f"- {fmt}: {count}")

    lines.extend(["", "## Source Details", ""])

    for source in report["sources"]:
        lines.extend([
            f"### {source['source_filename']}",
            "",
            f"- Status: {source['status']}",
            f"- Format: {source['format'] or 'Unknown'}",
            f"- Path: {source['source_path'] or 'Not supplied'}",
            f"- Source ID: {source['source_id'] or 'Not supplied'}",
            f"- Size: {source['size_bytes'] if source['size_bytes'] is not None else 'Unknown'} bytes",
            f"- SHA-256: `{source['checksum_sha256'] or 'Not supplied'}`",
            f"- Records: {source['record_count']}",
            f"- Warnings: {source['warning_count']}",
            f"- Syntax errors: {source['syntax_error_count']}",
        ])

        if source["error"]:
            lines.append(f"- Error: {source['error']}")

        if source["warnings"]:
            lines.extend(["", "**Warnings:**"])
            for warning in source["warnings"]:
                lines.append(f"- {_safe_text(warning)}")

        if source["syntax_errors"]:
            lines.extend(["", "**Syntax errors:**"])
            for error in source["syntax_errors"]:
                if isinstance(error, dict):
                    location = error.get("start_line", "unknown")
                    description = error.get("syntax_type", "syntax error")
                    lines.append(f"- Line {location}: {description}")
                else:
                    lines.append(f"- {_safe_text(error)}")

        lines.append("")

    lines.extend([
        "---",
        "",
        "Generated by DATUMOR. This report summarizes extraction results; "
        "it does not replace the original source files or extracted datasets.",
        "",
    ])

    return "\n".join(lines)


def write_extraction_report(
    report: dict,
    output_directory: str | Path,
    *,
    basename: str = "extraction-report",
) -> dict:
    """Write JSON and Markdown report files and return their paths."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", basename):
        raise ValueError("Invalid report basename")

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    json_path = output / f"{basename}.json"
    markdown_path = output / f"{basename}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_extraction_report_markdown(report),
        encoding="utf-8",
    )

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }
