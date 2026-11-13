import hashlib
from pathlib import Path

import pytest

from apps.api.app.extraction.metadata_extractor import extract_metadata
from apps.api.app.extraction.document_extractor import extract_document
from apps.api.app.extraction.code_parser import extract_code


def test_metadata_has_common_source_fields(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("alpha\nbeta\n", encoding="utf-8")

    result = extract_metadata(path, detected_format="text", content="alpha\nbeta\n")
    source = result["source"]

    assert source["filename"] == "sample.txt"
    assert source["extension"] == ".txt"
    assert source["format"] == "text"
    assert source["size_bytes"] == path.stat().st_size
    assert source["checksum_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert source["encoding"] == "utf-8"
    assert source["line_count"] == 2
    assert source["character_count"] == len("alpha\nbeta\n")
    assert source["metadata_schema_version"] == "1.0"


def test_existing_metadata_is_preserved(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text('{"name":"DATUMOR"}', encoding="utf-8")

    result = extract_metadata(
        path,
        existing_metadata={"root_type": "dict", "record_count": 1},
    )

    assert result["root_type"] == "dict"
    assert result["record_count"] == 1
    assert result["source"]["checksum_sha256"]


def test_source_identity_is_preserved(tmp_path: Path):
    path = tmp_path / "source.csv"
    path.write_text("id,name\n1,A\n", encoding="utf-8")
    identity = {"source_id": "source-123", "project_id": "project-456"}

    result = extract_metadata(path, source_metadata=identity)

    assert result["source_identity"] == identity


def test_utf8_bom_encoding_detection(tmp_path: Path):
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfDATUMOR")

    result = extract_metadata(path)
    assert result["source"]["encoding"] == "utf-8-sig"


def test_missing_file_is_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        extract_metadata(tmp_path / "missing.txt")


def test_document_extraction_includes_source_metadata(tmp_path: Path):
    path = tmp_path / "sample.md"
    path.write_text("# DATUMOR\n\nMetadata test.\n", encoding="utf-8")

    result = extract_document(path)

    assert result["metadata"]["heading_count"] == 1
    assert result["metadata"]["source"]["filename"] == "sample.md"
    assert result["metadata"]["source"]["checksum_sha256"] == (
        hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_code_extraction_includes_source_metadata(tmp_path: Path):
    path = tmp_path / "sample.py"
    path.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    result = extract_code(path)

    assert result["metadata"]["language"] == "python"
    assert result["metadata"]["declaration_count"] == 1
    assert result["metadata"]["source"]["checksum_sha256"] == (
        hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert result["metadata"]["source"]["filename"] == "sample.py"


def test_metadata_path_is_traceable(tmp_path: Path):
    path = tmp_path / "trace.txt"
    path.write_text("trace", encoding="utf-8")

    result = extract_metadata(path)
    assert result["source"]["path"].endswith("trace.txt")
    assert result["source"]["modified_at"]
    assert result["source"]["created_at"]
