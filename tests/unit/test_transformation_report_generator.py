import json

import pytest

from apps.api.app.transformation.profile_registry import get_profile
from apps.api.app.transformation.transformation_report_generator import (
    generate_transformation_report,
    render_transformation_report_markdown,
    export_transformation_report,
)


def sample_dataset():
    return {
        "report_type": "datumor.generated_dataset",
        "status": "completed",
        "profile": {
            "profile_id": "general_llm",
            "profile_version": "1.0.0",
        },
        "summary": {"examples_generated": 1},
        "examples": [{
            "example_id": "example-1",
            "instruction": "Explain Python.",
            "response": "Python is a programming language.",
            "provenance": {
                "source_id": "source-1",
                "evidence_text": "Python is a programming language.",
            },
        }],
        "skipped": [
            {"reason": "missing_instruction"},
            {"reason": "missing_instruction"},
            {"reason": "unsupported_record"},
        ],
        "warnings": [],
    }


def test_report_counts_and_profile():
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    assert report["status"] == "incomplete"
    assert report["summary"]["examples_generated"] == 1
    assert report["summary"]["examples_skipped"] == 3
    assert report["profile"]["profile_id"] == "general_llm"


def test_skip_reasons_are_counted():
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    assert report["skip_reasons"] == {
        "missing_instruction": 2,
        "unsupported_record": 1,
    }


def test_provenance_coverage():
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    assert report["provenance"]["examples_with_source_id"] == 1
    assert report["provenance"]["examples_with_evidence"] == 1
    assert report["source_ids"] == ["source-1"]


def test_quality_is_not_invented():
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    assert report["quality"]["assessment_status"] == "not_assessed"
    assert report["quality"]["report"] is None


def test_supplied_quality_report_is_preserved():
    quality = {"status": "completed", "overall_score": 0.92}
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm"),
        quality_report=quality,
    )

    assert report["quality"]["report"] == quality


def test_empty_dataset_is_reported_explicitly():
    dataset = sample_dataset()
    dataset["examples"] = []
    dataset["skipped"] = []

    report = generate_transformation_report(
        dataset, get_profile("general_llm")
    )

    assert report["summary"]["empty_output"] is True
    assert report["summary"]["examples_generated"] == 0
    assert report["status"] == "completed"


def test_serialization_reports_are_included():
    serialization = {
        "status": "completed",
        "output": {
            "format": "jsonl",
            "path": "dataset.jsonl",
            "size_bytes": 100,
            "sha256": "abc123",
        },
        "summary": {"examples_serialized": 1},
        "integrity": {"sha256_verified": True},
    }

    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm"),
        serialization_reports=[serialization],
    )

    assert report["exports"]["exports_completed"] == 1
    assert report["exports"]["exports"][0]["format"] == "jsonl"


def test_failed_export_makes_report_incomplete():
    failed = {"status": "failed", "output": {}, "summary": {}, "integrity": {}}

    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm"),
        serialization_reports=[failed],
    )

    assert report["status"] == "incomplete"
    assert report["exports"]["exports_failed"] == 1


def test_markdown_contains_report_sections():
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    markdown = render_transformation_report_markdown(report)

    assert "# DATUMOR Transformation Report" in markdown
    assert "## Provenance" in markdown
    assert "## Exports" in markdown
    assert "not assessed" in markdown.lower()


def test_json_and_markdown_exports(tmp_path):
    report = generate_transformation_report(
        sample_dataset(), get_profile("general_llm")
    )

    result = export_transformation_report(report, tmp_path)

    json_path = tmp_path / "transformation_report.json"
    md_path = tmp_path / "transformation_report.md"

    assert result["status"] == "completed"
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_type"] == (
        "datumor.transformation_report"
    )
    assert "# DATUMOR Transformation Report" in md_path.read_text(encoding="utf-8")
    assert result["json_sha256"]
    assert result["markdown_sha256"]


def test_profile_mismatch_is_rejected():
    with pytest.raises(ValueError, match="profile"):
        generate_transformation_report(
            sample_dataset(), get_profile("coding")
        )


def test_invalid_dataset_type_is_rejected():
    with pytest.raises(ValueError, match="report_type"):
        generate_transformation_report(
            {"examples": []}, get_profile("general_llm")
        )


def test_source_dataset_is_not_modified():
    import copy

    dataset = sample_dataset()
    original = copy.deepcopy(dataset)

    generate_transformation_report(dataset, get_profile("general_llm"))

    assert dataset == original
