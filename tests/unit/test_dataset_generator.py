from copy import deepcopy

import pytest

from apps.api.app.transformation.profile_registry import get_profile
from apps.api.app.transformation.dataset_generator import generate_dataset


def base_dukr():
    return {
        "representation_id": "test-dukr",
        "source": {
            "source_id": "source-1",
            "project_id": None,
            "filename": "sample.txt",
            "checksum_sha256": "a" * 64,
            "source_records": [],
        },
        "entities": [],
        "semantics": {
            "facts": [
                {
                    "subject": "Python",
                    "predicate": "supports",
                    "object": "FastAPI",
                    "evidence_text": "Python supports FastAPI.",
                    "start_offset": 0,
                    "end_offset": 23,
                }
            ],
            "claims": [],
        },
        "relationships": [],
        "context": {
            "context_units": [
                {
                    "context_id": "context-1",
                    "text": "Python supports FastAPI.",
                    "start_offset": 0,
                    "end_offset": 23,
                }
            ]
        },
        "knowledge_graph": {"nodes": [], "edges": []},
    }


def test_general_llm_generates_grounded_examples():
    result = generate_dataset([base_dukr()], get_profile("general_llm"))

    assert result["summary"]["examples_generated"] == 1
    example = result["examples"][0]
    assert example["response"] == "Python supports FastAPI."
    assert example["provenance"]["source_id"] == "source-1"


def test_research_generates_evidence_backed_qa():
    result = generate_dataset([base_dukr()], get_profile("research"))

    example = result["examples"][0]
    assert "Python" in example["instruction"]
    assert example["response"] == "Python supports FastAPI."
    assert example["evidence"] == "Python supports FastAPI."


def test_coding_skips_unsupported_source_material():
    result = generate_dataset([base_dukr()], get_profile("coding"))

    assert result["summary"]["examples_generated"] == 0
    assert result["summary"]["examples_skipped"] == 1
    assert "does not invent code solutions" in result["skipped"][0]["reason"]


def test_coding_uses_explicit_instruction_response_records():
    dukr = base_dukr()
    dukr["source"]["source_records"] = [{
        "instruction": "Write a Python function that adds two numbers.",
        "response": "def add(a, b):\n    return a + b",
        "evidence": "Verified source training example.",
    }]

    result = generate_dataset([dukr], get_profile("coding"))

    assert result["summary"]["examples_generated"] == 1
    assert result["examples"][0]["response"].startswith("def add")


def test_retrieval_requires_entity_grounded_context():
    dukr = base_dukr()
    dukr["entities"] = [{
        "entity_type": "technology",
        "normalized_value": "Python",
        "value": "Python",
    }]

    result = generate_dataset([dukr], get_profile("retrieval"))

    assert result["summary"]["examples_generated"] == 1
    example = result["examples"][0]
    assert example["query"] == "What does the source say about Python?"
    assert example["positive"] == "Python supports FastAPI."


def test_retrieval_skips_context_without_matching_entities():
    result = generate_dataset([base_dukr()], get_profile("retrieval"))

    assert result["summary"]["examples_generated"] == 0
    assert result["summary"]["examples_skipped"] == 1


def test_explicit_general_records_are_preferred():
    dukr = base_dukr()
    dukr["source"]["source_records"] = [{
        "instruction": "Explain the documented behavior.",
        "response": "The source documents the behavior.",
    }]

    result = generate_dataset([dukr], get_profile("general_llm"))

    assert result["summary"]["examples_generated"] == 1
    assert result["examples"][0]["instruction"] == "Explain the documented behavior."


def test_duplicate_examples_are_removed():
    dukr = base_dukr()
    result = generate_dataset([dukr, dukr], get_profile("general_llm"))

    assert result["summary"]["examples_generated"] == 1
    assert result["summary"]["examples_skipped"] == 1


def test_generation_is_deterministic():
    dukr = base_dukr()
    first = generate_dataset([dukr], get_profile("general_llm"))
    second = generate_dataset([dukr], get_profile("general_llm"))

    assert first["examples"] == second["examples"]


def test_generation_does_not_mutate_dukr():
    dukr = base_dukr()
    original = deepcopy(dukr)

    generate_dataset([dukr], get_profile("general_llm"))

    assert dukr == original


def test_provenance_contains_source_evidence_and_offsets():
    result = generate_dataset([base_dukr()], get_profile("general_llm"))
    provenance = result["examples"][0]["provenance"]

    assert provenance["source_id"] == "source-1"
    assert provenance["evidence_text"] == "Python supports FastAPI."
    assert provenance["start_offset"] == 0
    assert provenance["end_offset"] == 23


def test_invalid_profile_is_rejected():
    profile = get_profile("general_llm")
    profile["quality_threshold"] = 5

    with pytest.raises(ValueError):
        generate_dataset([base_dukr()], profile)


def test_empty_documents_are_rejected():
    with pytest.raises(ValueError):
        generate_dataset([], get_profile("general_llm"))


def test_missing_source_is_rejected():
    with pytest.raises(ValueError):
        generate_dataset([{}], get_profile("general_llm"))


def test_generated_examples_contain_profile_required_fields():
    for profile_id in ("general_llm", "coding", "research", "retrieval"):
        dukr = base_dukr()

        if profile_id == "coding":
            dukr["source"]["source_records"] = [{
                "instruction": "Explain this code.",
                "response": "print('hello')",
            }]
        elif profile_id == "retrieval":
            dukr["entities"] = [{
                "normalized_value": "Python",
                "value": "Python",
            }]

        result = generate_dataset([dukr], get_profile(profile_id))

        for example in result["examples"]:
            for field in get_profile(profile_id)["required_fields"]:
                assert field in example
