"""M8.1 schema and artifact validation tests."""

import json

import pytest

from apps.api.app.validation.schema_validation import (
    EXPECTED_SCHEMAS,
    strict_json_loads,
    validate_contract_schemas,
    validate_schema_instance,
    validate_dukr_document,
    validate_multimodal_document,
    validate_generated_dataset,
)


def test_all_eight_contract_schemas_are_valid():
    report = validate_contract_schemas()
    assert report["valid"], report
    assert report["schema_count"] == 8
    assert set(report["validated_schemas"]) == set(EXPECTED_SCHEMAS)


def test_source_schema_accepts_valid_source():
    from uuid import uuid4
    from datetime import datetime, timezone

    source = {
        "contract_version": "1.0.0",
        "source_id": str(uuid4()),
        "project_id": str(uuid4()),
        "source_type": "file",
        "source_name": "sample.txt",
        "media_type": "text/plain",
        "checksum_sha256": "a" * 64,
        "uri": "sources/file/sample.txt",
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    report = validate_schema_instance("source.schema.json", source)
    assert report["valid"], report


def test_source_schema_rejects_invalid_checksum():
    source = {
        "source_id": "not-a-uuid",
        "project_id": None,
        "source_type": "invalid",
        "source_name": "",
        "media_type": None,
        "checksum_sha256": "bad",
        "uri": None,
        "metadata": {},
        "created_at": "not-a-date",
    }
    report = validate_schema_instance("source.schema.json", source)
    assert not report["valid"]
    assert report["error_count"] > 0
    assert all(
        {"code", "path", "message", "severity"} <= set(error)
        for error in report["errors"]
    )


def test_unknown_schema_is_rejected():
    report = validate_schema_instance("unknown.schema.json", {})
    assert not report["valid"]
    assert report["errors"][0]["code"] == "SCHEMA_UNAVAILABLE"


def test_strict_json_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        strict_json_loads('{"value":1,"value":2}')


def test_strict_json_rejects_nan():
    with pytest.raises(ValueError, match="Non-standard JSON"):
        strict_json_loads('{"value":NaN}')


def test_dukr_rejects_non_object():
    report = validate_dukr_document([])
    assert not report["valid"]
    assert report["errors"][0]["code"] == "DUKR_TYPE_INVALID"


def test_dukr_validation_does_not_mutate_input():
    document = {
        "source": {
            "source_id": "source-1",
            "checksum_sha256": "a" * 64,
            "original_content": "",
        },
        "entities": [],
        "relationships": [],
        "context": {"context_units": []},
        "knowledge_graph": {"nodes": [], "edges": []},
    }
    original = json.dumps(document, sort_keys=True)
    validate_dukr_document(document)
    assert json.dumps(document, sort_keys=True) == original


def test_multimodal_rejects_non_object():
    report = validate_multimodal_document([])
    assert not report["valid"]
    assert report["errors"][0]["code"] == "MULTIMODAL_TYPE_INVALID"


def test_dataset_rejects_non_object():
    report = validate_generated_dataset([], {})
    assert not report["valid"]
    assert report["errors"][0]["code"] == "DATASET_TYPE_INVALID"


def test_dataset_validation_does_not_mutate_input():
    profile = {
        "profile_id": "general_llm",
        "version": "1.0.0",
        "required_fields": [
            "example_id", "task_type", "instruction", "response", "provenance"
        ],
        "preserve_provenance": True,
    }
    dataset = {
        "report_type": "datumor.generated_dataset",
        "profile": {
            "profile_id": "general_llm",
            "profile_version": "1.0.0",
        },
        "examples": [{
            "example_id": "example-1",
            "task_type": "fact",
            "instruction": "Question",
            "response": "Answer",
            "provenance": {"source_id": "source-1"},
        }],
        "skipped": [],
    }
    before = json.dumps(dataset, sort_keys=True)
    report = validate_generated_dataset(dataset, profile)
    assert report["valid"], report
    assert json.dumps(dataset, sort_keys=True) == before


def test_dataset_rejects_missing_provenance_source():
    profile = {
        "profile_id": "general_llm",
        "version": "1.0.0",
        "required_fields": [
            "example_id", "task_type", "instruction", "response", "provenance"
        ],
        "preserve_provenance": True,
    }
    dataset = {
        "report_type": "datumor.generated_dataset",
        "profile": {
            "profile_id": "general_llm",
            "profile_version": "1.0.0",
        },
        "examples": [{
            "example_id": "example-1",
            "task_type": "fact",
            "instruction": "Question",
            "response": "Answer",
            "provenance": {},
        }],
    }
    report = validate_generated_dataset(dataset, profile)
    assert not report["valid"]
    assert report["errors"][0]["code"] == "DATASET_STRUCTURE_INVALID"
