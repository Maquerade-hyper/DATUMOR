import json

import pyarrow.parquet as pq
import pytest

from apps.api.app.transformation.profile_registry import get_profile
from apps.api.app.transformation.dataset_serializer import serialize_dataset


def sample_dataset():
    return {
        "report_type": "datumor.generated_dataset",
        "version": "1.0.0",
        "profile": {
            "profile_id": "general_llm",
            "profile_version": "1.0.0",
        },
        "summary": {"examples_generated": 1},
        "examples": [{
            "example_id": "example-1",
            "task_type": "explicit_instruction_response",
            "instruction": "Explain Python.",
            "response": "Python is a programming language.",
            "provenance": {
                "source_id": "source-1",
                "evidence_text": "Python is a programming language.",
            },
        }],
        "skipped": [],
    }


def test_jsonl_serialization(tmp_path):
    path = tmp_path / "dataset.jsonl"
    report = serialize_dataset(
        sample_dataset(), get_profile("general_llm"), path, "jsonl"
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["example_id"] == "example-1"
    assert report["integrity"]["sha256_verified"] is True


def test_json_serialization(tmp_path):
    path = tmp_path / "dataset.json"
    report = serialize_dataset(
        sample_dataset(), get_profile("general_llm"), path, "json"
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema"] == "datumor.training_dataset"
    assert len(payload["examples"]) == 1
    assert report["output"]["format"] == "json"


def test_parquet_serialization(tmp_path):
    path = tmp_path / "dataset.parquet"
    report = serialize_dataset(
        sample_dataset(), get_profile("general_llm"), path, "parquet"
    )

    table = pq.read_table(path)
    rows = table.to_pylist()

    assert len(rows) == 1
    assert rows[0]["example_id"] == "example-1"
    assert "source-1" in rows[0]["provenance_json"]
    assert report["integrity"]["file_exists"] is True


def test_empty_dataset_can_be_serialized(tmp_path):
    dataset = sample_dataset()
    dataset["examples"] = []

    path = tmp_path / "empty.parquet"
    report = serialize_dataset(
        dataset, get_profile("general_llm"), path, "parquet"
    )

    assert pq.read_table(path).num_rows == 0
    assert report["summary"]["examples_serialized"] == 0


def test_profile_mismatch_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="profile"):
        serialize_dataset(
            sample_dataset(),
            get_profile("coding"),
            tmp_path / "dataset.json",
            "json",
        )


def test_missing_required_fields_are_rejected(tmp_path):
    dataset = sample_dataset()
    dataset["examples"][0].pop("instruction")

    with pytest.raises(ValueError, match="required fields"):
        serialize_dataset(
            dataset, get_profile("general_llm"),
            tmp_path / "dataset.json", "json"
        )


def test_missing_provenance_is_rejected(tmp_path):
    dataset = sample_dataset()
    dataset["examples"][0]["provenance"] = {}

    with pytest.raises(ValueError, match="source_id"):
        serialize_dataset(
            dataset, get_profile("general_llm"),
            tmp_path / "dataset.json", "json"
        )


def test_wrong_extension_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        serialize_dataset(
            sample_dataset(), get_profile("general_llm"),
            tmp_path / "dataset.txt", "json"
        )


def test_unsupported_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        serialize_dataset(
            sample_dataset(), get_profile("general_llm"),
            tmp_path / "dataset.csv", "csv"
        )


def test_input_dataset_is_not_modified(tmp_path):
    import copy

    dataset = sample_dataset()
    original = copy.deepcopy(dataset)

    serialize_dataset(
        dataset, get_profile("general_llm"),
        tmp_path / "dataset.jsonl", "jsonl"
    )

    assert dataset == original


def test_parquet_preserves_additional_fields(tmp_path):
    dataset = sample_dataset()
    dataset["examples"][0]["custom_annotation"] = "Documented annotation."

    path = tmp_path / "dataset.parquet"
    serialize_dataset(
        dataset, get_profile("general_llm"), path, "parquet"
    )

    row = pq.read_table(path).to_pylist()[0]
    assert "Documented annotation." in row["additional_fields_json"]


def test_parquet_preserves_evidence_column(tmp_path):
    dataset = sample_dataset()
    dataset["examples"][0]["evidence"] = "Documented evidence."

    path = tmp_path / "dataset.parquet"
    serialize_dataset(
        dataset, get_profile("general_llm"), path, "parquet"
    )

    row = pq.read_table(path).to_pylist()[0]
    assert row["evidence"] == "Documented evidence."


def test_jsonl_preserves_unicode(tmp_path):
    dataset = sample_dataset()
    dataset["examples"][0]["response"] = "Caf? ??"

    path = tmp_path / "dataset.jsonl"
    serialize_dataset(
        dataset, get_profile("general_llm"), path, "jsonl"
    )

    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["response"] == "Caf? ??"
