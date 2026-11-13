from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePath


SUPPORTED_EXPORT_FORMATS = ("json", "jsonl", "parquet")

FORMAT_EXTENSIONS = {
    "json": ".json",
    "jsonl": ".jsonl",
    "parquet": ".parquet",
}


class ExportConfigurationError(ValueError):
    """Invalid dataset export configuration."""


@dataclass(frozen=True)
class ExportConfig:
    format: str
    filename: str | None = None
    overwrite: bool = False
    include_metadata: bool = True
    include_provenance: bool = True


def _validate_filename(filename: str | None, export_format: str) -> str:
    extension = FORMAT_EXTENSIONS[export_format]

    if filename is None:
        return f"dataset{extension}"

    if not isinstance(filename, str) or not filename.strip():
        raise ExportConfigurationError(
            "filename must be a non-empty string."
        )

    filename = filename.strip()

    if filename in {".", ".."}:
        raise ExportConfigurationError("Invalid export filename.")

    if PurePath(filename).name != filename:
        raise ExportConfigurationError(
            "Export filename cannot contain directory components."
        )

    if "/" in filename or "\\" in filename:
        raise ExportConfigurationError(
            "Export filename cannot contain path separators."
        )

    if re.search(r'[<>:"|?*\x00-\x1f]', filename):
        raise ExportConfigurationError(
            "Export filename contains unsupported characters."
        )

    if not filename.lower().endswith(extension):
        raise ExportConfigurationError(
            f"Filename must end with {extension}."
        )

    return filename


def validate_export_configuration(
    configuration: dict | ExportConfig,
) -> dict:
    if isinstance(configuration, ExportConfig):
        raw = asdict(configuration)
    elif isinstance(configuration, dict):
        raw = dict(configuration)
    else:
        raise ExportConfigurationError(
            "Configuration must be a dictionary or ExportConfig."
        )

    allowed = {
        "format",
        "filename",
        "overwrite",
        "include_metadata",
        "include_provenance",
    }

    unknown = sorted(set(raw) - allowed)

    if unknown:
        raise ExportConfigurationError(
            f"Unknown configuration fields: {unknown}"
        )

    export_format = raw.get("format")

    if not isinstance(export_format, str):
        raise ExportConfigurationError(
            "Export format must be a string."
        )

    export_format = export_format.strip().lower()

    if export_format not in SUPPORTED_EXPORT_FORMATS:
        raise ExportConfigurationError(
            f"Unsupported format: {export_format}. "
            f"Supported formats: {', '.join(SUPPORTED_EXPORT_FORMATS)}."
        )

    normalized = {
        "format": export_format,
        "filename": _validate_filename(
            raw.get("filename"),
            export_format,
        ),
    }

    defaults = {
        "overwrite": False,
        "include_metadata": True,
        "include_provenance": True,
    }

    for field, default in defaults.items():
        value = raw.get(field, default)

        if not isinstance(value, bool):
            raise ExportConfigurationError(
                f"{field} must be a boolean."
            )

        normalized[field] = value

    return normalized


def build_export_configuration(
    export_format: str,
    *,
    filename: str | None = None,
    overwrite: bool = False,
    include_metadata: bool = True,
    include_provenance: bool = True,
) -> dict:
    return validate_export_configuration({
        "format": export_format,
        "filename": filename,
        "overwrite": overwrite,
        "include_metadata": include_metadata,
        "include_provenance": include_provenance,
    })
