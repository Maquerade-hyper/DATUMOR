import json

import pytest

from apps.api.app.multimodal.multimodal_record import (
    MultimodalRecordError,
    generate_multimodal_record,
    validate_multimodal_record,
    export_multimodal_record,
    load_multimodal_record,
)


def make_valid_record():
    image = {
        "report_type": "datumor.image_analysis",
        "version": "1.0.0",
        "status": "completed",
        "created_at": "2026-11-11T12:00:00+00:00",
        "source": {
            "source_id": None,
            "source_name": "serialization-test.png",
            "checksum_sha256": "a" * 64,
            "size_bytes": 128,
            "media_type": "image/png",
        },
        "capabilities": {},
        "warnings": [],
    }
    record = generate_multimodal_record(images=[image])
    result = validate_multimodal_record(record)
    assert result["valid"], result["errors"]
    return record


def test_valid_record_export_and_reload_roundtrip(tmp_path):
    record = make_valid_record()
    path = export_multimodal_record(record, tmp_path / "record.json")

    loaded = load_multimodal_record(path)

    assert loaded == record
    assert loaded["validation"]["status"] == "valid"


def test_invalid_record_cannot_be_exported(tmp_path):
    record = make_valid_record()
    record["provenance"]["sources"][0]["checksum_sha256"] = "f" * 64

    with pytest.raises(MultimodalRecordError, match="Cannot export invalid"):
        export_multimodal_record(record, tmp_path / "invalid.json")

    assert not (tmp_path / "invalid.json").exists()


def test_tampered_record_rejected_on_reload(tmp_path):
    record = make_valid_record()
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    loaded_json = json.loads(path.read_text(encoding="utf-8"))
    loaded_json["provenance"]["sources"][0]["checksum_sha256"] = "f" * 64
    path.write_text(json.dumps(loaded_json), encoding="utf-8")

    with pytest.raises(MultimodalRecordError, match="Loaded multimodal record is invalid"):
        load_multimodal_record(path)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"record_id":"one","record_id":"two"}', encoding="utf-8")

    with pytest.raises(MultimodalRecordError, match="Duplicate JSON key"):
        load_multimodal_record(path)


def test_nonfinite_json_constant_rejected(tmp_path):
    path = tmp_path / "nonfinite.json"
    path.write_text('{"record_id": NaN}', encoding="utf-8")

    with pytest.raises(MultimodalRecordError, match="Non-finite JSON number"):
        load_multimodal_record(path)


def test_deterministic_serialization(tmp_path):
    record = make_valid_record()

    first = export_multimodal_record(record, tmp_path / "first.json")
    second = export_multimodal_record(record, tmp_path / "second.json")

    assert first.read_bytes() == second.read_bytes()


def test_loaded_record_is_schema_valid(tmp_path):
    record = make_valid_record()
    path = export_multimodal_record(record, tmp_path / "record.json")

    loaded = load_multimodal_record(path)
    result = validate_multimodal_record(loaded)

    assert result["valid"]
    assert loaded["validation"]["status"] == "valid"
