
import pytest

from apps.api.app.optimization.optimization_report import (
    OptimizationReportEngine,
    OptimizationReportError,
    export_optimization_markdown,
    export_optimization_report,
    load_optimization_report,
    render_optimization_markdown,
    validate_optimization_report,
)


def complete_inputs():
    return {
        "tokenization": {
            "status": "completed",
            "summary": {"total_tokens": 120, "tokenizer": "test-tokenizer"},
            "tokenizer_fingerprint": "tokenizer-hash",
        },
        "chunking": {
            "status": "completed",
            "summary": {"chunk_count": 4},
            "chunk_size": 512,
            "overlap": 64,
        },
        "embedding": {
            "status": "completed",
            "provider": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dimensions": 768,
            },
            "summary": {"embedded_chunks": 4, "dimensions": 768},
        },
        "indexing": {
            "status": "completed",
            "collection": "datumor-test-768",
            "indexed_points": 4,
            "idempotent": True,
        },
        "validation": {
            "status": "completed",
            "valid": True,
            "errors": [],
        },
    }


def test_generates_complete_report():
    report = OptimizationReportEngine().generate(
        **complete_inputs(),
        dataset_id="dataset-001",
        profile="general_llm",
    )

    assert report["status"] == "completed"
    assert report["readiness"] == "ready"
    assert report["summary"]["token_count"] == 120
    assert report["summary"]["chunk_count"] == 4
    assert report["summary"]["embedded_chunks"] == 4
    assert report["summary"]["indexed_points"] == 4
    assert validate_optimization_report(report)["valid"]


def test_optional_embedding_and_indexing_can_be_skipped():
    inputs = complete_inputs()
    inputs["embedding"] = None
    inputs["indexing"] = None

    report = OptimizationReportEngine().generate(**inputs)

    assert report["readiness"] == "ready"
    assert report["operations"]["embedding"]["status"] == "skipped"
    assert report["operations"]["indexing"]["status"] == "skipped"
    assert "embedding" in report["skipped_operations"]
    assert "indexing" in report["skipped_operations"]


def test_failed_operation_prevents_readiness():
    inputs = complete_inputs()
    inputs["embedding"] = {"status": "failed", "warnings": ["Provider unavailable"]}

    report = OptimizationReportEngine().generate(**inputs)

    assert report["readiness"] == "not_ready"
    assert "embedding" in report["failed_operations"]
    assert report["warnings"]


def test_validation_failure_prevents_readiness():
    inputs = complete_inputs()
    inputs["validation"]["valid"] = False
    inputs["validation"]["errors"] = ["Invalid dataset"]

    report = OptimizationReportEngine().generate(**inputs)

    assert report["readiness"] == "not_ready"
    assert "validation" in report["failed_operations"]


def test_missing_core_operation_prevents_readiness():
    inputs = complete_inputs()
    inputs["chunking"] = None

    report = OptimizationReportEngine().generate(**inputs)

    assert report["readiness"] == "not_ready"
    assert "chunking" in report["skipped_operations"]


def test_report_integrity_detects_tampering():
    report = OptimizationReportEngine().generate(**complete_inputs())
    report["summary"]["token_count"] = 999

    result = validate_optimization_report(report)

    assert result["valid"] is False
    assert any("SHA-256" in error for error in result["errors"])


def test_json_export_and_reload(tmp_path):
    report = OptimizationReportEngine().generate(**complete_inputs())
    path = tmp_path / "optimization.json"

    result = export_optimization_report(report, path)
    loaded = load_optimization_report(path)

    assert result["status"] == "completed"
    assert loaded == report


def test_invalid_report_export_is_rejected(tmp_path):
    report = OptimizationReportEngine().generate(**complete_inputs())
    report["summary"]["chunk_count"] = 100

    with pytest.raises(OptimizationReportError):
        export_optimization_report(report, tmp_path / "invalid.json")


def test_markdown_export(tmp_path):
    report = OptimizationReportEngine().generate(**complete_inputs())
    markdown = render_optimization_markdown(report)
    path = tmp_path / "optimization.md"

    result = export_optimization_markdown(report, path)

    assert "# DATUMOR Optimization Report" in markdown
    assert "nomic-embed-text" not in markdown or "Operation details" in markdown
    assert result["status"] == "completed"
    assert path.exists()


def test_strict_json_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"report_type":"one","report_type":"two"}', encoding="utf-8")

    with pytest.raises(OptimizationReportError):
        load_optimization_report(path)
