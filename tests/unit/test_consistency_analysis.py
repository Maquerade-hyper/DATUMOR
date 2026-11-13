import pytest

from apps.api.app.quality.consistency_analyzer import analyze_consistency


def make_dukr(
    source_id,
    entity_value="OpenAI",
    object_value="artificial intelligence",
    statement="OpenAI develops artificial intelligence.",
    predicate="develops",
):
    content = statement

    entities = [
        {
            "entity_id": "e1",
            "entity_type": "organization",
            "value": entity_value,
            "normalized_value": entity_value.casefold(),
            "evidence": {"start_offset": 0, "end_offset": min(6, len(content))},
        },
        {
            "entity_id": "e2",
            "entity_type": "concept",
            "value": object_value,
            "normalized_value": object_value.casefold(),
            "evidence": {"start_offset": 0, "end_offset": len(content)},
        },
    ]

    relationship = {
        "relationship_id": f"r-{source_id}",
        "subject_entity_id": "e1",
        "predicate": predicate,
        "object_entity_id": "e2",
        "evidence": {"start_offset": 0, "end_offset": len(content)},
    }

    return {
        "dukr_schema": "datumor.dukr",
        "representation_id": f"dukr-{source_id}",
        "source": {
            "source_id": source_id,
            "project_id": "project-1",
            "filename": f"{source_id}.txt",
            "original_content": content,
        },
        "entities": entities,
        "relationships": [relationship],
        "semantics": {
            "statements": [{
                "statement_id": f"s-{source_id}",
                "text": statement,
                "epistemic_status": "observed",
                "evidence": {"start_offset": 0, "end_offset": len(content)},
            }]
        },
        "context": {"context_units": []},
        "knowledge_graph": {
            "nodes": [
                {"node_id": "e1"},
                {"node_id": "e2"},
            ],
            "edges": [{
                "edge_id": f"r-{source_id}",
                "subject_node_id": "e1",
                "object_node_id": "e2",
            }],
        },
    }


def test_empty_input_returns_empty_report():
    result = analyze_consistency([])

    assert result["summary"]["documents_analyzed"] == 0
    assert result["summary"]["findings_count"] == 0


def test_consistent_documents_produce_no_conflict_findings():
    result = analyze_consistency([
        make_dukr("source-1"),
        make_dukr("source-2"),
    ])

    assert result["summary"]["findings_count"] == 0


def test_entity_display_variance_is_reported_without_claiming_identity_conflict():
    result = analyze_consistency([
        make_dukr("source-1", entity_value="OpenAI"),
        make_dukr("source-2", entity_value="OPENAI"),
    ])

    findings = [
        item for item in result["findings"]
        if item["finding_type"] == "entity_representation_variance"
    ]

    assert len(findings) == 1
    assert findings[0]["severity"] == "low"
    assert "not proof" in findings[0]["description"]


def test_different_entity_types_are_not_grouped_together():
    first = make_dukr("source-1")
    second = make_dukr("source-2")
    second["entities"][0]["entity_type"] = "technology"

    result = analyze_consistency([first, second])

    assert not any(
        item["finding_type"] == "entity_representation_variance"
        for item in result["findings"]
    )


def test_relationship_object_disagreement_is_reported():
    first = make_dukr("source-1", object_value="artificial intelligence")
    second = make_dukr("source-2", object_value="machine learning")

    result = analyze_consistency([first, second])

    findings = [
        item for item in result["findings"]
        if item["finding_type"] == "relationship_object_disagreement"
    ]

    assert len(findings) == 1
    assert findings[0]["severity"] == "medium"
    assert len(findings[0]["evidence"]) == 2


def test_relationship_predicates_are_compared_separately():
    first = make_dukr("source-1", predicate="develops")
    second = make_dukr("source-2", predicate="uses")

    result = analyze_consistency([first, second])

    assert not any(
        item["finding_type"] == "relationship_object_disagreement"
        for item in result["findings"]
    )


def test_relationship_disagreement_with_same_source_is_not_cross_source():
    first = make_dukr("source-1", object_value="artificial intelligence")
    second = make_dukr("source-1", object_value="machine learning")

    result = analyze_consistency([first, second])

    assert not any(
        item["finding_type"] == "relationship_object_disagreement"
        for item in result["findings"]
    )


def test_opposing_semantic_statements_are_reported():
    first = make_dukr(
        "source-1",
        statement="OpenAI develops artificial intelligence.",
    )
    second = make_dukr(
        "source-2",
        statement="OpenAI does not develop artificial intelligence.",
    )

    result = analyze_consistency([first, second])

    findings = [
        item for item in result["findings"]
        if item["finding_type"] == "opposing_statement_polarity"
    ]

    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


def test_temporal_context_reduces_semantic_finding_severity():
    first = make_dukr(
        "source-1",
        statement="OpenAI develops artificial intelligence in 2024.",
    )
    second = make_dukr(
        "source-2",
        statement="OpenAI does not develop artificial intelligence in 2025.",
    )

    result = analyze_consistency([first, second])

    findings = [
        item for item in result["findings"]
        if item["finding_type"] == "opposing_statement_polarity"
    ]

    assert len(findings) == 1
    assert findings[0]["severity"] == "medium"


def test_structural_integrity_error_is_reported():
    document = make_dukr("source-1")
    document["knowledge_graph"]["edges"][0]["object_node_id"] = "missing"

    result = analyze_consistency([document])

    assert any(
        item["category"] == "structural"
        and item["severity"] == "high"
        for item in result["findings"]
    )


def test_findings_include_source_references_and_evidence():
    result = analyze_consistency([
        make_dukr("source-1", object_value="artificial intelligence"),
        make_dukr("source-2", object_value="machine learning"),
    ])

    finding = next(
        item for item in result["findings"]
        if item["category"] == "relationship"
    )

    assert finding["sources"][0]["source_id"] in {
        "source-1", "source-2"
    }
    assert finding["evidence"]
    assert finding["resolution_status"] == "unresolved"


def test_original_dukr_documents_are_not_modified():
    first = make_dukr("source-1")
    second = make_dukr("source-2", object_value="machine learning")

    original_first = repr(first)
    original_second = repr(second)

    analyze_consistency([first, second])

    assert repr(first) == original_first
    assert repr(second) == original_second


def test_duplicate_finding_ids_are_deterministic():
    documents = [
        make_dukr("source-1", entity_value="OpenAI"),
        make_dukr("source-2", entity_value="OPENAI"),
    ]

    first = analyze_consistency(documents)
    second = analyze_consistency(documents)

    assert [
        item["finding_id"] for item in first["findings"]
    ] == [
        item["finding_id"] for item in second["findings"]
    ]


def test_invalid_document_schema_is_rejected():
    with pytest.raises(ValueError, match="unsupported DUKR schema"):
        analyze_consistency([{"dukr_schema": "other"}])


def test_non_dictionary_document_is_rejected():
    with pytest.raises(TypeError):
        analyze_consistency([None])


def test_category_and_severity_counts_match_findings():
    result = analyze_consistency([
        make_dukr("source-1", object_value="artificial intelligence"),
        make_dukr("source-2", object_value="machine learning"),
    ])

    assert sum(
        result["summary"]["category_counts"].values()
    ) == result["summary"]["findings_count"]

    assert sum(
        result["summary"]["severity_counts"].values()
    ) == result["summary"]["findings_count"]
