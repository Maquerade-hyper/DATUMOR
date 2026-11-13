
import pytest

from apps.api.app.quality.quality_metrics import calculate_quality_metrics
from apps.api.app.understanding.dukr_generator import generate_dukr


CONTENT = "OpenAI develops artificial intelligence."


def make_dukr():
    extraction = {
        "format": "txt",
        "source_filename": "sample.txt",
        "content": CONTENT,
        "records": [],
        "metadata": {
            "source": {
                "source_id": "source-1",
                "project_id": "project-1",
                "filename": "sample.txt",
                "path": "sample.txt",
                "checksum_sha256": "a" * 64,
            }
        },
        "warnings": [],
    }
    entities = {
        "entities": [
            {
                "entity_id": "e1",
                "entity_type": "organization",
                "value": "OpenAI",
                "evidence": {"start_offset": 0, "end_offset": 6},
            },
            {
                "entity_id": "e2",
                "entity_type": "concept",
                "value": "artificial intelligence",
                "evidence": {"start_offset": 16, "end_offset": 39},
            },
        ]
    }
    semantics = {
        "facts": [{
            "statement_id": "f1",
            "text": CONTENT,
            "epistemic_status": "observed",
            "evidence": {"start_offset": 0, "end_offset": len(CONTENT)},
        }],
        "claims": [],
    }
    relationships = {
        "relationships": [{
            "relationship_id": "r1",
            "subject": {"entity_id": "e1"},
            "predicate": "develops",
            "object": {"entity_id": "e2"},
            "evidence": {"start_offset": 0, "end_offset": len(CONTENT)},
        }]
    }
    context = {
        "context_schema_version": "0.1.0",
        "context_units": [{
            "context_unit_id": "c1",
            "text": CONTENT,
            "entity_links": [{"entity_id": "e1"}, {"entity_id": "e2"}],
            "relationship_links": [{"relationship_id": "r1"}],
            "sentences": [{"sentence_id": "s1"}],
        }],
        "summary": {"context_unit_count": 1},
    }
    return generate_dukr(
        extraction, entities, semantics, relationships, context
    )


def test_returns_expected_metrics_schema():
    result = calculate_quality_metrics(make_dukr())

    assert result["metrics_schema"] == "datumor.quality_metrics"
    assert result["metrics_version"] == "0.1.0"
    assert result["representation_id"].startswith("dukr_")


def test_reports_all_six_quality_dimensions():
    result = calculate_quality_metrics(make_dukr())

    assert set(result["dimensions"]) == {
        "structural_integrity",
        "content_preservation",
        "evidence_coverage",
        "provenance_completeness",
        "semantic_linkage",
        "context_completeness",
    }


def test_complete_fixture_has_full_evidence_coverage():
    result = calculate_quality_metrics(make_dukr())

    dimension = result["dimensions"]["evidence_coverage"]
    assert dimension["score"] == 100.0
    assert dimension["details"]["artifacts_with_evidence"] == 4


def test_complete_fixture_has_full_provenance_coverage():
    result = calculate_quality_metrics(make_dukr())

    assert result["dimensions"]["provenance_completeness"]["score"] == 100.0


def test_complete_fixture_has_full_semantic_linkage():
    result = calculate_quality_metrics(make_dukr())

    assert result["dimensions"]["semantic_linkage"]["score"] == 100.0


def test_content_hash_and_reconstruction_are_measured():
    result = calculate_quality_metrics(make_dukr())
    details = result["dimensions"]["content_preservation"]["details"]

    assert details["exact_reconstruction"] is True
    assert details["content_hash_valid"] is True
    assert result["dimensions"]["content_preservation"]["score"] == 100.0


def test_missing_evidence_reduces_evidence_score():
    dukr = make_dukr()
    dukr["entities"][0]["evidence"] = {}

    result = calculate_quality_metrics(dukr)

    assert result["dimensions"]["evidence_coverage"]["score"] < 100.0


def test_missing_provenance_is_not_treated_as_complete():
    dukr = make_dukr()
    dukr["source"]["source_id"] = None
    dukr["source"]["checksum_sha256"] = None

    result = calculate_quality_metrics(dukr)

    assert result["dimensions"]["provenance_completeness"]["score"] == 60.0


def test_unresolved_relationship_reduces_semantic_linkage():
    dukr = make_dukr()
    dukr["relationships"][0]["object_entity_id"] = "missing"

    result = calculate_quality_metrics(dukr)

    assert result["dimensions"]["semantic_linkage"]["score"] == 50.0
    assert result["dimensions"]["structural_integrity"]["score"] < 100.0


def test_empty_optional_knowledge_is_not_given_false_evidence_score():
    extraction = {
        "format": "txt",
        "source_filename": "empty.txt",
        "content": "",
        "records": [],
        "metadata": {"source": {}},
        "warnings": [],
    }
    dukr = generate_dukr(extraction)
    result = calculate_quality_metrics(dukr)

    assert result["dimensions"]["evidence_coverage"]["score"] is None
    assert result["overall_score"] is not None
    assert result["overall_score"] < 100.0


def test_missing_context_is_not_given_full_context_score():
    dukr = make_dukr()
    dukr["context"]["context_units"] = []

    result = calculate_quality_metrics(dukr)

    assert result["dimensions"]["context_completeness"]["score"] < 100.0


def test_invalid_schema_is_rejected():
    with pytest.raises(ValueError, match="Unsupported DUKR schema"):
        calculate_quality_metrics({"dukr_schema": "other"})


def test_non_dictionary_input_is_rejected():
    with pytest.raises(TypeError):
        calculate_quality_metrics(None)


def test_counts_match_dukr_artifacts():
    result = calculate_quality_metrics(make_dukr())

    assert result["counts"]["entities"] == 2
    assert result["counts"]["relationships"] == 1
    assert result["counts"]["statements"] == 1
    assert result["counts"]["context_units"] == 1


def test_quality_score_is_bounded():
    result = calculate_quality_metrics(make_dukr())

    assert 0 <= result["overall_score"] <= 100


def test_weights_sum_to_one():
    result = calculate_quality_metrics(make_dukr())

    assert sum(result["weights"].values()) == pytest.approx(1.0)
