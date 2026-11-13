from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from apps.api.app.lineage.lineage_registry import record_lineage_event


def _uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID.") from exc


def _checksum(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).lower()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("output_checksum_sha256 must be a SHA-256 hex digest.")
    return value


def record_dataset_version_lineage(
    session,
    *,
    dataset_id: str,
    dataset_version: int,
    version_id: str,
    pipeline_run_id: str,
    source_ids: Iterable[str],
    parent_version_id: str | None = None,
    actor: str = "system",
    output_checksum_sha256: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record the provenance of one immutable dataset version.

    The caller owns the transaction. This function never commits.
    """
    dataset_id = _uuid(dataset_id, "dataset_id")
    version_id = _uuid(version_id, "version_id")
    pipeline_run_id = _uuid(pipeline_run_id, "pipeline_run_id")

    if isinstance(dataset_version, bool) or not isinstance(dataset_version, int):
        raise ValueError("dataset_version must be an integer.")
    if dataset_version < 1:
        raise ValueError("dataset_version must be at least 1.")

    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be a non-empty string.")

    parent_version_id = (
        _uuid(parent_version_id, "parent_version_id")
        if parent_version_id is not None
        else None
    )
    if parent_version_id == version_id:
        raise ValueError("A dataset version cannot be its own parent.")
    if dataset_version == 1 and parent_version_id is not None:
        raise ValueError("The first dataset version cannot have a parent.")
    if dataset_version > 1 and parent_version_id is None:
        raise ValueError("A subsequent dataset version requires a parent.")

    normalized_sources = sorted({
        _uuid(source_id, "source_id") for source_id in source_ids
    })

    if not isinstance(metadata or {}, Mapping):
        raise ValueError("metadata must be a mapping.")

    event_metadata = dict(metadata or {})
    reserved = {
        "lineage_action",
        "version_id",
        "parent_version_id",
        "source_ids",
        "pipeline_run_id",
    }
    if reserved.intersection(event_metadata):
        raise ValueError("metadata cannot override reserved lineage fields.")

    event_metadata.update({
        "lineage_action": "dataset_version_created",
        "version_id": version_id,
        "parent_version_id": parent_version_id,
        "source_ids": normalized_sources,
        "pipeline_run_id": pipeline_run_id,
    })

    input_references = [f"source:{source_id}" for source_id in normalized_sources]
    if parent_version_id:
        input_references.append(f"dataset_version:{parent_version_id}")

    event = {
        "contract_version": "1.0.0",
        "event_id": str(uuid.uuid4()),
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "event_type": "transformed",
        "actor": actor.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_references": input_references,
        "output_checksum_sha256": _checksum(output_checksum_sha256),
        "metadata": event_metadata,
    }

    record_lineage_event(session, event)
    return event


def build_dataset_version_lineage(
    events: Iterable[Mapping[str, Any]],
    dataset_id: str,
) -> dict[str, Any]:
    """Build and validate a dataset version ancestry graph from lineage events."""
    dataset_id = _uuid(dataset_id, "dataset_id")
    versions: dict[int, dict[str, Any]] = {}
    version_ids: set[str] = set()

    for event in events:
        if event.get("dataset_id") != dataset_id:
            continue
        metadata = event.get("metadata") or {}
        if metadata.get("lineage_action") != "dataset_version_created":
            continue

        number = event.get("dataset_version")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("Lineage event contains an invalid dataset_version.")

        version_id = _uuid(metadata.get("version_id"), "version_id")
        if number in versions or version_id in version_ids:
            raise ValueError("Duplicate dataset version lineage entry.")

        parent_id = metadata.get("parent_version_id")
        if parent_id is not None:
            parent_id = _uuid(parent_id, "parent_version_id")

        source_ids = metadata.get("source_ids", [])
        if not isinstance(source_ids, list):
            raise ValueError("Lineage source_ids must be a list.")
        source_ids = sorted({_uuid(item, "source_id") for item in source_ids})

        pipeline_run_id = _uuid(metadata.get("pipeline_run_id"), "pipeline_run_id")

        versions[number] = {
            "dataset_version": number,
            "version_id": version_id,
            "parent_version_id": parent_id,
            "source_ids": source_ids,
            "pipeline_run_id": pipeline_run_id,
            "event_id": event.get("event_id"),
            "output_checksum_sha256": event.get("output_checksum_sha256"),
            "timestamp": event.get("timestamp"),
        }
        version_ids.add(version_id)

    ordered = [versions[key] for key in sorted(versions)]

    for index, version in enumerate(ordered):
        expected_parent = ordered[index - 1]["version_id"] if index else None
        if version["parent_version_id"] != expected_parent:
            raise ValueError(
                f"Broken version ancestry at dataset version "
                f"{version['dataset_version']}."
            )

    return {
        "dataset_id": dataset_id,
        "version_count": len(ordered),
        "latest_version": ordered[-1]["dataset_version"] if ordered else None,
        "versions": ordered,
    }
