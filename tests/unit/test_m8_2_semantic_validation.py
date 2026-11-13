import copy

from apps.api.app.validation.semantic_validation import (
    validate_dukr_semantics,
    validate_dataset_semantics,
)


def make_dukr():
    content = "DATUMOR prepares reliable training data."
    return {
        "source": {
            "source_id": "source-001",
            "original_content": content,
        },
        "entities": [
            {
                "entity_id": "entity-001",
                "value": "DATUMOR",
                "start_offset": 0,
                "end_offset": 7,
            }
        ],
        "semantics": {
            "facts": [
                {
                    "fact_id": "fact-001",
                    "evidence": "reliable training data",
                }
            ],
            "claims": [
                {
                    "claim_id": "claim-001",
                    "evidence": "prepares reliable training data",
                }
            ],
        },
        "relationships": [
            {
                "relationship_id": "relationship-001",
                "subject_entity_id": "entity-001",
                "object_entity_id": "entity-001",
                "evidence": "DATUMOR",
            }
        ],
        "context": {
            "context_units": [
                {
                    "text": content,
                    "entity_links": [{"entity_id": "entity-001"}],
                    "relationship_links": [
                        {"relationship_id": "relationship-001"}
                    ],
                }
            ]
        },
    }


def test_valid_dukr_semantics_pass():
    report = validate_dukr_semantics(make_dukr())
    assert report["valid"], report
    assert report["entity_count"] == 1
    assert report["fact_count"] == 1
    assert report["claim_count"] == 1


def test_ungrounded_fact_is_rejected():
    dukr = make_dukr()
    dukr["semantics"]["facts"][0]["evidence"] = "This is invented evidence."

    report = validate_dukr_semantics(dukr)
    assert not report["valid"]
    assert any(
        item["code"] == "EVIDENCE_NOT_GROUNDED"
        for item in report["errors"]
    )


def test_invalid_entity_reference_is_rejected():
    dukr = make_dukr()
    dukr["relationships"][0]["object_entity_id"] = "missing-entity"

    report = validate_dukr_semantics(dukr)
    assert not report["valid"]
    assert any(
        item["code"] == "RELATIONSHIP_ENTITY_REFERENCE_UNRESOLVED"
        for item in report["errors"]
    )


def test_invalid_context_reference_is_rejected():
    dukr = make_dukr()
    dukr["context"]["context_units"][0]["entity_links"] = [
        {"entity_id": "missing-entity"}
    ]

    report = validate_dukr_semantics(dukr)
    assert not report["valid"]
    assert any(
        item["code"] == "CONTEXT_ENTITY_REFERENCE_UNRESOLVED"
        for item in report["errors"]
    )


def test_wrong_evidence_offsets_are_rejected():
    dukr = make_dukr()
    dukr["entities"][0]["start_offset"] = 1
    dukr["entities"][0]["end_offset"] = 8

    report = validate_dukr_semantics(dukr)
    assert not report["valid"]
    assert any(
        item["code"] == "EVIDENCE_OFFSET_MISMATCH"
        for item in report["errors"]
    )


def test_missing_evidence_is_warning_not_false_pass_claim():
    dukr = make_dukr()
    dukr["semantics"]["facts"][0].pop("evidence")

    report = validate_dukr_semantics(dukr)
    assert report["valid"]
    assert any(
        item["code"] == "EVIDENCE_MISSING"
        for item in report["warnings"]
    )


def test_dukr_input_is_not_mutated():
    dukr = make_dukr()
    before = copy.deepcopy(dukr)

    validate_dukr_semantics(dukr)

    assert dukr == before


def make_dataset(evidence="reliable training data"):
    return {
        "report_type": "datumor.generated_dataset",
        "examples": [
            {
                "example_id": "example-001",
                "instruction": "What does the source prepare?",
                "response": "Reliable training data.",
                "provenance": {
                    "source_id": "source-001",
                    "evidence_text": evidence,
                },
            }
        ],
    }


def test_grounded_dataset_example_passes():
    report = validate_dataset_semantics(make_dataset(), [make_dukr()])
    assert report["valid"], report
    assert report["example_count"] == 1
    assert report["source_count"] == 1


def test_dataset_example_with_invented_evidence_fails():
    report = validate_dataset_semantics(
        make_dataset("invented source evidence"),
        [make_dukr()],
    )
    assert not report["valid"]
    assert any(
        item["code"] == "DATASET_EVIDENCE_NOT_GROUNDED"
        for item in report["errors"]
    )


def test_dataset_example_with_unknown_source_fails():
    dataset = make_dataset()
    dataset["examples"][0]["provenance"]["source_id"] = "unknown-source"

    report = validate_dataset_semantics(dataset, [make_dukr()])
    assert not report["valid"]
    assert any(
        item["code"] == "DATASET_SOURCE_UNRESOLVED"
        for item in report["errors"]
    )


def test_dataset_input_is_not_mutated():
    dataset = make_dataset()
    before = copy.deepcopy(dataset)

    validate_dataset_semantics(dataset, [make_dukr()])

    assert dataset == before


def test_dataset_evidence_offset_mismatch_fails():
    dataset = make_dataset()
    dataset["examples"][0]["provenance"].update({
        "start_offset": 0,
        "end_offset": 10,
    })

    report = validate_dataset_semantics(dataset, [make_dukr()])
    assert not report["valid"]
    assert any(
        item["code"] == "DATASET_EVIDENCE_OFFSET_MISMATCH"
        for item in report["errors"]
    )
