import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.app.database import Base
from apps.api.app.lineage.lineage_registry import list_lineage_events
from apps.api.app.versioning.dataset_version_lineage_integration import (
    create_dataset_version_with_lineage,
)
from apps.api.app.versioning.dataset_versioning import (
    load_dataset_version,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def uid():
    return str(uuid.uuid4())


def test_real_version_creation_persists_lineage(
    tmp_path, db_session
):
    dataset_id = uid()
    source_id = uid()
    pipeline_run_id = uid()

    result = create_dataset_version_with_lineage(
        dataset={
            "dataset_id": dataset_id,
            "examples": [{"example_id": "ex-1", "text": "hello"}],
        },
        storage_dir=tmp_path,
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=pipeline_run_id,
        source_ids=[source_id],
        metadata={"profile": "general_llm"},
    )

    assert result["lineage_persisted"] is True
    assert result["transaction_committed"] is False

    version = result["version"]
    assert version["version_number"] == 1

    events = list_lineage_events(db_session, dataset_id)
    assert len(events) == 1

    event = events[0]
    assert event["event_type"] == "transformed"
    assert event["dataset_version"] == 1
    assert event["output_checksum_sha256"] == version["dataset_sha256"]
    assert event["metadata"]["version_id"] == version["version_id"]
    assert event["metadata"]["pipeline_run_id"] == pipeline_run_id
    assert event["metadata"]["source_ids"] == [source_id]
    assert f"source:{source_id}" in event["input_references"]


def test_second_version_links_to_first_version(
    tmp_path, db_session
):
    dataset_id = uid()
    pipeline_run_id = uid()

    first = create_dataset_version_with_lineage(
        dataset={"examples": [{"example_id": "one"}]},
        storage_dir=tmp_path,
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=pipeline_run_id,
        source_ids=[],
    )
    db_session.commit()

    first_id = first["version"]["version_id"]

    create_dataset_version_with_lineage(
        dataset={"examples": [{"example_id": "one"}, {"example_id": "two"}]},
        storage_dir=tmp_path,
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=pipeline_run_id,
        source_ids=[],
        parent_version_id=first_id,
    )
    db_session.commit()

    events = list_lineage_events(db_session, dataset_id)
    assert len(events) == 2

    second_event = next(
        event for event in events if event["dataset_version"] == 2
    )
    assert second_event["metadata"]["parent_version_id"] == first_id


def test_snapshot_remains_loadable_after_lineage_commit(
    tmp_path, db_session
):
    dataset_id = uid()

    result = create_dataset_version_with_lineage(
        dataset={"examples": [{"example_id": "persisted"}]},
        storage_dir=tmp_path,
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=uid(),
        source_ids=[],
    )
    db_session.commit()

    loaded = load_dataset_version(
        tmp_path,
        dataset_id,
        result["version"]["version_number"],
    )
    assert loaded["version_id"] == result["version"]["version_id"]


def test_lineage_failure_exposes_created_snapshot(
    tmp_path, db_session, monkeypatch
):
    from apps.api.app.versioning import dataset_version_lineage_integration as integration

    def fail_record(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(
        integration,
        "record_dataset_version_lineage",
        fail_record,
    )

    from apps.api.app.versioning.dataset_version_lineage_integration import (
        DatasetVersionLineageError,
    )

    dataset_id = uid()

    with pytest.raises(DatasetVersionLineageError) as caught:
        create_dataset_version_with_lineage(
            dataset={"examples": [{"example_id": "orphan"}]},
            storage_dir=tmp_path,
            dataset_id=dataset_id,
            session=db_session,
            pipeline_run_id=uid(),
            source_ids=[],
        )

    assert caught.value.version_id
    assert caught.value.version_number == 1

    loaded = load_dataset_version(
        tmp_path,
        dataset_id,
        caught.value.version_number,
    )
    assert loaded["version_id"] == caught.value.version_id
