import hashlib

import pytest

from apps.api.app.understanding.dukr_generator import (
    generate_dukr,
    validate_dukr,
)


CONTENT = "OpenAI develops artificial intelligence."


def inputs():
    extraction = {
        "format": "txt",
        "source_filename": "sample.txt",
        "content": CONTENT,
        "records": [{"record_number": 1}],
        "metadata": {
            "source": {
                "source_id": "source-1",
                "project_id": "project-1",
                "checksum_sha256": "a" * 64,
                "path": "sample.txt",
                "media_type": "text/plain",
            }
        },
        "warnings": [],
    }

    entities = {
        "entities": [
            {
                "entity_id": "entity-openai",
                "entity_type": "organization",
                "value": "OpenAI",
                "normalized_value": "openai",
                "confidence": 0.99,
                "method": "lexicon",
                "evidence": {"start_offset": 0, "end_offset": 6},
            },
            {
                "entity_id": "entity-ai",
                "entity_type": "concept",
                "value": "artificial intelligence",
                "normalized_value": "artificial intelligence",
                "confidence": 0.95,
                "method": "lexicon",
                "evidence": {"start_offset": 16, "end_offset": 39},
            },
        ]
    }

    semantics = {
        "overview": "A statement about OpenAI and AI.",
        "topics": [{"topic": "artificial_intelligence", "confidence": 0.9}],
        "content_classifications": ["technical_documentation"],
        "intents": ["informational"],
        "facts": [{
            "statement_id": "fact-1",
            "text": CONTENT,
            "epistemic_status": "observed",
            "evidence": {"start_offset": 0, "end_offset": len(CONTENT)},
        }],
        "claims": [{
            "statement_id": "claim-1",
            "text": "OpenAI develops artificial intelligence.",
            "epistemic_status": "observed_claim",
            "evidence": {"start_offset": 0, "end_offset": len(CONTENT)},
        }],
    }

    relationships = {
        "relationships": [{
            "relationship_id": "relation-1",
            "subject": {"entity_id": "entity-openai"},
            "predicate": "develops",
            "object": {"entity_id": "entity-ai"},
            "confidence": 0.95,
            "evidence": {"start_offset": 0, "end_offset": len(CONTENT)},
        }]
    }

    context = {
        "context_schema_version": "0.1.0",
        "context_units": [{
            "context_unit_id": "context-1",
            "unit_type": "paragraph",
            "sequence": 0,
            "start_offset": 0,
            "end_offset": len(CONTENT),
            "text": CONTENT,
            "entity_links": [
                {"entity_id": "entity-openai"},
                {"entity_id": "entity-ai"},
            ],
            "relationship_links": [
                {"relationship_id": "relation-1"}
            ],
        }],
        "summary": {"context_unit_count": 1, "sentence_count": 1},
        "warnings": [],
    }

    return extraction, entities, semantics, relationships, context


def build():
    return generate_dukr(*inputs())


def test_generates_expected_dukr_schema():
    result = build()

    assert result["dukr_schema"] == "datumor.dukr"
    assert result["dukr_schema_version"] == "1.0.0"
    assert result["representation_id"].startswith("dukr_")


def test_source_content_and_provenance_are_preserved():
    result = build()

    assert result["source"]["original_content"] == CONTENT
    assert result["source"]["source_id"] == "source-1"
    assert result["source"]["project_id"] == "project-1"
    assert result["source"]["checksum_sha256"] == "a" * 64
    assert result["source"]["source_records"] == [{"record_number": 1}]
    assert result["source"]["content_sha256"] == hashlib.sha256(
        CONTENT.encode()
    ).hexdigest()


def test_entities_are_canonicalized_without_losing_upstream_data():
    result = build()

    assert len(result["entities"]) == 2
    assert result["entities"][0]["entity_id"] == "entity-openai"
    assert result["entities"][0]["normalized_value"] == "openai"
    assert result["entities"][0]["upstream"]["method"] == "lexicon"


def test_observed_facts_and_claims_remain_distinguishable():
    result = build()
    statements = result["semantics"]["statements"]

    assert len(statements) == 2
    assert {item["statement_kind"] for item in statements} == {
        "fact", "claim"
    }
    assert {item["epistemic_status"] for item in statements} == {
        "observed", "observed_claim"
    }


def test_relationship_direction_and_evidence_are_preserved():
    result = build()
    relationship = result["relationships"][0]

    assert relationship["subject_entity_id"] == "entity-openai"
    assert relationship["predicate"] == "develops"
    assert relationship["object_entity_id"] == "entity-ai"
    assert relationship["evidence"]["start_offset"] == 0


def test_context_units_are_preserved_losslessly():
    result = build()

    assert result["context"]["context_units"][0]["text"] == CONTENT
    assert result["validation"]["checks"]["lossless_content"] is True


def test_knowledge_graph_contains_entity_nodes_and_relationship_edges():
    result = build()
    graph = result["knowledge_graph"]

    assert len(graph["nodes"]) == 4
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["subject_node_id"] == "entity-openai"
    assert graph["edges"][0]["object_node_id"] == "entity-ai"


def test_valid_complete_dukr_passes_validation():
    result = build()

    assert result["validation"]["valid"] is True
    assert result["validation"]["errors"] == []


def test_unresolved_relationship_endpoint_fails_validation():
    result = build()
    result["knowledge_graph"]["edges"][0]["object_node_id"] = "missing-node"

    validation = validate_dukr(result)

    assert validation["valid"] is False
    assert any("object reference is unresolved" in e for e in validation["errors"])


def test_corrupted_context_fails_validation():
    result = build()
    result["context"]["context_units"][0]["text"] = "corrupted"

    validation = validate_dukr(result)

    assert validation["valid"] is False
    assert any("reconstruct" in e for e in validation["errors"])


def test_checksum_tampering_is_detected():
    result = build()
    result["source"]["content_sha256"] = "0" * 64

    validation = validate_dukr(result)

    assert validation["valid"] is False
    assert any("checksum mismatch" in e for e in validation["errors"])


def test_missing_optional_upstream_inputs_are_supported():
    extraction = inputs()[0]
    result = generate_dukr(extraction)

    assert result["entities"] == []
    assert result["relationships"] == []
    assert result["semantics"]["statements"] == []
    assert result["validation"]["valid"] is True


def test_duplicate_entity_identifiers_are_rejected():
    extraction, entities, semantics, relationships, context = inputs()
    entities["entities"][1]["entity_id"] = "entity-openai"

    with pytest.raises(ValueError, match="Duplicate entity identifier"):
        generate_dukr(
            extraction, entities, semantics, relationships, context
        )


def test_context_reference_to_unknown_entity_fails_validation():
    result = build()
    result["context"]["context_units"][0]["entity_links"].append(
        {"entity_id": "missing-entity"}
    )

    validation = validate_dukr(result)

    assert validation["valid"] is False
    assert any("unknown entity" in error for error in validation["errors"])


def test_dukr_generation_is_deterministic():
    first = build()
    second = build()

    assert first["representation_id"] == second["representation_id"]
    assert [
        item["entity_id"] for item in first["entities"]
    ] == [
        item["entity_id"] for item in second["entities"]
    ]
