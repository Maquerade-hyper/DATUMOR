import hashlib

from apps.api.app.quality.provenance_verifier import verify_provenance


def make_dukr(content):
    return {
        "source": {
            "source_id": "source-001",
            "checksum_sha256": hashlib.sha256(content.encode()).hexdigest(),
        },
        "original_content": content,
        "entities": [{
            "entity_id": "entity-001",
            "value": "FastAPI",
            "evidence_text": "FastAPI",
            "start_offset": content.index("FastAPI"),
            "end_offset": content.index("FastAPI") + len("FastAPI"),
            "provenance": {"source_id": "source-001"},
        }],
        "relationships": [],
        "semantics": {"facts": [], "claims": []},
        "context": {"context_units": []},
    }


def test_valid_source_and_entity_evidence_are_verified():
    result = verify_provenance([make_dukr("Built with FastAPI.")])
    assert result["status"] == "verified"
    assert result["summary"]["failed"] == 0
    assert result["summary"]["unverifiable"] == 0


def test_checksum_mismatch_fails():
    dukr = make_dukr("Built with FastAPI.")
    dukr["source"]["checksum_sha256"] = "0" * 64
    result = verify_provenance([dukr])
    assert result["status"] == "failed"


def test_evidence_mismatch_fails():
    dukr = make_dukr("Built with FastAPI.")
    dukr["entities"][0]["evidence_text"] = "Django"
    result = verify_provenance([dukr])
    assert result["status"] == "failed"


def test_invalid_offsets_fail():
    dukr = make_dukr("Built with FastAPI.")
    dukr["entities"][0]["start_offset"] = -1
    result = verify_provenance([dukr])
    assert result["status"] == "failed"


def test_missing_checksum_is_unverifiable():
    dukr = make_dukr("Built with FastAPI.")
    del dukr["source"]["checksum_sha256"]
    result = verify_provenance([dukr])
    assert result["status"] == "incomplete"
    assert result["summary"]["unverifiable"] > 0


def test_missing_offsets_are_not_counted_as_verified():
    dukr = make_dukr("Built with FastAPI.")
    del dukr["entities"][0]["start_offset"]
    result = verify_provenance([dukr])
    assert result["status"] == "incomplete"


def test_wrong_source_reference_fails():
    dukr = make_dukr("Built with FastAPI.")
    dukr["entities"][0]["provenance"]["source_id"] = "other-source"
    result = verify_provenance([dukr])
    assert result["status"] == "failed"


def test_original_dukr_is_not_modified():
    dukr = make_dukr("Built with FastAPI.")
    before = repr(dukr)
    verify_provenance([dukr])
    assert repr(dukr) == before


def test_empty_input_is_valid_empty_report():
    result = verify_provenance([])
    assert result["status"] == "verified"
    assert result["summary"]["documents_assessed"] == 0


def test_invalid_input_type_is_rejected():
    try:
        verify_provenance({})
    except TypeError:
        return
    raise AssertionError("Expected TypeError")
