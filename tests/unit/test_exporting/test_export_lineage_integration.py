import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.app.database import Base
from apps.api.app.exporting.export_lineage_integration import (
    ExportLineageError,
    export_dataset_with_lineage,
)
from apps.api.app.lineage.lineage_registry import list_lineage_events


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def uid():
    return str(uuid.uuid4())


def make_export(tmp_path, session, **overrides):
    dataset_id = overrides.pop("dataset_id", uid())
    version_id = overrides.pop("version_id", uid())
    source_id = uid()
    pipeline_run_id = uid()

    args = {
        "dataset": {
            "dataset_id": dataset_id,
            "examples": [
                {
                    "example_id": "example-1",
                    "text": "lineage export test",
                    "provenance": {"source_id": source_id},
                }
            ],
        },
        "output_dir": tmp_path,
        "configuration": {
            "format": "jsonl",
            "filename": f"export-{uuid.uuid4().hex}.jsonl",
        },
        "session": session,
        "dataset_id": dataset_id,
        "dataset_version": 1,
        "version_id": version_id,
        "pipeline_run_id": pipeline_run_id,
        "source_ids": [source_id],
        "actor": "export-test",
    }
    args.update(overrides)
    return args, source_id, pipeline_run_id


def test_successful_export_records_verified_lineage(tmp_path, db_session):
    args, source_id, pipeline_run_id = make_export(tmp_path, db_session)

    result = export_dataset_with_lineage(**args)

    assert result["lineage_persisted"] is True
    assert result["transaction_committed"] is False

    export = result["export"]
    event = result["lineage_event"]

    assert event["event_type"] == "exported"
    assert event["dataset_id"] == args["dataset_id"]
    assert event["dataset_version"] == 1
    assert event["output_checksum_sha256"] == export["content_sha256"]
    assert event["metadata"]["manifest_sha256"] == export["manifest_sha256"]
    assert event["metadata"]["pipeline_run_id"] == pipeline_run_id
    assert event["metadata"]["version_id"] == args["version_id"]
    assert event["metadata"]["source_ids"] == [source_id]
    assert event["metadata"]["integrity_verified"] is True
    assert event["metadata"]["manifest_integrity_verified"] is True

    assert f"dataset_version:{args['version_id']}" in event["input_references"]
    assert f"source:{source_id}" in event["input_references"]

    events = list_lineage_events(db_session, args["dataset_id"])
    assert len(events) == 1
    assert events[0]["event_id"] == event["event_id"]


def test_export_manifest_and_artifact_checksums_match(tmp_path, db_session):
    args, _, _ = make_export(tmp_path, db_session)

    result = export_dataset_with_lineage(**args)
    with open(result["export"]["manifest_path"], encoding="utf-8") as handle:
        manifest = json.load(handle)

    assert manifest["artifact"]["sha256"] == result["export"]["content_sha256"]
    assert result["lineage_event"]["metadata"]["manifest_sha256"] == (
        result["export"]["manifest_sha256"]
    )


def test_failed_export_does_not_create_lineage_event(tmp_path, db_session):
    args, _, _ = make_export(tmp_path, db_session)
    args["configuration"] = {"format": "unsupported"}

    with pytest.raises(ValueError):
        export_dataset_with_lineage(**args)

    assert list_lineage_events(db_session, args["dataset_id"]) == []


def test_manifest_corruption_prevents_success_event(
    tmp_path, db_session, monkeypatch
):
    from apps.api.app.exporting import export_lineage_integration as integration

    original_verify = integration._verify_export_result

    def corrupted_verify(result):
        manifest_path = result["manifest_path"]
        with open(manifest_path, "ab") as handle:
            handle.write(b" ")
        return original_verify(result)

    monkeypatch.setattr(
        integration, "_verify_export_result", corrupted_verify
    )

    args, _, _ = make_export(tmp_path, db_session)

    with pytest.raises(ExportLineageError):
        export_dataset_with_lineage(**args)

    assert list_lineage_events(db_session, args["dataset_id"]) == []


def test_lineage_persistence_failure_exposes_export(
    tmp_path, db_session, monkeypatch
):
    from apps.api.app.exporting import export_lineage_integration as integration

    def fail_record(session, event):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(integration, "record_lineage_event", fail_record)

    args, _, _ = make_export(tmp_path, db_session)

    with pytest.raises(ExportLineageError) as caught:
        export_dataset_with_lineage(**args)

    assert caught.value.export_result["success"] is True
    assert caught.value.export_result["manifest_integrity_verified"] is True
