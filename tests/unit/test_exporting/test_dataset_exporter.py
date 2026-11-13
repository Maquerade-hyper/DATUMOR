import json

import pytest

from apps.api.app.exporting import (
    DatasetExportError,
    build_export_configuration,
    export_dataset,
)


@pytest.fixture
def dataset():
    return {
        "report_type": "datumor.generated_dataset",
        "version": "1.0.0",
        "examples": [
            {
                "example_id": "example-001",
                "instruction": "What does DATUMOR prepare?",
                "response": "AI-ready data.",
                "provenance": {"source_id": "source-001"},
            },
            {
                "example_id": "example-002",
                "instruction": "What is dataset export?",
                "response": "Serialization of a dataset.",
                "provenance": {"source_id": "source-002"},
            },
        ],
    }


def test_json_export_creates_complete_dataset(tmp_path, dataset):
    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    output = json.loads((tmp_path / "dataset.json").read_text("utf-8"))

    assert result["success"] is True
    assert result["format"] == "json"
    assert result["example_count"] == 2
    assert output == dataset


def test_jsonl_export_creates_one_example_per_line(tmp_path, dataset):
    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("jsonl"),
    )

    lines = (tmp_path / "dataset.jsonl").read_text("utf-8").splitlines()

    assert result["example_count"] == 2
    assert len(lines) == 2
    assert json.loads(lines[0]) == dataset["examples"][0]
    assert json.loads(lines[1]) == dataset["examples"][1]


def test_parquet_export_creates_readable_file(tmp_path, dataset):
    import pyarrow.parquet as pq

    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("parquet"),
    )

    table = pq.read_table(tmp_path / "dataset.parquet")

    assert result["format"] == "parquet"
    assert result["example_count"] == 2
    assert table.num_rows == 2
    assert table.column("example_id").to_pylist() == [
        "example-001",
        "example-002",
    ]


def test_empty_jsonl_export(tmp_path):
    result = export_dataset(
        {"examples": []},
        tmp_path,
        build_export_configuration("jsonl"),
    )

    assert result["example_count"] == 0
    assert (tmp_path / "dataset.jsonl").read_bytes() == b""


def test_empty_parquet_export(tmp_path):
    import pyarrow.parquet as pq

    result = export_dataset(
        {"examples": []},
        tmp_path,
        build_export_configuration("parquet"),
    )

    table = pq.read_table(tmp_path / "dataset.parquet")

    assert result["example_count"] == 0
    assert table.num_rows == 0


def test_existing_export_rejected_by_default(tmp_path, dataset):
    config = build_export_configuration("json")
    (tmp_path / "dataset.json").write_text("existing", encoding="utf-8")

    with pytest.raises(DatasetExportError, match="already exists"):
        export_dataset(dataset, tmp_path, config)


def test_existing_export_can_be_overwritten(tmp_path, dataset):
    config = build_export_configuration("json", overwrite=True)
    (tmp_path / "dataset.json").write_text("existing", encoding="utf-8")

    result = export_dataset(dataset, tmp_path, config)

    assert result["success"] is True
    assert json.loads(
        (tmp_path / "dataset.json").read_text("utf-8")
    ) == dataset


def test_export_does_not_mutate_dataset(tmp_path, dataset):
    import copy

    original = copy.deepcopy(dataset)

    export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    assert dataset == original


def test_non_dictionary_dataset_rejected(tmp_path):
    with pytest.raises(DatasetExportError, match="dictionary"):
        export_dataset(
            [],
            tmp_path,
            build_export_configuration("json"),
        )


def test_invalid_example_rejected(tmp_path):
    with pytest.raises(DatasetExportError, match="object"):
        export_dataset(
            {"examples": ["not-an-object"]},
            tmp_path,
            build_export_configuration("json"),
        )


def test_json_rejects_non_finite_numbers(tmp_path):
    with pytest.raises(DatasetExportError, match="JSON"):
        export_dataset(
            {"value": float("nan")},
            tmp_path,
            build_export_configuration("json"),
        )


def test_jsonl_requires_examples_list(tmp_path):
    with pytest.raises(DatasetExportError, match="examples list"):
        export_dataset(
            {"metadata": {}},
            tmp_path,
            build_export_configuration("jsonl"),
        )


def test_parquet_requires_examples_list(tmp_path):
    with pytest.raises(DatasetExportError, match="examples list"):
        export_dataset(
            {"metadata": {}},
            tmp_path,
            build_export_configuration("parquet"),
        )


def test_export_result_contains_file_information(tmp_path, dataset):
    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    assert result["filename"] == "dataset.json"
    assert result["path"]
    assert result["size_bytes"] > 0
