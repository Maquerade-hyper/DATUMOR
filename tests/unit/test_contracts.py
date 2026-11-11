import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
FORMAT_CHECKER = FormatChecker()

EXAMPLES = {
    "source.schema.json": {
        "contract_version": "1.0.0",
        "source_id": "11111111-1111-4111-8111-111111111111",
        "project_id": "22222222-2222-4222-8222-222222222222",
        "source_type": "file",
        "source_name": "sample.pdf",
        "media_type": "application/pdf",
        "checksum_sha256": "a" * 64,
        "uri": None,
        "metadata": {},
        "created_at": "2026-01-01T10:00:00Z"
    },
    "dataset.schema.json": {
        "contract_version": "1.0.0",
        "dataset_id": "33333333-3333-4333-8333-333333333333",
        "project_id": "22222222-2222-4222-8222-222222222222",
        "version": 1,
        "status": "created",
        "task_type": "coding",
        "source_ids": ["11111111-1111-4111-8111-111111111111"],
        "record_count": 0,
        "schema_version": "1.0.0",
        "created_at": "2026-01-01T10:00:00Z"
    },
    "processing-job.schema.json": {
        "contract_version": "1.0.0",
        "job_id": "44444444-4444-4444-8444-444444444444",
        "dataset_id": "33333333-3333-4333-8333-333333333333",
        "status": "queued",
        "stage": "ingestion",
        "progress": 0,
        "created_at": "2026-01-01T10:00:00Z",
        "started_at": None,
        "completed_at": None,
        "error": None
    },
    "processing-profile.schema.json": {
        "contract_version": "1.0.0",
        "profile_id": "55555555-5555-4555-8555-555555555555",
        "profile_name": "Coding Dataset",
        "task_type": "coding",
        "output_format": "jsonl",
        "options": {},
        "chunking": {
            "enabled": True,
            "max_tokens": 2048,
            "overlap_tokens": 100
        }
    },
    "quality-report.schema.json": {
        "contract_version": "1.0.0",
        "dataset_id": "33333333-3333-4333-8333-333333333333",
        "dataset_version": 1,
        "overall_score": 95.0,
        "status": "passed",
        "metrics": {"completeness": 98.0, "consistency": 92.0},
        "issues": [],
        "generated_at": "2026-01-01T10:00:00Z"
    },
    "lineage-event.schema.json": {
        "contract_version": "1.0.0",
        "event_id": "66666666-6666-4666-8666-666666666666",
        "dataset_id": "33333333-3333-4333-8333-333333333333",
        "dataset_version": 1,
        "event_type": "source_added",
        "actor": "system",
        "timestamp": "2026-01-01T10:00:00Z",
        "input_references": [],
        "output_checksum_sha256": None,
        "metadata": {}
    },
    "api-error.schema.json": {
        "contract_version": "1.0.0",
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Payload validation failed",
            "details": [],
            "trace_id": "77777777-7777-4777-8777-777777777777"
        }
    }
}

@pytest.mark.parametrize("filename", sorted(EXAMPLES))
def test_schema_is_valid(filename):
    schema = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

@pytest.mark.parametrize("filename,payload", EXAMPLES.items())
def test_valid_payload_is_accepted(filename, payload):
    schema = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    validator.validate(payload)

def test_invalid_source_checksum_is_rejected():
    schema = json.loads((SCHEMA_DIR / "source.schema.json").read_text(encoding="utf-8"))
    payload = dict(EXAMPLES["source.schema.json"])
    payload["checksum_sha256"] = "not-a-sha256"
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    assert list(validator.iter_errors(payload))

def test_job_progress_over_100_is_rejected():
    schema = json.loads((SCHEMA_DIR / "processing-job.schema.json").read_text(encoding="utf-8"))
    payload = dict(EXAMPLES["processing-job.schema.json"])
    payload["progress"] = 101
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    assert list(validator.iter_errors(payload))

def test_unknown_dataset_fields_are_rejected():
    schema = json.loads((SCHEMA_DIR / "dataset.schema.json").read_text(encoding="utf-8"))
    payload = dict(EXAMPLES["dataset.schema.json"])
    payload["unexpected_field"] = True
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    assert list(validator.iter_errors(payload))
