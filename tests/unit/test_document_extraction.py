import pytest

from apps.api.app.extraction.document_extractor import (
    extract_document,
    ExtractionError,
)


def test_extract_text(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("DATUMOR text extraction", encoding="utf-8")
    result = extract_document(path)
    assert result["content"] == "DATUMOR text extraction"
    assert result["metadata"]["line_count"] == 1


def test_extract_markdown_headings(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Main\n\n## Section\nText", encoding="utf-8")
    result = extract_document(path)
    assert len(result["metadata"]["headings"]) == 2
    assert result["metadata"]["headings"][1]["level"] == 2


def test_extract_json(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text('{"name":"DATUMOR"}', encoding="utf-8")
    result = extract_document(path)
    assert result["content"]["name"] == "DATUMOR"


def test_extract_jsonl_preserves_record_numbers(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"id":1}\n\n{"id":2}\n', encoding="utf-8")
    result = extract_document(path)
    assert result["metadata"]["record_count"] == 2
    assert result["records"][1]["line_number"] == 3


def test_extract_csv(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("name,age\nAlice,20\nBob,21\n", encoding="utf-8")
    result = extract_document(path)
    assert result["metadata"]["headers"] == ["name", "age"]
    assert result["metadata"]["row_count"] == 2
    assert result["records"][0]["value"]["name"] == "Alice"


def test_invalid_jsonl_reports_line(tmp_path):
    path = tmp_path / "invalid.jsonl"
    path.write_text('{"id":1}\ninvalid\n', encoding="utf-8")
    with pytest.raises(ExtractionError, match="line 2"):
        extract_document(path)


def test_missing_source_rejected(tmp_path):
    with pytest.raises(ExtractionError, match="does not exist"):
        extract_document(tmp_path / "missing.txt")


def test_unsupported_format_rejected(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"binary")
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract_document(path)


def test_extract_pdf_preserves_pages(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "sample.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.setTitle("DATUMOR Verification")
    pdf.drawString(72, 720, "DATUMOR page one")
    pdf.showPage()
    pdf.drawString(72, 720, "DATUMOR page two")
    pdf.showPage()
    pdf.save()

    result = extract_document(path)

    assert result["metadata"]["page_count"] == 2
    assert result["metadata"]["title"] == "DATUMOR Verification"
    assert result["records"][0]["page_number"] == 1
    assert result["records"][1]["page_number"] == 2
    assert "DATUMOR page one" in result["content"]
    assert "DATUMOR page two" in result["content"]
    assert isinstance(result["records"][0]["tables"], list)
