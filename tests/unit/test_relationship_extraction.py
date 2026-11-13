import re
from apps.api.app.understanding.relationship_extractor import (
    extract_relationships,
)


def make_fixture(content):
    entities = []
    values = [
        ("OpenAI", "organization"),
        ("artificial intelligence", "concept"),
        ("Python", "technology"),
        ("FastAPI", "technology"),
        ("Bengaluru", "location"),
        ("India", "location"),
        ("Guneshwar", "person"),
        ("DATUMOR", "organization"),
    ]

    for value, kind in values:
        pattern = re.compile(re.escape(value), re.IGNORECASE)
        for match in pattern.finditer(content):
            start, end = match.span()
            actual_value = content[start:end]
            entities.append({
                "entity_id": f"{kind}-{value}-{start}",
                "entity_type": kind,
                "value": actual_value,
                "normalized_value": actual_value.casefold(),
                "evidence": {
                    "start_offset": start,
                    "end_offset": end,
                },
            })

    return {
        "format": "text",
        "source_filename": "relationship-sample.txt",
        "content": content,
        "records": [],
        "metadata": {
            "source": {
                "checksum_sha256": "b" * 64,
                "path": "relationship-sample.txt",
            }
        },
        "warnings": [],
    }, {"entities": entities}


def test_extracts_forward_development_relationship():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence."
    )
    result = extract_relationships(extraction, entities)
    relation = result["relationships"][0]

    assert relation["triple"] == {
        "subject": "OpenAI",
        "predicate": "develops",
        "object": "artificial intelligence",
    }


def test_extracts_uses_relationship():
    extraction, entities = make_fixture(
        "DATUMOR uses Python."
    )
    result = extract_relationships(extraction, entities)
    assert result["relationships"][0]["predicate"] == "uses"


def test_extracts_collaboration_relationship():
    extraction, entities = make_fixture(
        "Guneshwar works with OpenAI."
    )
    result = extract_relationships(extraction, entities)
    relation = result["relationships"][0]
    assert relation["predicate"] == "collaborates_with"
    assert relation["subject"]["value"] == "Guneshwar"
    assert relation["object"]["value"] == "OpenAI"


def test_extracts_reverse_developed_by_direction():
    extraction, entities = make_fixture(
        "Artificial intelligence was developed by OpenAI."
    )
    result = extract_relationships(extraction, entities)
    relation = result["relationships"][0]

    assert relation["subject"]["value"] == "OpenAI"
    assert relation["predicate"] == "develops"
    assert relation["object"]["value"] == "Artificial intelligence"
    assert relation["object"]["normalized_value"] == "artificial intelligence"


def test_extracts_location_relationship():
    extraction, entities = make_fixture(
        "DATUMOR is located in Bengaluru."
    )
    result = extract_relationships(extraction, entities)
    assert result["relationships"][0]["predicate"] == "located_in"


def test_does_not_infer_relationship_from_cooccurrence():
    extraction, entities = make_fixture(
        "OpenAI and Python are mentioned in this sentence."
    )
    result = extract_relationships(extraction, entities)
    assert result["relationships"] == []


def test_evidence_offsets_reference_original_sentence():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence."
    )
    result = extract_relationships(extraction, entities)

    for relation in result["relationships"]:
        evidence = relation["evidence"]
        start = evidence["start_offset"]
        end = evidence["end_offset"]
        assert extraction["content"][start:end] == evidence["text"]


def test_relationship_ids_are_stable():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence."
    )
    first = extract_relationships(extraction, entities)
    second = extract_relationships(extraction, entities)

    assert [
        item["relationship_id"] for item in first["relationships"]
    ] == [
        item["relationship_id"] for item in second["relationships"]
    ]


def test_duplicate_relationships_are_deduplicated():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence."
    )
    entities["entities"].append(dict(entities["entities"][0]))
    result = extract_relationships(extraction, entities)

    assert len(result["relationships"]) == 1


def test_source_provenance_is_preserved():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence."
    )
    result = extract_relationships(extraction, entities)

    assert result["source"]["filename"] == "relationship-sample.txt"
    assert result["source"]["checksum_sha256"] == "b" * 64
    assert result["relationships"][0]["provenance"] == result["source"]


def test_empty_content_returns_no_relationships():
    extraction, entities = make_fixture("")
    result = extract_relationships(extraction, entities)

    assert result["relationships"] == []
    assert result["summary"]["relationship_count"] == 0


def test_invalid_content_is_rejected():
    try:
        extract_relationships({"content": None})
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid content.")


def test_summary_counts_are_consistent():
    extraction, entities = make_fixture(
        "OpenAI develops artificial intelligence. DATUMOR uses Python."
    )
    result = extract_relationships(extraction, entities)

    assert result["summary"]["relationship_count"] == len(
        result["relationships"]
    )
