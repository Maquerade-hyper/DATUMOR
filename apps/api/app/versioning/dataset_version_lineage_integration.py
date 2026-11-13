from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from apps.api.app.lineage.dataset_version_lineage import (
    record_dataset_version_lineage,
)
from apps.api.app.versioning.dataset_versioning import (
    create_dataset_version,
)


class DatasetVersionLineageError(RuntimeError):
    """A snapshot exists, but its lineage event could not be recorded."""

    def __init__(self, version_record: dict, cause: Exception):
        self.version_record = version_record
        self.version_id = version_record["version_id"]
        self.version_number = version_record["version_number"]
        super().__init__(
            "Dataset version snapshot was created, but lineage persistence "
            f"failed. version_id={self.version_id}, "
            f"version={self.version_number}. "
            "The snapshot remains on disk and requires lineage recovery."
        )
        self.__cause__ = cause


def create_dataset_version_with_lineage(
    dataset: dict,
    storage_dir: str | Path,
    dataset_id: str,
    session,
    *,
    pipeline_run_id: str,
    source_ids: Iterable[str],
    parent_version_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    actor: str = "system",
) -> dict:
    """Create an M8.3 immutable snapshot and persist its lineage event.

    The caller owns the SQLAlchemy transaction and must commit it.
    Filesystem snapshots cannot participate in the database transaction.
    If lineage persistence fails, the snapshot is retained and the raised
    exception exposes its version identity for recovery.
    """
    if session is None:
        raise ValueError("A SQLAlchemy session is required.")
    if not isinstance(metadata or {}, Mapping):
        raise ValueError("metadata must be a mapping.")

    version_record = create_dataset_version(
        dataset=dataset,
        storage_dir=storage_dir,
        dataset_id=dataset_id,
        parent_version_id=parent_version_id,
        metadata=dict(metadata or {}),
    )

    try:
        event = record_dataset_version_lineage(
            session,
            dataset_id=version_record["dataset_id"],
            dataset_version=version_record["version_number"],
            version_id=version_record["version_id"],
            parent_version_id=version_record["parent_version_id"],
            pipeline_run_id=pipeline_run_id,
            source_ids=source_ids,
            actor=actor,
            output_checksum_sha256=version_record["dataset_sha256"],
            metadata={
                "version_schema": version_record["schema_version"],
                "snapshot_created_at": version_record["created_at"],
            },
        )
    except Exception as exc:
        raise DatasetVersionLineageError(version_record, exc) from exc

    return {
        "version": version_record,
        "lineage_event": event,
        "lineage_persisted": True,
        "transaction_committed": False,
    }
