import pytest

from apps.api.app.exporting.export_config import (
    ExportConfig,
    ExportConfigurationError,
    SUPPORTED_EXPORT_FORMATS,
    build_export_configuration,
    validate_export_configuration,
)


@pytest.mark.parametrize(
    ("fmt", "filename"),
    [
        ("json", "dataset.json"),
        ("jsonl", "dataset.jsonl"),
        ("parquet", "dataset.parquet"),
    ],
)
def test_supported_formats(fmt, filename):
    result = build_export_configuration(fmt)
    assert result["format"] == fmt
    assert result["filename"] == filename


def test_supported_formats_registry():
    assert SUPPORTED_EXPORT_FORMATS == ("json", "jsonl", "parquet")


def test_format_case_normalization():
    assert build_export_configuration("JSONL")["format"] == "jsonl"


def test_custom_filename():
    result = build_export_configuration(
        "json",
        filename="training-data.json",
    )
    assert result["filename"] == "training-data.json"


def test_configuration_defaults():
    result = build_export_configuration("json")
    assert result["overwrite"] is False
    assert result["include_metadata"] is True
    assert result["include_provenance"] is True


def test_dataclass_configuration():
    result = validate_export_configuration(
        ExportConfig(format="parquet")
    )
    assert result["filename"] == "dataset.parquet"


@pytest.mark.parametrize("fmt", ["csv", "xml", "yaml", "", None])
def test_unsupported_formats_rejected(fmt):
    with pytest.raises(ExportConfigurationError):
        build_export_configuration(fmt)


@pytest.mark.parametrize(
    "filename",
    [
        "../dataset.json",
        "folder/dataset.json",
        "folder\\dataset.json",
        "",
        "..",
        "invalid?.json",
        "dataset.jsonl",
    ],
)
def test_unsafe_or_invalid_filenames_rejected(filename):
    with pytest.raises(ExportConfigurationError):
        build_export_configuration("json", filename=filename)


@pytest.mark.parametrize(
    "field",
    ["overwrite", "include_metadata", "include_provenance"],
)
def test_boolean_fields_are_strict(field):
    with pytest.raises(ExportConfigurationError):
        validate_export_configuration({
            "format": "json",
            field: "false",
        })


def test_unknown_fields_rejected():
    with pytest.raises(ExportConfigurationError):
        validate_export_configuration({
            "format": "json",
            "unknown": True,
        })


def test_wrong_extension_rejected():
    with pytest.raises(ExportConfigurationError):
        build_export_configuration(
            "parquet",
            filename="dataset.json",
        )


def test_input_is_not_mutated():
    config = {"format": "JSON", "overwrite": False}
    original = config.copy()

    validate_export_configuration(config)

    assert config == original
