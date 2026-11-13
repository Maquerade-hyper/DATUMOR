import hashlib
import json

import pytest

from apps.api.app.exporting import build_export_configuration, export_dataset


@pytest.fixture
def dataset_with_metadata_and_provenance():
    return {
        "report_type": "datumor.generated_dataset",
        "version": "1.0.0",
        "dataset_id": "dataset-001",
        "task_type": "general",
        "source_ids": ["source-001", "source-002"],
        "examples": [
            {
                "example_id": "example-001",
                "instruction": "Question one",
                "response": "Answer one",
                "provenance": {"source_id": "source-001", "page": 2},
            },
            {
                "example_id": "example-002",
                "instruction": "Question two",
                "response": "Answer two",
                "provenance": {"source_id": "source-002", "page": 4},
            },
        ],
    }


@pytest.mark.parametrize("export_format", ["json", "jsonl", "parquet"])
def test_manifest_preserves_metadata_and_provenance(
    tmp_path, dataset_with_metadata_and_provenance, export_format
):
    result = export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration(export_format),
    )

    manifest_path = tmp_path / result["manifest_filename"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = tmp_path / result["filename"]

    assert manifest["manifest_type"] == "datumor.export_manifest"
    assert manifest["dataset_metadata"]["dataset_id"] == "dataset-001"
    assert manifest["dataset_metadata"]["source_ids"] == [
        "source-001", "source-002"
    ]
    assert manifest["example_provenance"] == [
        {
            "example_id": "example-001",
            "provenance": {"source_id": "source-001", "page": 2},
        },
        {
            "example_id": "example-002",
            "provenance": {"source_id": "source-002", "page": 4},
        },
    ]
    assert manifest["artifact"]["sha256"] == hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    assert manifest["artifact"]["size_bytes"] == artifact_path.stat().st_size
    assert result["manifest_integrity_verified"] is True
    assert result["integrity_verified"] is True


def test_jsonl_remains_one_example_per_line(
    tmp_path, dataset_with_metadata_and_provenance
):
    result = export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration("jsonl"),
    )
    lines = (tmp_path / result["filename"]).read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 2
    assert all(isinstance(json.loads(line), dict) for line in lines)
    assert all("provenance" in json.loads(line) for line in lines)


def test_metadata_can_be_excluded(
    tmp_path, dataset_with_metadata_and_provenance
):
    result = export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration("json", include_metadata=False),
    )
    exported = json.loads((tmp_path / result["filename"]).read_text("utf-8"))
    manifest = json.loads(
        (tmp_path / result["manifest_filename"]).read_text("utf-8")
    )

    assert set(exported) == {"examples"}
    assert manifest["dataset_metadata"] == {}
    assert manifest["inclusion"]["metadata"] is False


def test_provenance_can_be_excluded(
    tmp_path, dataset_with_metadata_and_provenance
):
    result = export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration("json", include_provenance=False),
    )
    exported = json.loads((tmp_path / result["filename"]).read_text("utf-8"))
    manifest = json.loads(
        (tmp_path / result["manifest_filename"]).read_text("utf-8")
    )

    assert all("provenance" not in item for item in exported["examples"])
    assert manifest["example_provenance"] == []
    assert manifest["inclusion"]["provenance"] is False


def test_manifest_filename_is_returned(
    tmp_path, dataset_with_metadata_and_provenance
):
    result = export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration("json"),
    )

    assert result["manifest_filename"] == "dataset.json.manifest.json"
    assert (tmp_path / result["manifest_filename"]).is_file()
    assert len(result["manifest_sha256"]) == 64


def test_existing_manifest_is_protected_without_overwrite(
    tmp_path, dataset_with_metadata_and_provenance
):
    manifest_path = tmp_path / "dataset.json.manifest.json"
    manifest_path.write_text("preserve-me", encoding="utf-8")

    from apps.api.app.exporting import DatasetExportError

    with pytest.raises(DatasetExportError, match="manifest already exists"):
        export_dataset(
            dataset_with_metadata_and_provenance,
            tmp_path,
            build_export_configuration("json"),
        )

    assert manifest_path.read_text("utf-8") == "preserve-me"


def test_export_does_not_mutate_source_dataset(
    tmp_path, dataset_with_metadata_and_provenance
):
    import copy

    original = copy.deepcopy(dataset_with_metadata_and_provenance)
    export_dataset(
        dataset_with_metadata_and_provenance,
        tmp_path,
        build_export_configuration("json", include_provenance=False),
    )

    assert dataset_with_metadata_and_provenance == original
