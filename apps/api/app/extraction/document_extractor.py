import csv
import json
from pathlib import Path
from typing import Any


from .metadata_extractor import extract_metadata

class ExtractionError(Exception):
    pass


def _base_result(path: Path, fmt: str, content: Any, records: list,
                 metadata: dict, warnings: list | None = None) -> dict:
    normalized_metadata = extract_metadata(
        path,
        detected_format=fmt,
        content=content if isinstance(content, (str, bytes)) else None,
        existing_metadata=metadata,
    )
    return {
        "format": fmt,
        "source_filename": path.name,
        "content": content,
        "records": records,
        "metadata": normalized_metadata,
        "warnings": warnings or [],
    }


def extract_document(path: str | Path, detected_format: str | None = None) -> dict:
    path = Path(path)

    if not path.is_file():
        raise ExtractionError(f"Source file does not exist: {path}")

    fmt = detected_format or path.suffix.lower().lstrip(".")

    code_formats = {"py", "pyw", "js", "mjs", "cjs", "jsx", "ts", "tsx", "java", "c", "h", "cc", "cpp", "cxx", "hpp", "cs", "go", "rs", "php", "rb", "python", "javascript", "typescript", "c_sharp"}
    if fmt.lower() in code_formats:
        from .code_parser import extract_code
        try:
            return extract_code(path, fmt)
        except Exception as exc:
            raise ExtractionError(f"Code parsing failed: {exc}") from exc

    try:
        if fmt == "pdf":
            return _extract_pdf(path)
        if fmt in {"txt", "text"}:
            return _extract_text(path)
        if fmt in {"md", "markdown"}:
            return _extract_markdown(path)
        if fmt == "json":
            return _extract_json(path)
        if fmt == "jsonl":
            return _extract_jsonl(path)
        if fmt == "csv":
            return _extract_csv(path)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(
            f"Failed to extract {fmt} document: {exc}"
        ) from exc

    raise ExtractionError(f"Unsupported document format: {fmt}")


def _extract_pdf(path: Path) -> dict:
    import pdfplumber

    pages = []
    warnings = []

    try:
        with pdfplumber.open(path) as document:
            raw_metadata = document.metadata or {}
            metadata = {
                "page_count": len(document.pages),
                "title": raw_metadata.get("Title"),
                "author": raw_metadata.get("Author"),
                "subject": raw_metadata.get("Subject"),
                "creator": raw_metadata.get("Creator"),
                "producer": raw_metadata.get("Producer"),
            }

            for index, page in enumerate(document.pages):
                text = page.extract_text() or ""
                tables = []

                try:
                    tables = page.extract_tables() or []
                except Exception:
                    warnings.append(
                        f"Table extraction unavailable on page {index + 1}."
                    )

                pages.append({
                    "page_number": index + 1,
                    "text": text,
                    "tables": tables,
                    "width": page.width,
                    "height": page.height,
                    "rotation": getattr(page, "rotation", 0),
                })

    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise ExtractionError("Encrypted PDF is not supported.") from exc
        raise

    content = "\n\n".join(page["text"] for page in pages)

    records = [
        {
            "record_type": "page",
            "page_number": page["page_number"],
            "text": page["text"],
            "tables": page["tables"],
        }
        for page in pages
    ]

    return _base_result(
        path, "pdf", content, records, metadata, warnings
    )


def _extract_text(path: Path) -> dict:
    content = path.read_text(encoding="utf-8-sig")
    records = [{
        "record_type": "text",
        "text": content,
        "line_count": len(content.splitlines()),
    }]
    return _base_result(
        path, "text", content, records,
        {"character_count": len(content),
         "line_count": len(content.splitlines())}
    )


def _extract_markdown(path: Path) -> dict:
    content = path.read_text(encoding="utf-8-sig")
    headings = []

    for line_number, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if 1 <= level <= 6 and stripped[level:level + 1] == " ":
                headings.append({
                    "level": level,
                    "text": stripped[level:].strip(),
                    "line_number": line_number,
                })

    records = [{
        "record_type": "markdown",
        "text": content,
        "headings": headings,
    }]

    return _base_result(
        path, "markdown", content, records,
        {"character_count": len(content),
         "heading_count": len(headings),
         "headings": headings}
    )


def _extract_json(path: Path) -> dict:
    content = json.loads(path.read_text(encoding="utf-8-sig"))
    records = [{
        "record_type": "json",
        "value": content,
    }]
    return _base_result(
        path, "json", content, records,
        {"root_type": type(content).__name__}
    )


def _extract_jsonl(path: Path) -> dict:
    records = []

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"Invalid JSONL at line {line_number}: {exc.msg}"
            ) from exc

        records.append({
            "record_type": "jsonl_record",
            "record_number": len(records) + 1,
            "line_number": line_number,
            "value": value,
        })

    return _base_result(
        path, "jsonl", records, records,
        {"record_count": len(records)}
    )


def _extract_csv(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames or []
        records = []

        for index, row in enumerate(reader, 1):
            records.append({
                "record_type": "csv_row",
                "record_number": index,
                "value": dict(row),
            })

    return _base_result(
        path, "csv", records, records,
        {"headers": headers, "row_count": len(records),
         "column_count": len(headers)}
    )
