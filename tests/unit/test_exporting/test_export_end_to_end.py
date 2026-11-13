import hashlib
import json

import pytest

from apps.api.app.exporting import build_export_configuration, export_dataset


@pytest.fixture
def end_to_end_dataset():
    return {
        "report_type": "datumor.generated_dataset",
        "version": "1.0.0",
        "dataset_id": "e2e-dataset-001",
        "task_type": "general",
        "source_ids": ["source-001", "source-002"],
        "examples": [
            {
                "example_id": "e2e-001",
                "instruction": "Define data intelligence.",
                "response": "Structured preparation of raw data.",
                "provenance": {"source_id": "source-001"},
            },
            {
                "example_id": "e2e-002",
                "instruction": "Define dataset export.",
                "response": "Delivery of prepared data.",
                "provenance": {"source_id": "source-002"},
            },
        ],
    }


@pytest.mark.parametrize("export_format", ["json", "jsonl", "parquet"])
def test_complete_export_workflow(
    tmp_path, end_to_end_dataset, export_format
):
    result = export_dataset(
        end_to_end_dataset,
        tmp_path,
        build_export_configuration(export_format),
    )

    artifact = tmp_path / result["filename"]
    manifest_path = tmp_path / result["manifest_filename"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    assert result["success"] is True
    assert result["format"] == export_format
    assert result["example_count"] == 2
    assert result["size_bytes"] == artifact.stat().st_size
    assert result["content_sha256"] == artifact_hash
    assert result["integrity_verified"] is True
    assert result["atomic_write"] is True
    assert result["manifest_sha256"] == manifest_hash
    assert result["manifest_integrity_verified"] is True

    assert manifest["artifact"]["sha256"] == artifact_hash
    assert manifest["artifact"]["example_count"] == 2
    assert manifest["dataset_metadata"]["dataset_id"] == "e2e-dataset-001"
    assert len(manifest["example_provenance"]) == 2

    if export_format == "json":
        exported = json.loads(artifact.read_text(encoding="utf-8"))
        assert len(exported["examples"]) == 2
        assert exported["examples"][0]["provenance"]["source_id"] == "source-001"

    elif export_format == "jsonl":
        lines = artifact.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert all(isinstance(json.loads(line), dict) for line in lines)
        assert json.loads(lines[0])["example_id"] == "e2e-001"

    else:
        import pyarrow.parquet as pq

        table = pq.read_table(artifact)
        assert table.num_rows == 2
        assert table.column("example_id").to_pylist() == [
            "e2e-001", "e2e-002"
        ]


def test_overwrite_replaces_artifact_and_manifest(
    tmp_path, end_to_end_dataset
):
    first = export_dataset(
        end_to_end_dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    changed = {
        **end_to_end_dataset,
        "version": "2.0.0",
    }

    second = export_dataset(
        changed,
        tmp_path,
        build_export_configuration("json", overwrite=True),
    )

    manifest = json.loads(
        (tmp_path / second["manifest_filename"]).read_text("utf-8")
    )
    artifact = tmp_path / second["filename"]

    assert first["content_sha256"] != second["content_sha256"]
    assert manifest["dataset_metadata"]["version"] == "2.0.0"
    assert manifest["artifact"]["sha256"] == hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()


def test_successful_export_leaves_no_temporary_files(
    tmp_path, end_to_end_dataset
):
    export_dataset(
        end_to_end_dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))


def test_empty_dataset_end_to_end(tmp_path):
    result = export_dataset(
        {
            "report_type": "datumor.generated_dataset",
            "examples": [],
        },
        tmp_path,
        build_export_configuration("jsonl"),
    )

    manifest = json.loads(
        (tmp_path / result["manifest_filename"]).read_text("utf-8")
    )

    assert result["example_count"] == 0
    assert (tmp_path / result["filename"]).read_bytes() == b""
    assert manifest["artifact"]["example_count"] == 0
    assert manifest["example_provenance"] == []
