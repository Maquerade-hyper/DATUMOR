from apps.api.app.understanding.semantic_understander import (
    understand_semantics,
)


def sample():
    content = (
        "DATUMOR uses Python and FastAPI for software engineering. "
        "The project uses artificial intelligence to prepare datasets. "
        "The review is scheduled for 2026-11-11. "
        "Please configure the database before deployment."
    )
    return {
        "format": "text",
        "source_filename": "semantic-sample.txt",
        "content": content,
        "records": [],
        "metadata": {
            "source": {
                "checksum_sha256": "a" * 64,
                "path": "semantic-sample.txt",
            }
        },
        "warnings": [],
    }


def test_semantic_output_has_required_sections():
    result = understand_semantics(sample())
    for key in (
        "source", "overview", "subjects", "topics",
        "classifications", "intents", "facts",
        "claims", "summary", "warnings",
    ):
        assert key in result


def test_detects_software_and_ai_topics():
    result = understand_semantics(sample())
    topics = {item["topic"] for item in result["topics"]}
    assert "software_engineering" in topics
    assert "artificial_intelligence" in topics


def test_detects_instructional_and_scheduling_intents():
    result = understand_semantics(sample())
    intents = {item["intent"] for item in result["intents"]}
    assert "instructional" in intents
    assert "scheduling" in intents


def test_preserves_source_identity():
    result = understand_semantics(sample())
    assert result["source"]["filename"] == "semantic-sample.txt"
    assert result["source"]["checksum_sha256"] == "a" * 64


def test_observed_and_inferred_are_distinguished():
    result = understand_semantics(sample())
    assert result["overview"]["epistemic_status"] == "inferred"
    assert all(
        item["epistemic_status"] == "observed"
        for item in result["facts"]
    )


def test_fact_evidence_offsets_are_exact():
    extraction = sample()
    result = understand_semantics(extraction)

    for fact in result["facts"]:
        evidence = fact["evidence"]
        start = evidence["start_offset"]
        end = evidence["end_offset"]
        assert extraction["content"][start:end] == evidence["matched_text"]


def test_claims_retain_source_evidence():
    result = understand_semantics(sample())
    assert result["claims"]
    assert all(
        claim["claim_type"] == "source_assertion"
        and claim["evidence"]["text"] == claim["text"]
        for claim in result["claims"]
    )


def test_empty_content_is_handled():
    extraction = sample()
    extraction["content"] = ""
    result = understand_semantics(extraction)
    assert result["summary"]["sentence_count"] == 0
    assert result["facts"] == []
    assert result["claims"] == []


def test_invalid_input_is_rejected():
    try:
        understand_semantics({"content": None})
    except ValueError:
        return
    raise AssertionError("Expected ValueError for missing string content.")


def test_supplied_entities_are_used():
    extraction = sample()
    supplied = {
        "entities": [{
            "entity_id": "entity-1",
            "entity_type": "technology",
            "value": "Python",
            "normalized_value": "python",
        }]
    }
    result = understand_semantics(extraction, supplied)
    assert "python" in result["subjects"]["observed_entities"]
    assert "entity-1" in result["facts"][0]["evidence"]["entity_ids"]


def test_summary_counts_are_consistent():
    result = understand_semantics(sample())
    summary = result["summary"]
    assert summary["fact_count"] == len(result["facts"])
    assert summary["claim_count"] == len(result["claims"])
    assert summary["topic_count"] == len(result["topics"])
