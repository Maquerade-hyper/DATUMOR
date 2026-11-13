import uuid

import pytest

from apps.api.app.lineage.dataset_version_lineage import (
    build_dataset_version_lineage,
    record_dataset_version_lineage,
)


def uid():
    return str(uuid.uuid4())


class RecordingSession:
    def __init__(self):
        self.events = []


def test_records_first_version_without_parent(monkeypatch):
    session = RecordingSession()
    captured = []

    monkeypatch.setattr(
        "apps.api.app.lineage.dataset_version_lineage.record_lineage_event",
        lambda target_session, event: captured.append((target_session, event)),
    )

    event = record_dataset_version_lineage(
        session,
        dataset_id=uid(),
        dataset_version=1,
        version_id=uid(),
        pipeline_run_id=uid(),
        source_ids=[uid()],
        output_checksum_sha256="a" * 64,
    )

    assert event["event_type"] == "transformed"
    assert event["metadata"]["lineage_action"] == "dataset_version_created"
    assert event["metadata"]["parent_version_id"] is None
    assert captured == [(session, event)]


def test_registry_is_called_without_commit(monkeypatch):
    session = RecordingSession()
    captured = []

    def fake_record(target_session, event):
        captured.append((target_session, event))

    monkeypatch.setattr(
        "apps.api.app.lineage.dataset_version_lineage.record_lineage_event",
        fake_record,
    )
    event = record_dataset_version_lineage(
        session,
        dataset_id=uid(),
        dataset_version=1,
        version_id=uid(),
        pipeline_run_id=uid(),
        source_ids=[],
    )
    assert captured == [(session, event)]


def test_records_parent_and_source_references(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "apps.api.app.lineage.dataset_version_lineage.record_lineage_event",
        lambda session, event: captured.append(event),
    )
    dataset_id, parent_id, source_id = uid(), uid(), uid()
    event = record_dataset_version_lineage(
        RecordingSession(),
        dataset_id=dataset_id,
        dataset_version=2,
        version_id=uid(),
        parent_version_id=parent_id,
        pipeline_run_id=uid(),
        source_ids=[source_id],
    )
    assert f"source:{source_id}" in event["input_references"]
    assert f"dataset_version:{parent_id}" in event["input_references"]


@pytest.mark.parametrize("number,parent", [(1, uid()), (2, None), (0, None)])
def test_rejects_invalid_parent_relationship(number, parent, monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.lineage.dataset_version_lineage.record_lineage_event",
        lambda session, event: None,
    )
    with pytest.raises(ValueError):
        record_dataset_version_lineage(
            RecordingSession(),
            dataset_id=uid(),
            dataset_version=number,
            version_id=uid(),
            parent_version_id=parent,
            pipeline_run_id=uid(),
            source_ids=[],
        )


def test_rejects_invalid_ids_and_checksums(monkeypatch):
    monkeypatch.setattr(
        "apps.api.app.lineage.dataset_version_lineage.record_lineage_event",
        lambda session, event: None,
    )
    args = dict(
        dataset_version=1,
        version_id=uid(),
        pipeline_run_id=uid(),
        source_ids=[],
    )
    with pytest.raises(ValueError):
        record_dataset_version_lineage(
            RecordingSession(), dataset_id="bad-id", **args
        )
    with pytest.raises(ValueError):
        record_dataset_version_lineage(
            RecordingSession(),
            dataset_id=uid(),
            output_checksum_sha256="bad",
            **args,
        )


def make_event(dataset_id, number, version_id, parent_id, source_ids=None):
    return {
        "event_id": uid(),
        "dataset_id": dataset_id,
        "dataset_version": number,
        "event_type": "transformed",
        "timestamp": "2026-11-11T10:00:00+00:00",
        "output_checksum_sha256": None,
        "metadata": {
            "lineage_action": "dataset_version_created",
            "version_id": version_id,
            "parent_version_id": parent_id,
            "source_ids": source_ids or [],
            "pipeline_run_id": uid(),
        },
    }


def test_builds_two_version_ancestry():
    dataset_id, first_id, second_id = uid(), uid(), uid()
    events = [
        make_event(dataset_id, 2, second_id, first_id, [uid()]),
        make_event(dataset_id, 1, first_id, None),
    ]
    graph = build_dataset_version_lineage(events, dataset_id)
    assert graph["version_count"] == 2
    assert graph["latest_version"] == 2
    assert graph["versions"][1]["parent_version_id"] == first_id


def test_ignores_other_datasets_and_non_version_events():
    dataset_id = uid()
    other_dataset = uid()
    event = make_event(other_dataset, 1, uid(), None)
    graph = build_dataset_version_lineage([event], dataset_id)
    assert graph["version_count"] == 0
    assert graph["versions"] == []


def test_rejects_broken_ancestry():
    dataset_id = uid()
    events = [
        make_event(dataset_id, 1, uid(), None),
        make_event(dataset_id, 2, uid(), uid()),
    ]
    with pytest.raises(ValueError, match="Broken version ancestry"):
        build_dataset_version_lineage(events, dataset_id)


def test_rejects_duplicate_version_number():
    dataset_id, version_id = uid(), uid()
    events = [
        make_event(dataset_id, 1, version_id, None),
        make_event(dataset_id, 1, uid(), None),
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        build_dataset_version_lineage(events, dataset_id)
