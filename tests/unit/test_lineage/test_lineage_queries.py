import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.app.database import Base
from apps.api.app.exporting.export_lineage_integration import (
    export_dataset_with_lineage,
)
from apps.api.app.lineage.lineage_queries import (
    LineageQueryError,
    build_lineage_report,
    get_complete_dataset_lineage,
    query_dataset_lineage,
    query_export_lineage,
    query_source_lineage,
    render_lineage_markdown,
    write_lineage_report,
)
from apps.api.app.lineage.pipeline_integration import (
    record_pipeline_stage_success,
)
from apps.api.app.versioning.dataset_version_lineage_integration import (
    create_dataset_version_with_lineage,
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


def test_dataset_lineage_query_filters_and_paginates(db_session):
    dataset_id = uid()
    identity = {
        "dataset_id": dataset_id,
        "dataset_version": 1,
        "actor": "lineage-query-test",
    }

    record_pipeline_stage_success(
        db_session,
        stage="source_ingestion",
        **identity,
    )
    record_pipeline_stage_success(
        db_session,
        stage="extraction",
        **identity,
    )
    db_session.commit()

    first_page = query_dataset_lineage(
        db_session, dataset_id, limit=1, offset=0
    )
    second_page = query_dataset_lineage(
        db_session, dataset_id, limit=1, offset=1
    )
    extraction = query_dataset_lineage(
        db_session, dataset_id, event_type="extracted"
    )

    assert first_page["pagination"]["returned"] == 1
    assert second_page["pagination"]["returned"] == 1
    assert extraction["events"][0]["event_type"] == "extracted"


def test_source_query_finds_source_references(db_session):
    dataset_id = uid()
    source_id = uid()

    record_pipeline_stage_success(
        db_session,
        stage="extraction",
        dataset_id=dataset_id,
        dataset_version=1,
        actor="source-query-test",
        input_references=[f"source:{source_id}"],
    )
    db_session.commit()

    result = query_source_lineage(
        db_session, dataset_id, source_id
    )
    assert result["event_count"] == 1
    assert result["dataset_versions"] == [1]


def test_complete_lineage_reconstructs_version_graph(
    tmp_path, db_session
):
    dataset_id = uid()
    source_id = uid()
    pipeline_run_id = uid()

    result = create_dataset_version_with_lineage(
        dataset={"examples": [{"example_id": "graph-1", "text": "one"}]},
        storage_dir=tmp_path,
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=pipeline_run_id,
        source_ids=[source_id],
    )
    db_session.commit()

    lineage = get_complete_dataset_lineage(
        db_session, dataset_id
    )

    assert lineage["event_count"] == 1
    assert lineage["version_graph"]["version_count"] == 1
    assert lineage["version_graph"]["versions"][0]["version_id"] == (
        result["version"]["version_id"]
    )


def test_export_query_returns_artifact_and_manifest(
    tmp_path, db_session
):
    dataset_id = uid()
    version_id = uid()

    export_dataset_with_lineage(
        dataset={
            "examples": [{"example_id": "export-1", "text": "export"}]
        },
        output_dir=tmp_path,
        configuration={
            "format": "jsonl",
            "filename": "query-export.jsonl",
        },
        session=db_session,
        dataset_id=dataset_id,
        dataset_version=1,
        version_id=version_id,
        pipeline_run_id=uid(),
        source_ids=[],
    )
    db_session.commit()

    result = query_export_lineage(db_session, dataset_id)

    assert result["export_count"] == 1
    export = result["exports"][0]
    assert export["version_id"] == version_id
    assert export["artifact_sha256"]
    assert export["manifest_sha256"]
    assert export["integrity_verified"] is True


def test_report_json_markdown_and_file_outputs(
    tmp_path, db_session
):
    dataset_id = uid()

    record_pipeline_stage_success(
        db_session,
        stage="source_ingestion",
        dataset_id=dataset_id,
        dataset_version=1,
        actor="report-test",
    )
    db_session.commit()

    report = build_lineage_report(db_session, dataset_id)
    markdown = render_lineage_markdown(report)
    paths = write_lineage_report(report, tmp_path)

    assert report["report_type"] == "datumor.dataset_lineage_report"
    assert report["summary"]["total_events"] == 1
    assert "DATUMOR Dataset Lineage Report" in markdown

    with open(paths["json_path"], encoding="utf-8") as handle:
        persisted = json.load(handle)

    assert persisted["dataset_id"] == dataset_id

    with open(paths["markdown_path"], encoding="utf-8") as handle:
        persisted_markdown = handle.read()

    assert persisted_markdown == markdown + "\n"


def test_invalid_dataset_and_source_ids_are_rejected(db_session):
    with pytest.raises(LineageQueryError):
        query_dataset_lineage(db_session, "not-a-uuid")

    with pytest.raises(LineageQueryError):
        query_source_lineage(db_session, uid(), "not-a-uuid")


def test_full_version_to_export_lineage_workflow(
    tmp_path, db_session
):
    dataset_id = uid()
    source_id = uid()
    pipeline_run_id = uid()

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
            db_session,
            stage=stage,
            dataset_id=dataset_id,
            dataset_version=1,
            actor="end-to-end-test",
            input_references=[f"source:{source_id}"],
        )

    dataset = {
        "dataset_id": dataset_id,
        "examples": [
            {
                "example_id": "e2e-1",
                "text": "DATUMOR end-to-end lineage verification",
                "provenance": {"source_id": source_id},
            }
        ],
    }

    version_result = create_dataset_version_with_lineage(
        dataset=dataset,
        storage_dir=tmp_path / "versions",
        dataset_id=dataset_id,
        session=db_session,
        pipeline_run_id=pipeline_run_id,
        source_ids=[source_id],
        actor="end-to-end-test",
    )

    version = version_result["version"]

    export_result = export_dataset_with_lineage(
        dataset=dataset,
        output_dir=tmp_path / "exports",
        configuration={
            "format": "jsonl",
            "filename": "e2e-dataset.jsonl",
        },
        session=db_session,
        dataset_id=dataset_id,
        dataset_version=version["version_number"],
        version_id=version["version_id"],
        pipeline_run_id=pipeline_run_id,
        source_ids=[source_id],
        actor="end-to-end-test",
    )

    db_session.commit()

    complete = get_complete_dataset_lineage(
        db_session, dataset_id
    )
    source_history = query_source_lineage(
        db_session, dataset_id, source_id
    )
    export_history = query_export_lineage(
        db_session, dataset_id
    )
    report = build_lineage_report(db_session, dataset_id)

    assert complete["version_graph"]["version_count"] == 1
    assert complete["event_counts"]["source_added"] == 1
    assert complete["event_counts"]["extracted"] == 1
    assert complete["event_counts"]["understood"] == 1
    assert complete["event_counts"]["quality_checked"] == 1
    assert complete["event_counts"]["transformed"] == 2
    assert complete["event_counts"]["optimized"] == 1
    assert complete["event_counts"]["validated"] == 1
    assert complete["event_counts"]["exported"] == 1

    assert source_history["event_count"] >= 2
    assert export_history["export_count"] == 1
    assert export_result["lineage_persisted"] is True
    assert report["summary"]["total_events"] == 9
    assert report["summary"]["verified_exports"] == 1
    assert (
        export_history["exports"][0]["artifact_sha256"]
        == export_result["export"]["content_sha256"]
    )
