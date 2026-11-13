from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from sqlalchemy.orm import Session

from apps.api.app.lineage.lineage_registry import record_lineage_event


PIPELINE_STAGE_EVENT_TYPES = {
    "source_ingestion": "source_added",
    "extraction": "extracted",
    "understanding": "understood",
    "quality": "quality_checked",
    "transformation": "transformed",
    "optimization": "optimized",
    "validation": "validated",
}

PIPELINE_STAGE_SEQUENCE = {
    "source_ingestion": 1,
    "extraction": 2,
    "understanding": 3,
    "quality": 4,
    "transformation": 5,
    "optimization": 6,
    "validation": 7,
}

SUPPORTED_PIPELINE_STAGES = frozenset(PIPELINE_STAGE_EVENT_TYPES)


class PipelineLineageError(ValueError):
    """Invalid pipeline lineage integration request."""


@dataclass
class PipelineStageExecution:
    """Metadata collected while a pipeline stage is executing."""

    input_references: list[str] = field(default_factory=list)
    output_checksum_sha256: str | None = None
    metadata: dict = field(default_factory=dict)


def record_pipeline_stage_success(
    session: Session,
    *,
    stage: str,
    dataset_id: str,
    dataset_version: int,
    actor: str,
    input_references: list[str] | None = None,
    output_checksum_sha256: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Record a completed pipeline stage in the caller's transaction."""
    if stage not in SUPPORTED_PIPELINE_STAGES:
        raise PipelineLineageError(f"Unsupported pipeline stage: {stage}")

    if not isinstance(actor, str) or not actor.strip():
        raise PipelineLineageError("actor must be a non-empty string.")

    if input_references is None:
        input_references = []

    if (
        not isinstance(input_references, list)
        or any(not isinstance(item, str) for item in input_references)
    ):
        raise PipelineLineageError(
            "input_references must be a list of strings."
        )

    if metadata is None:
        metadata = {}

    if not isinstance(metadata, dict):
        raise PipelineLineageError("metadata must be an object.")

    event = {
        "contract_version": "1.0.0",
        "event_id": str(uuid4()),
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "event_type": PIPELINE_STAGE_EVENT_TYPES[stage],
        "actor": actor.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_references": list(input_references),
        "output_checksum_sha256": output_checksum_sha256,
        "metadata": {
            **metadata,
            "pipeline_stage": stage,
            "stage_sequence": PIPELINE_STAGE_SEQUENCE[stage],
        },
    }

    return record_lineage_event(session, event)


@contextmanager
def track_pipeline_stage(
    session: Session,
    *,
    stage: str,
    dataset_id: str,
    dataset_version: int,
    actor: str,
    input_references: list[str] | None = None,
) -> Iterator[PipelineStageExecution]:
    """Record a success event only after the wrapped operation succeeds."""
    if stage not in SUPPORTED_PIPELINE_STAGES:
        raise PipelineLineageError(f"Unsupported pipeline stage: {stage}")

    execution = PipelineStageExecution(
        input_references=list(input_references or [])
    )

    yield execution

    record_pipeline_stage_success(
        session,
        stage=stage,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        actor=actor,
        input_references=execution.input_references,
        output_checksum_sha256=execution.output_checksum_sha256,
        metadata=execution.metadata,
    )
