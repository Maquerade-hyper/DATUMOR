import copy
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.app.lineage import (
    DuplicateLineageEventError,
    LineageEventModel,
    LineageValidationError,
    get_lineage_event,
    list_lineage_events,
    record_lineage_event,
    validate_lineage_event,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    LineageEventModel.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def event():
    return {
        "contract_version": "1.0.0",
        "event_id": str(uuid.uuid4()),
        "dataset_id": str(uuid.uuid4()),
        "dataset_version": 1,
        "event_type": "source_added",
        "actor": "datumor-system",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_references": ["source-001"],
        "output_checksum_sha256": "a" * 64,
        "metadata": {"source_type": "file"},
    }


def test_valid_event_passes_contract_validation(event):
    normalized = validate_lineage_event(event)
    assert normalized["event_id"] == event["event_id"]
    assert normalized["dataset_id"] == event["dataset_id"]


def test_event_is_persisted_and_retrievable(session, event):
    result = record_lineage_event(session, event)
    session.commit()

    loaded = get_lineage_event(session, event["event_id"])

    assert result["event_id"] == event["event_id"]
    assert loaded["dataset_id"] == event["dataset_id"]
    assert loaded["event_type"] == "source_added"
    assert loaded["metadata"] == {"source_type": "file"}


def test_identical_event_submission_is_idempotent(session, event):
    first = record_lineage_event(session, event)
    session.commit()

    second = record_lineage_event(session, event)

    assert first["event_id"] == second["event_id"]
    assert len(list_lineage_events(session, event["dataset_id"])) == 1


def test_event_id_reuse_with_different_content_is_rejected(session, event):
    record_lineage_event(session, event)
    session.commit()

    changed = copy.deepcopy(event)
    changed["actor"] = "different-actor"

    with pytest.raises(DuplicateLineageEventError):
        record_lineage_event(session, changed)


def test_missing_required_field_is_rejected(event):
    event.pop("actor")

    with pytest.raises(LineageValidationError, match="Missing required"):
        validate_lineage_event(event)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "2.0.0"),
        ("event_type", "unknown"),
        ("dataset_version", 0),
        ("dataset_version", True),
        ("actor", ""),
        ("input_references", "not-a-list"),
        ("output_checksum_sha256", "invalid"),
        ("metadata", []),
        ("event_id", "not-a-uuid"),
    ],
)
def test_invalid_contract_values_are_rejected(event, field, value):
    event[field] = value

    with pytest.raises(LineageValidationError):
        validate_lineage_event(event)


def test_timezone_is_normalized_to_utc(event):
    event["timestamp"] = "2026-11-11T12:00:00+05:30"

    normalized = validate_lineage_event(event)

    assert normalized["timestamp"].utcoffset().total_seconds() == 0


def test_naive_timestamp_is_rejected(event):
    event["timestamp"] = "2026-11-11T12:00:00"

    with pytest.raises(LineageValidationError, match="timezone"):
        validate_lineage_event(event)


def test_nan_metadata_is_rejected(event):
    event["metadata"] = {"score": float("nan")}

    with pytest.raises(LineageValidationError, match="strict JSON"):
        validate_lineage_event(event)


def test_event_filters_work(session, event):
    record_lineage_event(session, event)
    session.commit()

    second_event = {
        **event,
        "event_id": str(uuid.uuid4()),
        "event_type": "extracted",
        "dataset_version": 2,
    }
    record_lineage_event(session, second_event)
    session.commit()

    all_events = list_lineage_events(session, event["dataset_id"])
    version_two = list_lineage_events(
        session, event["dataset_id"], dataset_version=2
    )
    extracted = list_lineage_events(
        session, event["dataset_id"], event_type="extracted"
    )

    assert len(all_events) == 2
    assert len(version_two) == 1
    assert version_two[0]["event_id"] == second_event["event_id"]
    assert len(extracted) == 1


def test_pagination_works(session, event):
    for _ in range(3):
        record_lineage_event(
            session,
            {
                **event,
                "event_id": str(uuid.uuid4()),
            },
        )
    session.commit()

    page = list_lineage_events(
        session, event["dataset_id"], limit=2, offset=1
    )

    assert len(page) == 2


def test_missing_event_returns_none(session, event):
    assert get_lineage_event(session, event["event_id"]) is None


def test_invalid_query_parameters_are_rejected(session, event):
    with pytest.raises(LineageValidationError):
        list_lineage_events(session, event["dataset_id"], limit=0)

    with pytest.raises(LineageValidationError):
        list_lineage_events(session, event["dataset_id"], offset=-1)
