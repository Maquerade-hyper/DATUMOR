import json

import pytest

from apps.api.app.versioning.dataset_versioning import (
    DatasetVersionConflict,
    DatasetVersionIntegrityError,
    compare_dataset_versions,
    create_dataset_version,
    list_dataset_versions,
    load_dataset_version,
    verify_dataset_version,
)


def sample_dataset(response="DATUMOR prepares reliable datasets.", extra=False):
    examples = [
        {
            "example_id": "example-001",
            "instruction": "What does DATUMOR prepare?",
            "response": response,
            "provenance": {"source_id": "source-001"},
        }
    ]
    if extra:
        examples.append({
            "example_id": "example-002",
            "instruction": "What is its purpose?",
            "response": "Prepare AI-ready data.",
            "provenance": {"source_id": "source-001"},
        })
    return {
        "report_type": "datumor.generated_dataset",
        "version": "1.0.0",
        "examples": examples,
        "skipped": [],
    }


def test_create_first_dataset_version(tmp_path):
    dataset = sample_dataset()
    result = create_dataset_version(dataset, tmp_path, "dataset-001")

    assert result["created"]
    assert result["version"] == 1
    assert result["parent_version_id"] is None
    assert len(result["content_sha256"]) == 64


def test_load_version_returns_original_snapshot(tmp_path):
    dataset = sample_dataset()
    created = create_dataset_version(dataset, tmp_path, "dataset-001")

    loaded = load_dataset_version(tmp_path, "dataset-001", 1)

    assert loaded["dataset"] == dataset
    assert loaded["metadata"]["version_id"] == created["version_id"]


def test_create_second_version_requires_latest_parent(tmp_path):
    first = create_dataset_version(
        sample_dataset(), tmp_path, "dataset-001"
    )

    with pytest.raises(DatasetVersionConflict, match="parent_version_id"):
        create_dataset_version(
            sample_dataset(extra=True), tmp_path, "dataset-001"
        )

    second = create_dataset_version(
        sample_dataset(extra=True),
        tmp_path,
        "dataset-001",
        parent_version_id=first["version_id"],
    )

    assert second["version"] == 2
    assert second["parent_version_id"] == first["version_id"]


def test_old_version_is_not_overwritten(tmp_path):
    original = sample_dataset()
    first = create_dataset_version(original, tmp_path, "dataset-001")

    updated = sample_dataset(response="Updated response.")
    create_dataset_version(
        updated,
        tmp_path,
        "dataset-001",
        parent_version_id=first["version_id"],
    )

    loaded_first = load_dataset_version(tmp_path, "dataset-001", 1)
    loaded_second = load_dataset_version(tmp_path, "dataset-001", 2)

    assert loaded_first["dataset"] == original
    assert loaded_second["dataset"] == updated


def test_history_is_ordered_and_verified(tmp_path):
    first = create_dataset_version(
        sample_dataset(), tmp_path, "dataset-001"
    )
    create_dataset_version(
        sample_dataset(extra=True),
        tmp_path,
        "dataset-001",
        parent_version_id=first["version_id"],
    )

    history = list_dataset_versions(tmp_path, "dataset-001")

    assert history["version_count"] == 2
    assert history["latest_version"] == 2
    assert [item["version"] for item in history["versions"]] == [1, 2]
    assert all(item["integrity_valid"] for item in history["versions"])


def test_compare_reports_added_examples(tmp_path):
    first = create_dataset_version(
        sample_dataset(), tmp_path, "dataset-001"
    )
    create_dataset_version(
        sample_dataset(extra=True),
        tmp_path,
        "dataset-001",
        parent_version_id=first["version_id"],
    )

    report = compare_dataset_versions(
        tmp_path, "dataset-001", 1, 2
    )

    assert report["summary"]["added"] == 1
    assert report["added_example_ids"] == ["example-002"]
    assert report["summary"]["unchanged"] == 1


def test_compare_reports_changed_and_removed_examples(tmp_path):
    first = create_dataset_version(
        sample_dataset(), tmp_path, "dataset-001"
    )

    changed_dataset = {
        "examples": [{
            "example_id": "example-001",
            "instruction": "Updated question",
            "response": "Updated answer",
            "provenance": {"source_id": "source-001"},
        }]
    }
    create_dataset_version(
        changed_dataset,
        tmp_path,
        "dataset-001",
        parent_version_id=first["version_id"],
    )

    report = compare_dataset_versions(
        tmp_path, "dataset-001", 1, 2
    )

    assert report["summary"]["changed"] == 1
    assert report["summary"]["removed"] == 0


def test_tampered_snapshot_fails_integrity(tmp_path):
    create_dataset_version(
        sample_dataset(), tmp_path, "dataset-001"
    )
    path = tmp_path / "dataset-001" / "versions" / "v000001.json"

    record = json.loads(path.read_text(encoding="utf-8"))
    record["dataset"]["examples"][0]["response"] = "Tampered."
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(
        DatasetVersionIntegrityError,
        match="checksum mismatch",
    ):
        verify_dataset_version(tmp_path, "dataset-001", 1)


def test_missing_version_raises(tmp_path):
    from apps.api.app.versioning.dataset_versioning import (
        DatasetVersionNotFound,
    )

    with pytest.raises(DatasetVersionNotFound):
        load_dataset_version(tmp_path, "dataset-001", 1)


def test_invalid_dataset_id_rejected(tmp_path):
    with pytest.raises(ValueError):
        create_dataset_version(sample_dataset(), tmp_path, "../escape")


def test_dataset_input_is_not_mutated(tmp_path):
    dataset = sample_dataset()
    before = json.dumps(dataset, sort_keys=True)

    create_dataset_version(dataset, tmp_path, "dataset-001")

    assert json.dumps(dataset, sort_keys=True) == before


def test_unknown_parent_is_rejected(tmp_path):
    create_dataset_version(sample_dataset(), tmp_path, "dataset-001")

    with pytest.raises(DatasetVersionConflict, match="Parent version"):
        create_dataset_version(
            sample_dataset(extra=True),
            tmp_path,
            "dataset-001",
            parent_version_id="not-a-real-version",
        )
