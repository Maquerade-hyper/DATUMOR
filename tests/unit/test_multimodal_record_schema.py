import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "schemas"
    / "multimodal-record.schema.json"
)


def load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))


def test_multimodal_schema_is_valid_draft_2020_12():
    schema = load_schema()
    Draft202012Validator.check_schema(schema)


def test_schema_requires_canonical_record_fields():
    schema = load_schema()

    assert set(schema["required"]) == {
        "record_id",
        "schema_version",
        "created_at",
        "modalities",
        "temporal",
        "provenance",
        "warnings",
        "validation",
    }


def test_schema_rejects_unknown_top_level_fields():
    schema = load_schema()
    assert schema["additionalProperties"] is False


def test_schema_defines_all_supported_modalities():
    schema = load_schema()
    properties = schema["properties"]["modalities"]["properties"]

    assert {"images", "audio", "video"} == set(properties)


def test_schema_allows_missing_audio_and_video():
    schema = load_schema()
    properties = schema["properties"]["modalities"]["properties"]

    assert "null" in properties["audio"]["type"]
    assert "null" in properties["video"]["type"]


def test_schema_accepts_valid_minimal_record():
    schema = load_schema()
    record = {
        "record_id": "123e4567-e89b-42d3-a456-426614174000",
        "schema_version": "1.0.0",
        "created_at": "2026-11-11T12:00:00+00:00",
        "modalities": {
            "images": [],
            "audio": None,
            "video": None,
        },
        "temporal": None,
        "provenance": {
            "sources": [],
            "upstream_reports": [],
        },
        "warnings": [],
        "validation": {
            "status": "valid",
            "errors": [],
        },
    }

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )
    assert list(validator.iter_errors(record)) == []


def test_schema_rejects_invalid_schema_version():
    schema = load_schema()
    record = {
        "record_id": "123e4567-e89b-42d3-a456-426614174000",
        "schema_version": "2.0.0",
        "created_at": "2026-11-11T12:00:00+00:00",
        "modalities": {"images": [], "audio": None, "video": None},
        "temporal": None,
        "provenance": {"sources": [], "upstream_reports": []},
        "warnings": [],
        "validation": {"status": "valid", "errors": []},
    }

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(record))
