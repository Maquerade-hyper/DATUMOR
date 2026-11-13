import json

import pytest

from apps.api.app.detection.format_detector import detect_format


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        ("sample.pdf", b"%PDF-1.7\nsample", "pdf"),
        ("sample.png", b"\x89PNG\r\n\x1a\nrest", "png"),
        ("sample.jpg", b"\xff\xd8\xffrest", "jpeg"),
        ("sample.gif", b"GIF89arest", "gif"),
        ("sample.json", b'{"name":"datumor"}', "json"),
        ("sample.jsonl", b'{"a":1}\n{"a":2}\n', "jsonl"),
        ("sample.csv", b"name,age\nAlice,20\nBob,21\n", "csv"),
        ("sample.md", b"# DATUMOR\n\nA project.", "markdown"),
        ("sample.txt", b"Plain text content.", "text"),
        ("sample.py", b"def hello():\n    return 'hi'\n", "python"),
        ("sample.zip", b"PK\x03\x04archive", "zip"),
        ("sample.gz", b"\x1f\x8bcompressed", "gzip"),
        ("sample.mp3", b"ID3audio", "mp3"),
        ("sample.flac", b"fLaCaudio", "flac"),
        ("sample.wav", b"RIFFxxxxWAVEdata", "wav"),
        ("sample.mp4", b"\x00\x00\x00\x18ftypisom", "mp4"),
        ("sample.parquet", b"PAR1data", "parquet"),
    ],
)
def test_detects_supported_formats(tmp_path, filename, content, expected):
    path = tmp_path / filename
    path.write_bytes(content)

    result = detect_format(path)

    assert result["format"] == expected
    assert result["confidence"] >= 0.80


def test_detects_content_extension_mismatch(tmp_path):
    path = tmp_path / "misleading.txt"
    path.write_bytes(b"%PDF-1.7\ncontent")

    result = detect_format(path)

    assert result["format"] == "pdf"
    assert result["extension_matches"] is False
    assert result["warnings"]


def test_detects_json_even_with_txt_extension(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text(json.dumps({"project": "DATUMOR"}), encoding="utf-8")

    result = detect_format(path)

    assert result["format"] == "json"
    assert result["extension_matches"] is False


def test_unknown_binary_is_not_guessed(tmp_path):
    path = tmp_path / "unknown.bin"
    path.write_bytes(b"\x00\x01\x02\x03\xff")

    result = detect_format(path)

    assert result["format"] == "unknown"
    assert result["confidence"] <= 0.20


def test_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    result = detect_format(path)

    assert result["format"] == "empty"


def test_result_contains_contract_fields(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("DATUMOR", encoding="utf-8")

    result = detect_format(path, declared_media_type="text/plain")

    assert set(result) == {
        "format", "media_type", "category", "detection_method",
        "confidence", "extension", "extension_matches", "warnings",
    }
