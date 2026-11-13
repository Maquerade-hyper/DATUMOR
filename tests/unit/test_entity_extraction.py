
from apps.api.app.understanding.entity_extractor import extract_entities


def sample_result():
    text = (
        "DATUMOR uses Python and FastAPI for artificial intelligence. "
        "Contact team@example.com. Visit https://example.com. "
        "The project is developed by Alice Smith in India. "
        "OpenAI Technologies builds machine learning systems."
    )
    return {
        "format": "text",
        "source_filename": "sample.txt",
        "content": text,
        "records": [],
        "metadata": {
            "source": {
                "filename": "sample.txt",
                "path": "docs/sample.txt",
                "checksum_sha256": "abc123",
            },
            "source_identity": {
                "source_id": "source-1",
                "project_id": "project-1",
            },
        },
    }


def test_extracts_technology_and_concepts():
    result = extract_entities(sample_result())
    types = {entity["entity_type"] for entity in result["entities"]}

    assert "technology" in types
    assert "concept" in types
    assert any(
        entity["normalized_value"] == "python"
        for entity in result["entities"]
    )


def test_extracts_email_and_url():
    result = extract_entities(sample_result())
    values = {
        entity["value"] for entity in result["entities"]
    }

    assert "team@example.com" in values
    assert "https://example.com" in values


def test_extracts_contextual_person_and_organization():
    result = extract_entities(sample_result())
    pairs = {
        (entity["entity_type"], entity["value"])
        for entity in result["entities"]
    }

    assert ("person", "Alice Smith") in pairs
    assert ("organization", "OpenAI Technologies") in pairs


def test_extracts_standalone_organization_name():
    result = extract_entities({
        "format": "text",
        "source_filename": "organization.txt",
        "content": "Guneshwar works with OpenAI in Bengaluru.",
        "records": [],
        "metadata": {},
        "warnings": [],
    })

    assert any(
        entity["entity_type"] == "organization"
        and entity["value"] == "OpenAI"
        for entity in result["entities"]
    )


def test_extracts_location():
    result = extract_entities(sample_result())
    assert any(
        entity["entity_type"] == "location"
        and entity["normalized_value"] == "india"
        for entity in result["entities"]
    )


def test_source_traceability_is_preserved():
    result = extract_entities(sample_result())
    assert result["source"]["source_id"] == "source-1"
    assert result["source"]["project_id"] == "project-1"
    assert result["source"]["checksum_sha256"] == "abc123"

    for entity in result["entities"]:
        assert entity["source"]["filename"] == "sample.txt"
        assert entity["source"]["checksum_sha256"] == "abc123"


def test_evidence_offsets_point_to_exact_match():
    result = extract_entities(sample_result())
    text = sample_result()["content"]

    for entity in result["entities"]:
        evidence = entity["evidence"]
        start = evidence["start_offset"]
        end = evidence["end_offset"]
        if start is not None:
            assert text[start:end] == evidence["matched_text"]


def test_entity_ids_are_stable():
    first = extract_entities(sample_result())
    second = extract_entities(sample_result())

    assert [
        entity["entity_id"] for entity in first["entities"]
    ] == [
        entity["entity_id"] for entity in second["entities"]
    ]


def test_pdf_page_reference_is_preserved():
    result = {
        "format": "pdf",
        "source_filename": "sample.pdf",
        "content": "ignored combined content",
        "records": [
            {
                "record_type": "page",
                "page_number": 2,
                "text": "Python is used for machine learning.",
            }
        ],
        "metadata": {"source": {"checksum_sha256": "pdfhash"}},
    }

    entities = extract_entities(result)
    python_entity = next(
        entity for entity in entities["entities"]
        if entity["normalized_value"] == "python"
    )

    assert python_entity["evidence"]["page_number"] == 2


def test_code_parser_records_become_code_entities():
    result = {
        "format": "code",
        "source_filename": "app.py",
        "content": "def hello():\n    return True\n",
        "records": [
            {
                "record_type": "declaration",
                "declaration_type": "function",
                "name": "hello",
                "source_code": "def hello(): return True",
                "start_line": 1,
                "end_line": 2,
                "file_path": "src/app.py",
            }
        ],
        "metadata": {"source": {"checksum_sha256": "codehash"}},
    }

    entities = extract_entities(result)
    symbol = next(
        entity for entity in entities["entities"]
        if entity["entity_type"] == "code_symbol"
    )

    assert symbol["value"] == "hello"
    assert symbol["evidence"]["start_line"] == 1


def test_empty_content_returns_empty_entities():
    result = {
        "format": "text",
        "source_filename": "empty.txt",
        "content": "",
        "records": [],
        "metadata": {},
    }

    extracted = extract_entities(result)
    assert extracted["summary"]["entity_count"] == 0


def test_invalid_input_is_rejected():
    try:
        extract_entities("not a result")
    except TypeError:
        pass
    else:
        raise AssertionError("Expected TypeError")
