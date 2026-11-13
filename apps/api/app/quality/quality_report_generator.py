"""Consolidated, read-only DATUMOR quality report generation."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from apps.api.app.quality.quality_metrics import calculate_quality_metrics, validate_dukr
from apps.api.app.quality.duplicate_detector import detect_duplicates
from apps.api.app.quality.consistency_analyzer import analyze_consistency
from apps.api.app.quality.provenance_verifier import verify_provenance


REPORT_TYPE = "datumor.quality_report"
REPORT_VERSION = "1.0.0"


def _status_counts(findings: list[dict]) -> dict:
    counts = {"total": len(findings)}
    for status in ("verified", "failed", "unverifiable"):
        counts[status] = sum(
            1 for finding in findings
            if str(finding.get("status", "")).lower() == status
        )
    return counts


def _document_identity(dukr: dict) -> dict:
    source = dukr.get("source", {})
    return {
        "representation_id": dukr.get("representation_id"),
        "source_id": source.get("source_id"),
        "filename": source.get("filename"),
        "checksum_sha256": source.get("checksum_sha256"),
    }


def generate_quality_report(
    dukr_documents: list[dict],
    near_duplicate_threshold: float = 0.90,
) -> dict:
    """Generate consolidated quality analysis without modifying DUKR inputs."""

    if not isinstance(dukr_documents, list) or not dukr_documents:
        raise ValueError("dukr_documents must be a non-empty list")

    if not 0 < near_duplicate_threshold <= 1:
        raise ValueError("near_duplicate_threshold must be greater than 0 and at most 1")

    snapshots = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in dukr_documents]

    document_reports = []
    for dukr in dukr_documents:
        if not isinstance(dukr, dict):
            raise ValueError("Every DUKR document must be a dictionary")

        metrics = calculate_quality_metrics(dukr)
        validation = validate_dukr(dukr)

        document_reports.append({
            "source": _document_identity(dukr),
            "quality_metrics": metrics,
            "dukr_validation": validation,
        })

    duplicates = detect_duplicates(
        dukr_documents,
        near_duplicate_threshold=near_duplicate_threshold,
    )
    consistency = analyze_consistency(dukr_documents)
    provenance = verify_provenance(dukr_documents)

    provenance_summary = provenance.get("summary", {})
    validation_failures = sum(
        1 for item in document_reports
        if item["dukr_validation"].get("valid") is not True
    )

    failed_provenance = provenance_summary.get("failed", 0)
    unverifiable_provenance = provenance_summary.get("unverifiable", 0)

    if validation_failures or failed_provenance:
        overall_status = "failed"
    elif unverifiable_provenance:
        overall_status = "incomplete"
    else:
        overall_status = "completed"

    report = {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "summary": {
            "documents_assessed": len(dukr_documents),
            "dukr_validation_passed": len(dukr_documents) - validation_failures,
            "dukr_validation_failed": validation_failures,
            "provenance": provenance_summary,
            "duplicate_groups": len(duplicates.get("groups", [])),
            "consistency_findings": len(consistency.get("findings", [])),
            "consistency_review_required": sum(
                1 for finding in consistency.get("findings", [])
                if finding.get("review_required") is True
            ),
        },
        "documents": document_reports,
        "duplicate_analysis": duplicates,
        "consistency_analysis": consistency,
        "provenance_verification": provenance,
        "automatic_changes_made": False,
    }

    # Guard against accidental mutation by any analysis component.
    if snapshots != [
        json.dumps(item, sort_keys=True, ensure_ascii=False)
        for item in dukr_documents
    ]:
        raise RuntimeError("Quality analysis modified an input DUKR document")

    return report


def render_quality_report_markdown(report: dict) -> str:
    """Render a consolidated report as readable Markdown."""

    summary = report.get("summary", {})
    lines = [
        "# DATUMOR Quality Report",
        "",
        f"- **Status:** {report.get('status', 'unknown')}",
        f"- **Generated:** {report.get('generated_at', 'unknown')}",
        f"- **Documents assessed:** {summary.get('documents_assessed', 0)}",
        f"- **DUKR validation passed:** {summary.get('dukr_validation_passed', 0)}",
        f"- **DUKR validation failed:** {summary.get('dukr_validation_failed', 0)}",
        f"- **Duplicate groups:** {summary.get('duplicate_groups', 0)}",
        f"- **Consistency findings:** {summary.get('consistency_findings', 0)}",
        f"- **Consistency findings requiring review:** {summary.get('consistency_review_required', 0)}",
        "",
        "## Provenance",
        "",
    ]

    provenance = report.get("provenance_verification", {})
    provenance_summary = provenance.get("summary", {})
    lines.extend([
        f"- **Status:** {provenance.get('status', 'unknown')}",
        f"- **Verified:** {provenance_summary.get('verified', 0)}",
        f"- **Failed:** {provenance_summary.get('failed', 0)}",
        f"- **Unverifiable:** {provenance_summary.get('unverifiable', 0)}",
        "",
        "## Per-document quality metrics",
        "",
    ])

    for index, document in enumerate(report.get("documents", []), start=1):
        source = document.get("source", {})
        lines.extend([
            f"### Document {index}: {source.get('filename') or source.get('source_id') or 'Unknown'}",
            "",
            f"- **Source ID:** {source.get('source_id') or 'Unavailable'}",
            f"- **Checksum:** `{source.get('checksum_sha256') or 'Unavailable'}`",
            f"- **DUKR valid:** {document.get('dukr_validation', {}).get('valid', 'unknown')}",
            "",
            "#### Quality metrics",
            "",
            "```json",
            json.dumps(document.get("quality_metrics", {}), indent=2, ensure_ascii=False),
            "```",
            "",
        ])

    for section, key in (
        ("Duplicate analysis", "duplicate_analysis"),
        ("Consistency analysis", "consistency_analysis"),
        ("Provenance findings", "provenance_verification"),
    ):
        lines.extend([
            f"## {section}",
            "",
            "```json",
            json.dumps(report.get(key, {}), indent=2, ensure_ascii=False),
            "```",
            "",
        ])

    lines.extend([
        "## Integrity statement",
        "",
        f"- **Automatic changes made:** {report.get('automatic_changes_made', False)}",
        "- Original DUKR documents are retained unchanged.",
        "",
    ])

    return "\n".join(lines)


def export_quality_report(report: dict, output_directory: str) -> dict:
    """Write JSON and Markdown report files."""

    from pathlib import Path

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "quality_report.json"
    markdown_path = directory / "quality_report.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_quality_report_markdown(report),
        encoding="utf-8",
    )

    return {
        "json_path": str(json_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
    }
