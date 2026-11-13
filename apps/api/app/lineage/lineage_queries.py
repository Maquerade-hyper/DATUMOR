from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from apps.api.app.lineage.dataset_version_lineage import (
    build_dataset_version_lineage,
)
from apps.api.app.lineage.lineage_registry import (
    list_lineage_events,
)


class LineageQueryError(ValueError):
    """Invalid lineage query or report request."""


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise LineageQueryError(
            f"{field} must be a valid UUID."
        ) from exc


def _all_dataset_events(
    session,
    dataset_id: str,
    *,
    dataset_version: int | None = None,
    event_type: str | None = None,
) -> list[dict]:
    events = []
    offset = 0
    page_size = 1000

    while True:
        page = list_lineage_events(
            session,
            dataset_id,
            dataset_version=dataset_version,
            event_type=event_type,
            limit=page_size,
            offset=offset,
        )
        events.extend(page)

        if len(page) < page_size:
            break

        offset += page_size

    return events


def query_dataset_lineage(
    session,
    dataset_id: str,
    *,
    dataset_version: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Query a dataset's persisted lineage history."""
    dataset_id = _validate_uuid(dataset_id, "dataset_id")

    events = list_lineage_events(
        session,
        dataset_id,
        dataset_version=dataset_version,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )

    return {
        "dataset_id": dataset_id,
        "filters": {
            "dataset_version": dataset_version,
            "event_type": event_type,
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned": len(events),
        },
        "events": events,
    }


def get_complete_dataset_lineage(
    session,
    dataset_id: str,
) -> dict[str, Any]:
    """Retrieve complete event history and reconstruct version ancestry."""
    dataset_id = _validate_uuid(dataset_id, "dataset_id")
    events = _all_dataset_events(session, dataset_id)

    version_graph = build_dataset_version_lineage(
        events,
        dataset_id,
    )

    event_counts: dict[str, int] = {}
    for event in events:
        event_type = event["event_type"]
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    exports = [
        event for event in events
        if event["event_type"] == "exported"
    ]

    return {
        "dataset_id": dataset_id,
        "event_count": len(events),
        "event_counts": event_counts,
        "version_graph": version_graph,
        "exports": exports,
        "events": events,
    }


def query_source_lineage(
    session,
    dataset_id: str,
    source_id: str,
) -> dict[str, Any]:
    """Find all events referencing a source within a dataset."""
    dataset_id = _validate_uuid(dataset_id, "dataset_id")
    source_id = _validate_uuid(source_id, "source_id")

    events = _all_dataset_events(session, dataset_id)
    reference = f"source:{source_id}"

    matches = []
    for event in events:
        metadata = event.get("metadata") or {}
        source_ids = metadata.get("source_ids") or []

        if (
            reference in event.get("input_references", [])
            or source_id in source_ids
        ):
            matches.append(event)

    versions = sorted({
        event["dataset_version"] for event in matches
    })

    return {
        "dataset_id": dataset_id,
        "source_id": source_id,
        "event_count": len(matches),
        "dataset_versions": versions,
        "events": matches,
    }


def query_export_lineage(
    session,
    dataset_id: str,
    *,
    dataset_version: int | None = None,
) -> dict[str, Any]:
    """Retrieve export events and their artifact/manifest integrity data."""
    dataset_id = _validate_uuid(dataset_id, "dataset_id")

    if dataset_version is not None:
        if (
            isinstance(dataset_version, bool)
            or not isinstance(dataset_version, int)
            or dataset_version < 1
        ):
            raise LineageQueryError(
                "dataset_version must be a positive integer."
            )

    events = _all_dataset_events(
        session,
        dataset_id,
        dataset_version=dataset_version,
        event_type="exported",
    )

    exports = []
    for event in events:
        metadata = event.get("metadata") or {}
        exports.append({
            "event_id": event["event_id"],
            "dataset_version": event["dataset_version"],
            "timestamp": event["timestamp"],
            "actor": event["actor"],
            "version_id": metadata.get("version_id"),
            "pipeline_run_id": metadata.get("pipeline_run_id"),
            "format": metadata.get("format"),
            "filename": metadata.get("filename"),
            "artifact_path": metadata.get("artifact_path"),
            "artifact_sha256": event["output_checksum_sha256"],
            "manifest_path": metadata.get("manifest_path"),
            "manifest_sha256": metadata.get("manifest_sha256"),
            "artifact_size_bytes": metadata.get("artifact_size_bytes"),
            "manifest_size_bytes": metadata.get("manifest_size_bytes"),
            "example_count": metadata.get("example_count"),
            "integrity_verified": metadata.get("integrity_verified"),
            "manifest_integrity_verified": metadata.get(
                "manifest_integrity_verified"
            ),
        })

    return {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "export_count": len(exports),
        "exports": exports,
    }


def build_lineage_report(
    session,
    dataset_id: str,
) -> dict[str, Any]:
    """Build a complete machine-readable lineage report."""
    lineage = get_complete_dataset_lineage(session, dataset_id)

    verified_exports = sum(
        1 for export in lineage["exports"]
        if (export.get("metadata") or {}).get("integrity_verified") is True
        and (export.get("metadata") or {}).get(
            "manifest_integrity_verified"
        ) is True
    )

    return {
        "report_type": "datumor.dataset_lineage_report",
        "report_version": "1.0.0",
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "dataset_id": lineage["dataset_id"],
        "summary": {
            "total_events": lineage["event_count"],
            "total_versions": lineage["version_graph"]["version_count"],
            "total_exports": len(lineage["exports"]),
            "verified_exports": verified_exports,
            "event_counts": lineage["event_counts"],
        },
        "version_graph": lineage["version_graph"],
        "events": lineage["events"],
    }


def render_lineage_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable Markdown lineage report."""
    summary = report["summary"]
    graph = report["version_graph"]

    lines = [
        "# DATUMOR Dataset Lineage Report",
        "",
        f"- Dataset ID: `{report['dataset_id']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Report version: `{report['report_version']}`",
        "",
        "## Summary",
        "",
        f"- Total events: {summary['total_events']}",
        f"- Dataset versions: {summary['total_versions']}",
        f"- Exports: {summary['total_exports']}",
        f"- Integrity-verified exports: {summary['verified_exports']}",
        "",
        "## Version History",
        "",
    ]

    if not graph["versions"]:
        lines.append("No dataset version lineage events were found.")
    else:
        for version in graph["versions"]:
            parent = version["parent_version_id"] or "None"
            lines.extend([
                f"### Version {version['dataset_version']}",
                f"- Version ID: `{version['version_id']}`",
                f"- Parent: `{parent}`",
                f"- Pipeline run: `{version['pipeline_run_id']}`",
                f"- Sources: {len(version['source_ids'])}",
                f"- Checksum: `{version['output_checksum_sha256']}`",
                "",
            ])

    lines.extend(["## Event History", ""])

    for event in report["events"]:
        lines.extend([
            f"### {event['event_type']} — Version {event['dataset_version']}",
            f"- Event ID: `{event['event_id']}`",
            f"- Timestamp: {event['timestamp']}",
            f"- Actor: {event['actor']}",
        ])

        metadata = event.get("metadata") or {}
        if metadata.get("filename"):
            lines.append(f"- Export file: `{metadata['filename']}`")
        if metadata.get("artifact_sha256"):
            lines.append(
                f"- Artifact SHA-256: `{metadata['artifact_sha256']}`"
            )
        if metadata.get("manifest_sha256"):
            lines.append(
                f"- Manifest SHA-256: `{metadata['manifest_sha256']}`"
            )

        lines.append("")

    return "\n".join(lines)


def write_lineage_report(
    report: dict[str, Any],
    output_dir: str | Path,
    *,
    filename: str = "lineage-report",
) -> dict[str, str]:
    """Write JSON and Markdown reports using atomic file replacement."""
    if (
        not isinstance(filename, str)
        or not filename.strip()
        or Path(filename).name != filename
        or filename in {".", ".."}
    ):
        raise LineageQueryError("Invalid report filename.")

    output_directory = Path(output_dir).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    json_path = output_directory / f"{filename}.json"
    markdown_path = output_directory / f"{filename}.md"

    json_content = (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"
    )
    markdown_content = render_lineage_markdown(report) + "\n"

    for path, content in (
        (json_path, json_content),
        (markdown_path, markdown_content),
    ):
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                import os
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }
