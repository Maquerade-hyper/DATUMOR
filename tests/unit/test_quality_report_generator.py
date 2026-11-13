import copy
import json

import pytest

from apps.api.app.quality import quality_report_generator as generator


@pytest.fixture
def sample_dukr():
    return {
        "dukr_schema": "datumor.dukr",
        "dukr_schema_version": "1.0.0",
        "representation_id": "test-representation",
        "source": {
            "source_id": "test-source",
            "filename": "sample.txt",
            "checksum_sha256": "a" * 64,
            "original_content": "Sample source content.",
            "content_sha256": "a" * 64,
        },
        "entities": [],
        "semantics": {},
        "relationships": [],
        "context": {"context_units": []},
        "knowledge_graph": {"nodes": [], "edges": []},
    }


def test_report_combines_all_quality_engines(monkeypatch, sample_dukr):
    monkeypatch.setattr(generator, "calculate_quality_metrics",
                        lambda d: {"overall_score": 85})
    monkeypatch.setattr(generator, "validate_dukr",
                        lambda d: {"valid": True, "errors": []})
    monkeypatch.setattr(generator, "detect_duplicates",
                        lambda docs, near_duplicate_threshold=0.90:
                        {"groups": [], "findings": []})
    monkeypatch.setattr(generator, "analyze_consistency",
                        lambda docs: {"findings": []})
    monkeypatch.setattr(generator, "verify_provenance",
                        lambda docs: {
                            "status": "verified",
                            "summary": {
                                "documents_assessed": 1,
                                "total_findings": 1,
                                "verified": 1,
                                "failed": 0,
                                "unverifiable": 0,
                            },
                            "findings": [],
                        })

    report = generator.generate_quality_report([sample_dukr])

    assert report["report_type"] == "datumor.quality_report"
    assert report["status"] == "completed"
    assert report["documents"][0]["quality_metrics"]["overall_score"] == 85
    assert report["documents"][0]["dukr_validation"]["valid"] is True
    assert report["automatic_changes_made"] is False


def test_failed_provenance_fails_report(monkeypatch, sample_dukr):
    monkeypatch.setattr(generator, "calculate_quality_metrics", lambda d: {})
    monkeypatch.setattr(generator, "validate_dukr", lambda d: {"valid": True})
    monkeypatch.setattr(generator, "detect_duplicates", lambda docs, near_duplicate_threshold=0.90: {"groups": []})
    monkeypatch.setattr(generator, "analyze_consistency", lambda docs: {"findings": []})
    monkeypatch.setattr(generator, "verify_provenance", lambda docs: {
        "status": "failed",
        "summary": {"failed": 1, "unverifiable": 0, "verified": 0},
        "findings": [],
    })

    report = generator.generate_quality_report([sample_dukr])
    assert report["status"] == "failed"


def test_unverifiable_provenance_makes_report_incomplete(monkeypatch, sample_dukr):
    monkeypatch.setattr(generator, "calculate_quality_metrics", lambda d: {})
    monkeypatch.setattr(generator, "validate_dukr", lambda d: {"valid": True})
    monkeypatch.setattr(generator, "detect_duplicates", lambda docs, near_duplicate_threshold=0.90: {"groups": []})
    monkeypatch.setattr(generator, "analyze_consistency", lambda docs: {"findings": []})
    monkeypatch.setattr(generator, "verify_provenance", lambda docs: {
        "status": "incomplete",
        "summary": {"failed": 0, "unverifiable": 1, "verified": 0},
        "findings": [],
    })

    report = generator.generate_quality_report([sample_dukr])
    assert report["status"] == "incomplete"


def test_report_rejects_empty_documents():
    with pytest.raises(ValueError):
        generator.generate_quality_report([])


def test_report_rejects_invalid_threshold(sample_dukr):
    with pytest.raises(ValueError):
        generator.generate_quality_report([sample_dukr], 1.5)


def test_markdown_contains_quality_sections():
    report = {
        "status": "completed",
        "generated_at": "2026-11-11T00:00:00+00:00",
        "summary": {"documents_assessed": 1},
        "documents": [],
        "provenance_verification": {"status": "verified", "summary": {}},
        "automatic_changes_made": False,
    }

    markdown = generator.render_quality_report_markdown(report)

    assert "# DATUMOR Quality Report" in markdown
    assert "## Provenance" in markdown
    assert "## Integrity statement" in markdown


def test_export_writes_json_and_markdown(tmp_path):
    report = {
        "report_type": "datumor.quality_report",
        "version": "1.0.0",
        "status": "completed",
        "summary": {},
        "documents": [],
        "duplicate_analysis": {},
        "consistency_analysis": {},
        "provenance_verification": {},
        "automatic_changes_made": False,
    }

    paths = generator.export_quality_report(report, str(tmp_path))

    json_path = tmp_path / "quality_report.json"
    markdown_path = tmp_path / "quality_report.md"

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "completed"
    assert "# DATUMOR Quality Report" in markdown_path.read_text(encoding="utf-8")
    assert paths["json_path"] == str(json_path.resolve())


def test_generation_does_not_mutate_dukr(monkeypatch, sample_dukr):
    original = copy.deepcopy(sample_dukr)

    monkeypatch.setattr(generator, "calculate_quality_metrics", lambda d: {})
    monkeypatch.setattr(generator, "validate_dukr", lambda d: {"valid": True})
    monkeypatch.setattr(generator, "detect_duplicates", lambda docs, near_duplicate_threshold=0.90: {"groups": []})
    monkeypatch.setattr(generator, "analyze_consistency", lambda docs: {"findings": []})
    monkeypatch.setattr(generator, "verify_provenance", lambda docs: {
        "status": "verified",
        "summary": {"failed": 0, "unverifiable": 0, "verified": 0},
        "findings": [],
    })

    generator.generate_quality_report([sample_dukr])
    assert sample_dukr == original
