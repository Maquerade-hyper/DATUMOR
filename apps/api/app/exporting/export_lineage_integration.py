from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterable

from apps.api.app.exporting.dataset_exporter import export_dataset
from apps.api.app.lineage.lineage_registry import record_lineage_event


class ExportLineageError(RuntimeError):
    """An export completed, but its lineage could not be verified or saved."""

    def __init__(self, message: str, export_result: dict | None = None):
        self.export_result = export_result
        super().__init__(message)


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID.") from exc


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_export_result(result: dict) -> dict:
    required = {
        "success",
        "format",
        "filename",
        "path",
        "size_bytes",
        "example_count",
        "content_sha256",
        "integrity_verified",
        "manifest_filename",
        "manifest_path",
        "manifest_sha256",
        "manifest_integrity_verified",
    }
    missing = required - set(result)
    if missing:
        raise ExportLineageError(
            f"Exporter result is missing required fields: {sorted(missing)}",
            result,
        )

    if result["success"] is not True:
        raise ExportLineageError("Exporter did not report success.", result)

    if result["integrity_verified"] is not True:
        raise ExportLineageError(
            "Artifact integrity was not verified by the exporter.", result
        )

    if result["manifest_integrity_verified"] is not True:
        raise ExportLineageError(
            "Manifest integrity was not verified by the exporter.", result
        )

    artifact_path = Path(result["path"]).resolve()
    manifest_path = Path(result["manifest_path"]).resolve()

    if not artifact_path.is_file() or not manifest_path.is_file():
        raise ExportLineageError(
            "Export artifact or manifest is missing.", result
        )

    artifact_hash = _file_sha256(artifact_path)
    manifest_hash = _file_sha256(manifest_path)

    if artifact_hash != result["content_sha256"]:
        raise ExportLineageError(
            "Artifact checksum differs from the exporter result.", result
        )

    if manifest_hash != result["manifest_sha256"]:
        raise ExportLineageError(
            "Manifest checksum differs from the exporter result.", result
        )

    artifact_size = artifact_path.stat().st_size
    if artifact_size != result["size_bytes"]:
        raise ExportLineageError(
            "Artifact size differs from the exporter result.", result
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportLineageError(
            f"Export manifest cannot be read: {exc}", result
        ) from exc

    manifest_artifact = manifest.get("artifact")
    if not isinstance(manifest_artifact, dict):
        raise ExportLineageError(
            "Manifest does not contain an artifact object.", result
        )

    expected_manifest_values = {
        "filename": artifact_path.name,
        "format": result["format"],
        "sha256": artifact_hash,
        "size_bytes": artifact_size,
        "example_count": result["example_count"],
    }

    for key, expected in expected_manifest_values.items():
        if manifest_artifact.get(key) != expected:
            raise ExportLineageError(
                f"Manifest artifact field {key!r} does not match "
                "the verified export.",
                result,
            )

    if manifest.get("manifest_type") != "datumor.export_manifest":
        raise ExportLineageError("Unknown export manifest type.", result)

    return {
        "artifact_path": str(artifact_path),
        "manifest_path": str(manifest_path),
        "artifact_sha256": artifact_hash,
        "manifest_sha256": manifest_hash,
        "artifact_size_bytes": artifact_size,
        "manifest_size_bytes": manifest_path.stat().st_size,
        "manifest": manifest,
    }


def export_dataset_with_lineage(
    dataset: dict,
    output_dir: str | Path,
    configuration: dict,
    session,
    *,
    dataset_id: str,
    dataset_version: int,
    version_id: str,
    pipeline_run_id: str,
    source_ids: Iterable[str] = (),
    actor: str = "system",
) -> dict:
    """Export a dataset, verify both artifacts, and persist export lineage.

    The caller owns the SQLAlchemy transaction and must commit it.
    No successful export event is recorded unless artifact and manifest
    verification both pass.
    """
    if session is None:
        raise ValueError("A SQLAlchemy session is required.")

    dataset_id = _validate_uuid(dataset_id, "dataset_id")
    version_id = _validate_uuid(version_id, "version_id")
    pipeline_run_id = _validate_uuid(pipeline_run_id, "pipeline_run_id")

    if (
        isinstance(dataset_version, bool)
        or not isinstance(dataset_version, int)
        or dataset_version < 1
    ):
        raise ValueError("dataset_version must be a positive integer.")

    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be a non-empty string.")

    normalized_sources = sorted({
        _validate_uuid(source_id, "source_id")
        for source_id in source_ids
    })

    # Export failures propagate directly. No lineage event is written.
    export_result = export_dataset(
        dataset=dataset,
        output_dir=output_dir,
        configuration=configuration,
    )

    try:
        verified = _verify_export_result(export_result)

        input_references = [f"dataset_version:{version_id}"]
        input_references.extend(
            f"source:{source_id}" for source_id in normalized_sources
        )

        event = {
            "contract_version": "1.0.0",
            "event_id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "event_type": "exported",
            "actor": actor.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_references": input_references,
            "output_checksum_sha256": verified["artifact_sha256"],
            "metadata": {
                "lineage_action": "dataset_exported",
                "version_id": version_id,
                "pipeline_run_id": pipeline_run_id,
                "source_ids": normalized_sources,
                "format": export_result["format"],
                "filename": export_result["filename"],
                "artifact_path": verified["artifact_path"],
                "artifact_sha256": verified["artifact_sha256"],
                "artifact_size_bytes": verified["artifact_size_bytes"],
                "manifest_filename": export_result["manifest_filename"],
                "manifest_path": verified["manifest_path"],
                "manifest_sha256": verified["manifest_sha256"],
                "manifest_size_bytes": verified["manifest_size_bytes"],
                "example_count": export_result["example_count"],
                "manifest_type": verified["manifest"]["manifest_type"],
                "manifest_version": verified["manifest"]["manifest_version"],
                "integrity_verified": True,
                "manifest_integrity_verified": True,
            },
        }

        persisted_event = record_lineage_event(session, event)

    except Exception as exc:
        if isinstance(exc, ExportLineageError):
            raise
        raise ExportLineageError(
            "Export artifact was created, but export lineage verification "
            "or persistence failed. The export remains on disk.",
            export_result,
        ) from exc

    return {
        "export": export_result,
        "lineage_event": persisted_event,
        "lineage_persisted": True,
        "transaction_committed": False,
    }
