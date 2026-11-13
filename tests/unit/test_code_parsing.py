from pathlib import Path

import pytest

from apps.api.app.extraction.code_parser import (
    CodeParsingError,
    extract_code,
)
from apps.api.app.extraction.document_extractor import (
    ExtractionError,
    extract_document,
)


def test_python_declarations_and_imports(tmp_path: Path):
    source = (
        "import os\n\n"
        "class Worker:\n"
        "    def run(self, value):\n"
        "        return value\n\n"
        "def helper():\n"
        "    return 1\n"
    )
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")

    result = extract_code(path)

    assert result["metadata"]["language"] == "python"
    assert result["metadata"]["declaration_count"] == 3
    assert result["metadata"]["import_count"] == 1
    assert result["content"] == source

    declarations = [
        record for record in result["records"]
        if record["record_type"] == "declaration"
    ]
    assert [item["declaration_type"] for item in declarations] == [
        "class", "function", "function"
    ]
    assert declarations[1]["parent_id"] == declarations[0]["record_id"]
    assert declarations[0]["start_line"] == 3
    assert "def run" in declarations[1]["source_code"]


def test_javascript_functions_and_imports(tmp_path: Path):
    path = tmp_path / "sample.js"
    path.write_text(
        'import React from "react";\n'
        "function greet(name) { return name; }\n"
        "class App { render() { return null; } }\n",
        encoding="utf-8",
    )
    result = extract_code(path)
    assert result["metadata"]["language"] == "javascript"
    assert result["metadata"]["declaration_count"] >= 3
    assert result["metadata"]["import_count"] >= 1


def test_typescript_language_selection(tmp_path: Path):
    path = tmp_path / "sample.ts"
    path.write_text(
        "interface User { name: string; }\n"
        "function getUser(): User { return { name: 'A' }; }\n",
        encoding="utf-8",
    )
    result = extract_code(path)
    assert result["metadata"]["language"] == "typescript"
    assert result["metadata"]["declaration_count"] >= 2


def test_original_source_is_preserved(tmp_path: Path):
    source = "def exact_spacing( x ):\n    return  x\n"
    path = tmp_path / "spacing.py"
    path.write_text(source, encoding="utf-8")
    assert extract_code(path)["content"] == source


def test_syntax_errors_are_reported_without_losing_source(tmp_path: Path):
    source = "def broken(:\n    pass\n"
    path = tmp_path / "broken.py"
    path.write_text(source, encoding="utf-8")
    result = extract_code(path)
    assert result["content"] == source
    assert result["metadata"]["has_syntax_errors"] is True
    assert result["syntax_errors"]


def test_unsupported_language_is_rejected(tmp_path: Path):
    path = tmp_path / "sample.unknown"
    path.write_text("some content", encoding="utf-8")
    with pytest.raises(CodeParsingError, match="Unsupported"):
        extract_code(path)


def test_missing_source_is_rejected(tmp_path: Path):
    with pytest.raises(CodeParsingError, match="does not exist"):
        extract_code(tmp_path / "missing.py")


def test_document_extractor_dispatches_code(tmp_path: Path):
    path = tmp_path / "integrated.py"
    path.write_text("def integrated():\n    return True\n", encoding="utf-8")
    result = extract_document(path)
    assert result["format"] == "code"
    assert result["metadata"]["language"] == "python"
    assert result["metadata"]["declaration_count"] == 1


def test_document_extractor_wraps_code_errors(tmp_path: Path):
    path = tmp_path / "unsupported.xyz"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ExtractionError, match="Unsupported document format"):
        extract_document(path, "xyz")
