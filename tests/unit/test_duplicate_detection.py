import pytest

from apps.api.app.quality.duplicate_detector import detect_duplicates


def dukr(
    content,
    source_id,
    project_id="project-1",
    filename=None,
    representation_id=None,
):
    return {
        "dukr_schema": "datumor.dukr",
        "dukr_schema_version": "1.0.0",
        "representation_id": representation_id or f"dukr-{source_id}",
        "source": {
            "source_id": source_id,
            "project_id": project_id,
            "filename": filename or f"{source_id}.txt",
            "path": f"data/{source_id}.txt",
            "checksum_sha256": None,
            "original_content": content,
        },
    }


def test_exact_duplicates_are_detected():
    result = detect_duplicates([
        dukr("OpenAI builds AI systems.", "source-1"),
        dukr("OpenAI builds AI systems.", "source-2"),
    ])

    assert result["summary"]["exact_matches"] == 1
    assert result["matches"][0]["detection_method"] == "exact"
    assert result["matches"][0]["similarity"] == 1.0


def test_normalized_duplicates_ignore_case_punctuation_and_whitespace():
    result = detect_duplicates([
        dukr("OpenAI builds AI systems.", "source-1"),
        dukr("  OPENAI   builds, AI systems!  ", "source-2"),
    ])

    assert result["summary"]["normalized_matches"] == 1
    assert result["matches"][0]["detection_method"] == "normalized"


def test_near_duplicates_are_detected():
    result = detect_duplicates([
        dukr(
            "OpenAI develops advanced artificial intelligence systems "
            "for developers around the world.",
            "source-1",
        ),
        dukr(
            "OpenAI develops advanced artificial intelligence systems "
            "for developers around the world today.",
            "source-2",
        ),
    ])

    assert result["summary"]["near_duplicate_matches"] == 1
    assert result["matches"][0]["review_required"] is True
    assert result["matches"][0]["similarity"] >= 0.90


def test_unrelated_documents_are_not_duplicates():
    result = detect_duplicates([
        dukr("The weather is sunny today.", "source-1"),
        dukr("Database transactions require atomicity.", "source-2"),
    ])

    assert result["summary"]["duplicate_pairs"] == 0
    assert result["groups"] == []


def test_cross_source_detection_is_reported():
    result = detect_duplicates([
        dukr("Same content.", "source-1", "project-1"),
        dukr("Same content.", "source-2", "project-2"),
    ])

    assert result["matches"][0]["cross_source"] is True
    assert result["matches"][0]["same_project"] is False


def test_same_source_representations_are_not_compared():
    result = detect_duplicates([
        dukr("Same content.", "source-1", representation_id="dukr-a"),
        dukr("Same content.", "source-1", representation_id="dukr-b"),
    ])

    assert result["summary"]["duplicate_pairs"] == 0


def test_multiple_matches_are_grouped():
    result = detect_duplicates([
        dukr("Identical content for duplicate grouping.", "source-1"),
        dukr("Identical content for duplicate grouping.", "source-2"),
        dukr("Identical content for duplicate grouping.", "source-3"),
    ])

    assert result["summary"]["duplicate_pairs"] == 3
    assert result["summary"]["duplicate_groups"] == 1
    assert result["groups"][0]["document_count"] == 3


def test_originals_are_never_modified():
    documents = [
        dukr("Keep this original.", "source-1"),
        dukr("Keep this original.", "source-2"),
    ]
    before = [item["source"]["original_content"] for item in documents]

    result = detect_duplicates(documents)

    after = [item["source"]["original_content"] for item in documents]
    assert before == after
    assert result["summary"]["originals_modified"] is False


def test_empty_document_collection_is_supported():
    result = detect_duplicates([])

    assert result["summary"]["documents_analyzed"] == 0
    assert result["summary"]["duplicate_pairs"] == 0


def test_empty_documents_are_exact_duplicates():
    result = detect_duplicates([
        dukr("", "source-1"),
        dukr("", "source-2"),
    ])

    assert result["summary"]["exact_matches"] == 1


def test_invalid_threshold_is_rejected():
    with pytest.raises(ValueError):
        detect_duplicates([], near_duplicate_threshold=0)

    with pytest.raises(ValueError):
        detect_duplicates([], near_duplicate_threshold=1.1)


def test_invalid_dukr_schema_is_rejected():
    with pytest.raises(ValueError, match="unsupported DUKR schema"):
        detect_duplicates([{"dukr_schema": "other"}])


def test_missing_source_content_is_rejected():
    with pytest.raises(ValueError, match="original_content"):
        detect_duplicates([{
            "dukr_schema": "datumor.dukr",
            "source": {},
        }])


def test_non_string_content_is_rejected():
    with pytest.raises(ValueError, match="original_content"):
        detect_duplicates([{
            "dukr_schema": "datumor.dukr",
            "source": {"original_content": None},
        }])


def test_document_limit_is_enforced():
    documents = [
        dukr("content", f"source-{index}")
        for index in range(501)
    ]

    with pytest.raises(ValueError, match="At most"):
        detect_duplicates(documents)


def test_report_preserves_source_references():
    result = detect_duplicates([
        dukr("Trace this source.", "source-1", filename="one.txt"),
        dukr("Trace this source.", "source-2", filename="two.txt"),
    ])

    match = result["matches"][0]
    assert match["left"]["source_id"] == "source-1"
    assert match["right"]["source_id"] == "source-2"
    assert match["left"]["filename"] == "one.txt"
    assert match["right"]["filename"] == "two.txt"
    assert match["duplicate_group_id"]


def test_threshold_can_be_configured():
    documents = [
        dukr(
            "The system processes documents and preserves their source "
            "identities for reliable AI dataset preparation.",
            "source-1",
        ),
        dukr(
            "The system processes documents and preserves their source "
            "identities for reliable AI dataset preparation today.",
            "source-2",
        ),
    ]

    strict = detect_duplicates(
        documents, near_duplicate_threshold=0.999
    )
    relaxed = detect_duplicates(
        documents, near_duplicate_threshold=0.80
    )

    assert relaxed["summary"]["duplicate_pairs"] >= (
        strict["summary"]["duplicate_pairs"]
    )
