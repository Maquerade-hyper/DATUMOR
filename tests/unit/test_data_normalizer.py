from copy import deepcopy
import hashlib

import pytest

from apps.api.app.transformation.profile_registry import get_profile
from apps.api.app.transformation.data_normalizer import normalize_dukr


@pytest.fixture
def sample_dukr():
    content = "Hello  world.\r\n\r\n\r\nGoodbye.  \r\n"
    return {
        "dukr_schema": "datumor.dukr",
        "dukr_schema_version": "1.0.0",
        "representation_id": "normalization-test",
        "source": {
            "source_id": "source-123",
            "project_id": None,
            "filename": "sample.txt",
            "checksum_sha256": "a" * 64,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "original_content": content,
            "source_records": [
                {"question": "  What  is this?  ", "answer": "  A test.  "}
            ],
        },
        "entities": [],
        "semantics": {},
        "relationships": [],
        "context": {"context_units": []},
        "knowledge_graph": {"nodes": [], "edges": []},
    }


def test_conservative_normalization(sample_dukr):
    profile = get_profile("general_llm")
    result = normalize_dukr(sample_dukr, profile)

    expected = "Hello  world." + chr(10) * 3 + "Goodbye." + chr(10)
    assert result["normalized_data"]["content"] == expected
    assert result["source"]["source_id"] == "source-123"
    assert result["profile"]["normalization_mode"] == "conservative"
def test_standard_normalization_collapses_whitespace(sample_dukr):
    profile = get_profile("general_llm")
    profile["normalization"]["mode"] = "standard"

    result = normalize_dukr(sample_dukr, profile)

    expected = "Hello world." + chr(10) * 2 + "Goodbye." + chr(10)
    assert result["normalized_data"]["content"] == expected
def test_none_mode_preserves_content(sample_dukr):
    profile = get_profile("general_llm")
    profile["normalization"]["mode"] = "none"

    result = normalize_dukr(sample_dukr, profile)

    assert result["normalized_data"]["content"] == (
        sample_dukr["source"]["original_content"]
    )
    assert result["change_summary"]["changed"] is False


def test_unicode_is_normalized_to_nfc(sample_dukr):
    sample_dukr["source"]["original_content"] = "Cafe" + chr(0x301)
    profile = get_profile("general_llm")

    result = normalize_dukr(sample_dukr, profile)

    assert result["normalized_data"]["content"] == "Caf" + chr(0xE9)
    assert "unicode_nfc" in result["change_summary"]["operations"]
def test_original_dukr_is_never_mutated(sample_dukr):
    original = deepcopy(sample_dukr)

    normalize_dukr(sample_dukr, get_profile("general_llm"))

    assert sample_dukr == original


def test_source_identity_and_hashes_are_preserved(sample_dukr):
    result = normalize_dukr(sample_dukr, get_profile("general_llm"))

    assert result["source"]["source_id"] == sample_dukr["source"]["source_id"]
    assert result["integrity"]["source_checksum_preserved"] == (
        sample_dukr["source"]["checksum_sha256"]
    )
    assert result["integrity"]["source_content_hash_preserved"] == (
        sample_dukr["source"]["content_sha256"]
    )


def test_change_log_contains_before_and_after_hashes(sample_dukr):
    result = normalize_dukr(sample_dukr, get_profile("general_llm"))

    assert result["changes"]
    for change in result["changes"]:
        assert len(change["before_sha256"]) == 64
        assert len(change["after_sha256"]) == 64
        assert change["changed"] is True


def test_code_whitespace_is_not_collapsed_in_standard_mode(sample_dukr):
    sample_dukr["source"]["source_records"] = [
        {"code": "def  f():\r\n    return  1  "}
    ]
    profile = get_profile("coding")
    profile["normalization"]["mode"] = "standard"

    result = normalize_dukr(sample_dukr, profile)

    assert result["normalized_data"]["records"][0]["code"] == (
        "def  f():\n    return  1"
    )


def test_invalid_profile_is_rejected(sample_dukr):
    profile = get_profile("general_llm")
    profile["normalization"]["mode"] = "unsafe"

    with pytest.raises(ValueError):
        normalize_dukr(sample_dukr, profile)


def test_missing_source_is_rejected():
    with pytest.raises(ValueError):
        normalize_dukr({}, get_profile("general_llm"))


def test_non_string_content_is_rejected(sample_dukr):
    sample_dukr["source"]["original_content"] = {"invalid": "content"}

    with pytest.raises(ValueError):
        normalize_dukr(sample_dukr, get_profile("general_llm"))


def test_record_fields_are_normalized(sample_dukr):
    result = normalize_dukr(sample_dukr, get_profile("general_llm"))

    record = result["normalized_data"]["records"][0]
    assert record["question"] == "  What  is this?"
    assert record["answer"] == "  A test."


def test_report_identifies_profile_version(sample_dukr):
    result = normalize_dukr(sample_dukr, get_profile("research"))

    assert result["profile"]["profile_id"] == "research"
    assert result["profile"]["profile_version"] == "1.0.0"


def test_empty_source_records_are_supported(sample_dukr):
    sample_dukr["source"]["source_records"] = []

    result = normalize_dukr(sample_dukr, get_profile("general_llm"))

    assert result["normalized_data"]["records"] == []
