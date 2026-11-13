from apps.api.app.understanding.context_preserver import preserve_context


def extraction(content):
    return {
        "format": "text",
        "source_filename": "context-sample.txt",
        "content": content,
        "records": [{"record_number": 1, "source": "sample"}],
        "metadata": {
            "source": {
                "source_id": "source-123",
                "project_id": "project-123",
                "checksum_sha256": "c" * 64,
                "path": "context-sample.txt",
            }
        },
        "warnings": [],
    }


def test_original_content_is_preserved_exactly():
    content = "First paragraph.\n\nSecond paragraph.\nThird line."
    result = preserve_context(extraction(content))

    reconstructed = "".join(
        unit["text"] for unit in result["context_units"]
    )
    assert reconstructed == content
    assert result["document"]["original_content"] == content
    assert result["summary"]["original_content_preserved"] is True


def test_paragraph_order_and_offsets_are_preserved():
    content = "Alpha sentence.\n\nBeta sentence.\n\nGamma sentence."
    result = preserve_context(extraction(content))
    units = result["context_units"]

    assert len(units) == 3
    assert [unit["sequence"] for unit in units] == [0, 1, 2]

    for unit in units:
        assert content[
            unit["start_offset"]:unit["end_offset"]
        ] == unit["text"]


def test_sentence_offsets_reference_original_content():
    content = "First sentence. Second sentence!\n\nThird sentence?"
    result = preserve_context(extraction(content))

    for unit in result["context_units"]:
        for sentence in unit["sentences"]:
            start = sentence["start_offset"]
            end = sentence["end_offset"]
            assert content[start:end] == sentence["text"]


def test_neighboring_paragraph_context_is_linked():
    result = preserve_context(
        extraction("One paragraph.\n\nTwo paragraph.\n\nThree paragraph.")
    )
    units = result["context_units"]

    assert units[0]["previous_context_unit_id"] is None
    assert units[0]["next_context_unit_id"] == units[1]["context_unit_id"]
    assert units[1]["previous_context_unit_id"] == units[0]["context_unit_id"]
    assert units[2]["next_context_unit_id"] is None


def test_entity_relationship_and_fact_links_are_preserved():
    content = "OpenAI develops artificial intelligence."
    extracted = extraction(content)

    entities = {
        "entities": [
            {
                "entity_id": "entity-openai",
                "entity_type": "organization",
                "value": "OpenAI",
                "evidence": {
                    "start_offset": 0,
                    "end_offset": 6,
                    "page_number": 1,
                    "record_number": 2,
                    "start_line": 1,
                    "end_line": 1,
                    "segment_type": "content",
                },
            },
            {
                "entity_id": "entity-ai",
                "entity_type": "concept",
                "value": "artificial intelligence",
                "evidence": {
                    "start_offset": 16,
                    "end_offset": 39,
                    "page_number": 1,
                    "record_number": 2,
                    "start_line": 1,
                    "end_line": 1,
                    "segment_type": "content",
                },
            },
        ]
    }

    relationships = {
        "relationships": [{
            "relationship_id": "relation-1",
            "subject": {"entity_id": "entity-openai"},
            "predicate": "develops",
            "object": {"entity_id": "entity-ai"},
            "evidence": {
                "start_offset": 0,
                "end_offset": len(content),
            },
        }]
    }

    semantic = {
        "facts": [{
            "statement_id": "fact-1",
            "text": content,
            "epistemic_status": "observed",
            "evidence": {
                "start_offset": 0,
                "end_offset": len(content),
            },
        }],
        "claims": [],
    }

    result = preserve_context(
        extracted, entities, semantic, relationships
    )
    unit = result["context_units"][0]

    assert {e["entity_id"] for e in unit["entity_links"]} == {
        "entity-openai", "entity-ai"
    }
    assert unit["relationship_links"][0]["relationship_id"] == "relation-1"
    assert unit["fact_links"][0]["statement_id"] == "fact-1"

    sentence = unit["sentences"][0]
    assert len(sentence["entity_links"]) == 2
    assert sentence["relationship_links"][0]["relationship_id"] == "relation-1"


def test_source_provenance_is_retained():
    result = preserve_context(extraction("A source sentence."))

    assert result["source"]["source_id"] == "source-123"
    assert result["source"]["project_id"] == "project-123"
    assert result["source"]["checksum_sha256"] == "c" * 64
    assert result["source_records"][0]["record_number"] == 1


def test_page_and_record_references_are_preserved():
    content = "OpenAI develops artificial intelligence."
    extracted = extraction(content)
    entities = {
        "entities": [{
            "entity_id": "entity-1",
            "entity_type": "organization",
            "value": "OpenAI",
            "evidence": {
                "start_offset": 0,
                "end_offset": 6,
                "page_number": 3,
                "record_number": 7,
                "start_line": 12,
                "end_line": 12,
                "segment_type": "page",
            },
        }]
    }

    result = preserve_context(extracted, entities)
    link = result["context_units"][0]["entity_links"][0]

    assert link["page_number"] == 3
    assert link["record_number"] == 7
    assert link["start_line"] == 12
    assert link["segment_type"] == "page"


def test_empty_content_is_supported():
    result = preserve_context(extraction(""))

    assert result["context_units"] == []
    assert result["document"]["original_content"] == ""
    assert result["summary"]["original_content_preserved"] is True


def test_whitespace_only_content_is_preserved():
    content = " \n\n \t\n"
    result = preserve_context(extraction(content))

    assert "".join(
        unit["text"] for unit in result["context_units"]
    ) == content


def test_context_ids_are_stable():
    extracted = extraction("First paragraph.\n\nSecond paragraph.")
    first = preserve_context(extracted)
    second = preserve_context(extracted)

    assert [
        unit["context_unit_id"] for unit in first["context_units"]
    ] == [
        unit["context_unit_id"] for unit in second["context_units"]
    ]


def test_source_content_hash_is_correct():
    import hashlib

    content = "Preserve this exact content."
    result = preserve_context(extraction(content))

    assert result["document"]["content_sha256"] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def test_invalid_content_is_rejected():
    try:
        preserve_context({"content": None})
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid content.")


def test_summary_counts_are_consistent():
    result = preserve_context(
        extraction("First sentence. Second sentence.\n\nThird sentence.")
    )
    summary = result["summary"]

    assert summary["context_unit_count"] == len(result["context_units"])
    assert summary["sentence_count"] == sum(
        len(unit["sentences"]) for unit in result["context_units"]
    )
