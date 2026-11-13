from __future__ import annotations

import hashlib

import pytest

from apps.api.app.exporting import (
    DatasetExportError,
    export_dataset,
    build_export_configuration,
)


def test_export_returns_sha256_and_integrity_status(tmp_path):
    dataset = {"examples": [{"example_id": "e1", "text": "hello"}]}

    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("json"),
    )

    content = (tmp_path / "dataset.json").read_bytes()

    assert result["content_sha256"] == hashlib.sha256(content).hexdigest()
    assert len(result["content_sha256"]) == 64
    assert result["integrity_verified"] is True
    assert result["atomic_write"] is True


def test_jsonl_export_integrity(tmp_path):
    dataset = {"examples": [{"example_id": "e1"}, {"example_id": "e2"}]}

    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("jsonl"),
    )

    assert result["integrity_verified"] is True
    assert result["content_sha256"] == hashlib.sha256(
        (tmp_path / "dataset.jsonl").read_bytes()
    ).hexdigest()


def test_parquet_export_integrity(tmp_path):
    dataset = {"examples": [{"example_id": "e1", "value": 10}]}

    result = export_dataset(
        dataset,
        tmp_path,
        build_export_configuration("parquet"),
    )

    assert result["integrity_verified"] is True
    assert len(result["content_sha256"]) == 64


def test_existing_file_is_preserved_without_overwrite(tmp_path):
    destination = tmp_path / "dataset.json"
    destination.write_bytes(b"original-content")

    with pytest.raises(DatasetExportError, match="already exists"):
        export_dataset(
            {"examples": [{"example_id": "new"}]},
            tmp_path,
            build_export_configuration("json"),
        )

    assert destination.read_bytes() == b"original-content"


def test_overwrite_publishes_complete_verified_content(tmp_path):
    destination = tmp_path / "dataset.json"
    destination.write_bytes(b"old-content")

    result = export_dataset(
        {"examples": [{"example_id": "new"}]},
        tmp_path,
        build_export_configuration("json", overwrite=True),
    )

    assert result["integrity_verified"] is True
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == (
        result["content_sha256"]
    )


def test_failed_serialization_does_not_create_export_or_temp_file(tmp_path):
    with pytest.raises(DatasetExportError):
        export_dataset(
            {"value": float("nan")},
            tmp_path,
            build_export_configuration("json"),
        )

    assert not (tmp_path / "dataset.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_failed_staging_write_cleans_temporary_file(tmp_path, monkeypatch):
    import apps.api.app.exporting.dataset_exporter as exporter

    original_fsync = exporter.os.fsync

    def failing_fsync(_descriptor):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(exporter.os, "fsync", failing_fsync)

    with pytest.raises(DatasetExportError, match="Atomic export"):
        export_dataset(
            {"examples": [{"example_id": "e1"}]},
            tmp_path,
            build_export_configuration("json"),
        )

    assert not (tmp_path / "dataset.json").exists()
    assert list(tmp_path.glob(".*.tmp")) == []

    monkeypatch.setattr(exporter.os, "fsync", original_fsync)


def test_empty_export_has_valid_checksum(tmp_path):
    result = export_dataset(
        {"examples": []},
        tmp_path,
        build_export_configuration("jsonl"),
    )

    assert result["size_bytes"] == 0
    assert result["content_sha256"] == hashlib.sha256(b"").hexdigest()
    assert result["integrity_verified"] is True


def test_export_does_not_leave_temporary_files(tmp_path):
    export_dataset(
        {"examples": [{"example_id": "e1"}]},
        tmp_path,
        build_export_configuration("json"),
    )

    assert list(tmp_path.glob(".*.tmp")) == []
