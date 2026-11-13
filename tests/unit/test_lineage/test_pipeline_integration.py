import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.app.lineage.lineage_model import LineageEventModel
from apps.api.app.lineage.lineage_registry import list_lineage_events
from apps.api.app.lineage.pipeline_integration import (
    PIPELINE_STAGE_EVENT_TYPES,
    PipelineLineageError,
    record_pipeline_stage_success,
    track_pipeline_stage,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    LineageEventModel.__table__.create(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def identity():
    return {
        "dataset_id": str(uuid.uuid4()),
        "dataset_version": 1,
        "actor": "datumor-worker",
    }


@pytest.mark.parametrize(
    ("stage", "event_type"),
    list(PIPELINE_STAGE_EVENT_TYPES.items()),
)
def test_every_pipeline_stage_maps_to_contract_event(
    session, identity, stage, event_type
):
    result = record_pipeline_stage_success(
        session,
        stage=stage,
        **identity,
    )
    session.commit()

    assert result["event_type"] == event_type
    assert result["metadata"]["pipeline_stage"] == stage


def test_stage_success_preserves_references_checksum_and_metadata(
    session, identity
):
    checksum = "b" * 64

    result = record_pipeline_stage_success(
        session,
        stage="extraction",
        input_references=["source-001", "source-002"],
        output_checksum_sha256=checksum,
        metadata={"document_count": 2},
        **identity,
    )
    session.commit()

    assert result["input_references"] == [
        "source-001", "source-002"
    ]
    assert result["output_checksum_sha256"] == checksum
    assert result["metadata"]["document_count"] == 2


def test_context_manager_records_event_after_success(
    session, identity
):
    with track_pipeline_stage(
        session,
        stage="understanding",
        **identity,
    ) as execution:
        execution.input_references.append("extraction-output")
        execution.metadata["entity_count"] = 12
        execution.output_checksum_sha256 = "c" * 64

    session.commit()

    events = list_lineage_events(session, identity["dataset_id"])

    assert len(events) == 1
    assert events[0]["event_type"] == "understood"
    assert events[0]["metadata"]["entity_count"] == 12


def test_failed_stage_does_not_record_success_event(
    session, identity
):
    with pytest.raises(RuntimeError, match="processing failed"):
        with track_pipeline_stage(
            session,
            stage="extraction",
            **identity,
        ):
            raise RuntimeError("processing failed")

    session.commit()

    assert list_lineage_events(
        session, identity["dataset_id"]
    ) == []


def test_stage_event_uses_supplied_dataset_version(
    session, identity
):
    identity["dataset_version"] = 4

    result = record_pipeline_stage_success(
        session,
        stage="validation",
        **identity,
    )
    session.commit()

    assert result["dataset_version"] == 4


def test_unknown_stage_is_rejected(session, identity):
    with pytest.raises(PipelineLineageError, match="Unsupported"):
        record_pipeline_stage_success(
            session,
            stage="unknown",
            **identity,
        )


def test_invalid_actor_is_rejected(session, identity):
    identity["actor"] = ""

    with pytest.raises(PipelineLineageError, match="actor"):
        record_pipeline_stage_success(
            session,
            stage="quality",
            **identity,
        )


def test_invalid_input_references_are_rejected(session, identity):
    with pytest.raises(PipelineLineageError, match="strings"):
        record_pipeline_stage_success(
            session,
            stage="quality",
            input_references=["valid", 123],
            **identity,
        )


def test_multiple_successful_stages_preserve_pipeline_order(
    session, identity
):
    stages = [
        "source_ingestion",
        "extraction",
        "understanding",
        "quality",
        "transformation",
        "optimization",
        "validation",
    ]

    for stage in stages:
        record_pipeline_stage_success(
            session,
            stage=stage,
            **identity,
        )

    session.commit()

    events = list_lineage_events(session, identity["dataset_id"])
    ordered_events = sorted(
        events,
        key=lambda event: event["metadata"]["stage_sequence"],
    )

    assert [event["event_type"] for event in ordered_events] == [
        PIPELINE_STAGE_EVENT_TYPES[stage] for stage in stages
    ]
    assert [
        event["metadata"]["stage_sequence"] for event in ordered_events
    ] == list(range(1, 8))
def test_context_manager_does_not_commit_callers_transaction(
    session, identity
):
    record_pipeline_stage_success(
        session,
        stage="extraction",
        **identity,
    )

    assert session.in_transaction()

    session.rollback()

    assert list_lineage_events(
        session, identity["dataset_id"]
    ) == []
