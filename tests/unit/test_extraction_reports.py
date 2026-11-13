import json
from pathlib import Path

import pytest

from apps.api.app.extraction.report_generator import (
    generate_extraction_report,
    render_extraction_report_markdown,
    write_extraction_report,
)


def successful_result():
    return {
        "format": "python",
        "source_filename": "app.py",
        "content": "def hello(): pass",
        "records": [{"record_type": "declaration"}],
        "metadata": {
            "language": "python",
            "source": {
                "filename": "app.py",
                "path": "src/app.py",
                "media_type": "text/x-python",
                "size_bytes": 100,
                "checksum_sha256": "abc123",
            },
            "source_identity": {
                "source_id": "source-1",
                "project_id": "project-1",
            },
        },
        "warnings": ["Example warning"],
        "syntax_errors": [],
    }


def test_report_summary_counts_sources_and_records():
    report = generate_extraction_report([
        successful_result(),
        {
            "source_filename": "broken.pdf",
            "status": "failed",
            "error": "Invalid PDF",
            "records": [],
            "warnings": [],
        },
    ])

    assert report["status"] == "partial"
    assert report["summary"]["total_sources"] == 2
    assert report["summary"]["successful_sources"] == 1
    assert report["summary"]["failed_sources"] == 1
    assert report["summary"]["total_records"] == 1
    assert report["summary"]["total_warnings"] == 1


def test_report_preserves_provenance_and_checksum():
    report = generate_extraction_report(successful_result())
    source = report["sources"][0]

    assert source["source_id"] == "source-1"
    assert source["project_id"] == "project-1"
    assert source["source_path"] == "src/app.py"
    assert source["checksum_sha256"] == "abc123"


def test_report_counts_syntax_errors():
    result = successful_result()
    result["syntax_errors"] = [
        {"syntax_type": "ERROR", "start_line": 4},
        {"syntax_type": "MISSING", "start_line": 5},
    ]

    report = generate_extraction_report(result)

    assert report["summary"]["total_syntax_errors"] == 2
    assert report["sources"][0]["syntax_error_count"] == 2


def test_all_failed_report_status():
    report = generate_extraction_report({
        "source_filename": "broken.json",
        "status": "failed",
        "error": "Invalid JSON",
    })
    assert report["status"] == "failed"
    assert report["summary"]["failed_sources"] == 1


def test_successful_report_status():
    report = generate_extraction_report(successful_result())
    assert report["status"] == "success"


def test_empty_report_is_rejected():
    with pytest.raises(ValueError, match="At least one"):
        generate_extraction_report([])


def test_invalid_result_type_is_rejected():
    with pytest.raises(TypeError):
        generate_extraction_report([successful_result(), "invalid"])


def test_markdown_report_contains_summary_and_source():
    report = generate_extraction_report(successful_result())
    markdown = render_extraction_report_markdown(report)

    assert "# DATUMOR Extraction Report" in markdown
    assert "app.py" in markdown
    assert "Extracted records: 1" in markdown
    assert "abc123" in markdown


def test_json_and_markdown_files_are_written(tmp_path: Path):
    report = generate_extraction_report(successful_result())
    paths = write_extraction_report(report, tmp_path)

    json_path = Path(paths["json_path"])
    markdown_path = Path(paths["markdown_path"])

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_id"] == report["report_id"]
    assert "DATUMOR Extraction Report" in markdown_path.read_text(encoding="utf-8")


def test_unsafe_basename_is_rejected(tmp_path: Path):
    report = generate_extraction_report(successful_result())

    with pytest.raises(ValueError, match="basename"):
        write_extraction_report(report, tmp_path, basename="../escape")
