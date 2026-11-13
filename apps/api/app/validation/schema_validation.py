"""Central schema and artifact validation for DATUMOR M8.1."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from apps.api.app.transformation import dataset_serializer
from apps.api.app.understanding.dukr_generator import validate_dukr
from apps.api.app.multimodal.multimodal_record import (
    MultimodalRecordError,
    validate_multimodal_record,
)

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "contracts" / "schemas"

EXPECTED_SCHEMAS = (
    "api-error.schema.json",
    "dataset.schema.json",
    "lineage-event.schema.json",
    "multimodal-record.schema.json",
    "processing-job.schema.json",
    "processing-profile.schema.json",
    "quality-report.schema.json",
    "source.schema.json",
)

FORMAT_CHECKER = FormatChecker()


class ValidationInputError(ValueError):
    """Raised when a validation request itself is malformed."""


def _error(
    code: str,
    path: str,
    message: str,
    *,
    severity: str = "error",
) -> dict[str, str]:
    return {
        "code": code,
        "path": path or "$",
        "message": message,
        "severity": severity,
    }


def _result(errors: list[dict], warnings: list[dict] | None = None) -> dict:
    warnings = warnings or []
    return {
        "valid": not errors,
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def _load_schema(schema_name: str) -> dict:
    if schema_name not in EXPECTED_SCHEMAS:
        raise ValidationInputError(
            f"Unsupported schema name: {schema_name}"
        )

    path = SCHEMA_DIR / schema_name
    try:
        schema = strict_json_loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValidationInputError(
            f"Unable to read schema {schema_name}: {exc}"
        ) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationInputError(
            f"Schema {schema_name} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(schema, dict):
        raise ValidationInputError(
            f"Schema {schema_name} must contain a JSON object"
        )

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ValidationInputError(
            f"Schema {schema_name} is not a valid Draft 2020-12 schema: {exc}"
        ) from exc

    return schema


def strict_json_loads(raw: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-standard numbers."""

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Non-standard JSON numeric constant: {value}")

    return json.loads(
        raw,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )


def validate_contract_schemas() -> dict:
    """Check all eight shipped contract schemas for presence and validity."""

    errors = []
    validated = []

    for schema_name in EXPECTED_SCHEMAS:
        try:
            _load_schema(schema_name)
            validated.append(schema_name)
        except ValidationInputError as exc:
            errors.append(
                _error(
                    "SCHEMA_DEFINITION_INVALID",
                    f"contracts/schemas/{schema_name}",
                    str(exc),
                )
            )

    actual_names = {
        path.name for path in SCHEMA_DIR.glob("*.schema.json")
    } if SCHEMA_DIR.is_dir() else set()

    for missing in sorted(set(EXPECTED_SCHEMAS) - actual_names):
        if not any(item["path"].endswith(missing) for item in errors):
            errors.append(
                _error(
                    "SCHEMA_MISSING",
                    f"contracts/schemas/{missing}",
                    "Required contract schema is missing.",
                )
            )

    return {
        **_result(errors),
        "validated_schemas": validated,
        "schema_count": len(validated),
        "expected_schema_count": len(EXPECTED_SCHEMAS),
    }


def validate_schema_instance(
    schema_name: str,
    instance: Any,
) -> dict:
    """Validate an in-memory JSON-compatible value against a named contract."""

    try:
        schema = _load_schema(schema_name)
    except ValidationInputError as exc:
        return _result([
            _error("SCHEMA_UNAVAILABLE", "$", str(exc))
        ])

    validator = Draft202012Validator(
        schema,
        format_checker=FORMAT_CHECKER,
    )

    errors = []
    for issue in validator.iter_errors(instance):
        location = "$"
        for part in issue.absolute_path:
            location += (
                f"[{part}]" if isinstance(part, int)
                else f".{part}"
            )

        errors.append(
            _error(
                "SCHEMA_VALIDATION_ERROR",
                location,
                issue.message,
            )
        )

    errors.sort(key=lambda item: (item["path"], item["message"]))
    return _result(errors)


def validate_dukr_document(dukr: Any) -> dict:
    """Run the canonical DUKR validator and normalize its findings."""

    if not isinstance(dukr, dict):
        return _result([
            _error("DUKR_TYPE_INVALID", "$", "DUKR must be a JSON object.")
        ])

    snapshot = copy.deepcopy(dukr)
    try:
        report = validate_dukr(copy.deepcopy(dukr))
    except Exception as exc:
        return _result([
            _error("DUKR_VALIDATOR_ERROR", "$", str(exc))
        ])

    errors = [
        _error("DUKR_INTEGRITY_ERROR", "$", message)
        for message in report.get("errors", [])
    ]
    warnings = [
        _error(
            "DUKR_INTEGRITY_WARNING",
            "$",
            message,
            severity="warning",
        )
        for message in report.get("warnings", [])
    ]

    if dukr != snapshot:
        errors.append(
            _error(
                "INPUT_MUTATED",
                "$",
                "DUKR validation modified the input document.",
            )
        )

    return {
        **_result(errors, warnings),
        "checks": report.get("checks", {}),
    }


def validate_multimodal_document(record: Any) -> dict:
    """Validate a multimodal record without exposing it to validator mutation."""

    if not isinstance(record, dict):
        return _result([
            _error(
                "MULTIMODAL_TYPE_INVALID",
                "$",
                "Multimodal record must be a JSON object.",
            )
        ])

    snapshot = copy.deepcopy(record)

    try:
        report = validate_multimodal_record(copy.deepcopy(record))
    except (MultimodalRecordError, ValueError, TypeError, KeyError) as exc:
        return _result([
            _error("MULTIMODAL_VALIDATION_ERROR", "$", str(exc))
        ])
    except Exception as exc:
        return _result([
            _error("MULTIMODAL_VALIDATOR_ERROR", "$", str(exc))
        ])

    errors = [
        _error("MULTIMODAL_INTEGRITY_ERROR", "$", message)
        for message in report.get("errors", [])
    ]

    if record != snapshot:
        errors.append(
            _error(
                "INPUT_MUTATED",
                "$",
                "Multimodal validation modified the caller's input.",
            )
        )

    return {
        **_result(errors),
        "source_count": report.get("source_count", 0),
        "temporal_event_count": report.get("temporal_event_count", 0),
    }


def validate_generated_dataset(
    dataset: Any,
    profile: Any,
) -> dict:
    """Validate the existing M5 generated-dataset structure."""

    if not isinstance(dataset, dict):
        return _result([
            _error("DATASET_TYPE_INVALID", "$", "Dataset must be an object.")
        ])

    if not isinstance(profile, dict):
        return _result([
            _error("PROFILE_TYPE_INVALID", "$.profile", "Profile must be an object.")
        ])

    snapshot = copy.deepcopy(dataset)

    try:
        dataset_serializer._validate_dataset(
            copy.deepcopy(dataset),
            copy.deepcopy(profile),
        )
    except (TypeError, ValueError, KeyError) as exc:
        message = str(exc)
        path = "$"
        if "examples" in message.lower():
            path = "$.examples"
        elif "profile" in message.lower():
            path = "$.profile"

        code = (
            "DATASET_PROFILE_MISMATCH"
            if "profile" in message.lower()
            else "DATASET_STRUCTURE_INVALID"
        )
        return _result([_error(code, path, message)])
    except Exception as exc:
        return _result([
            _error("DATASET_VALIDATOR_ERROR", "$", str(exc))
        ])

    if dataset != snapshot:
        return _result([
            _error(
                "INPUT_MUTATED",
                "$",
                "Dataset validation modified the input.",
            )
        ])

    return {
        **_result([]),
        "example_count": len(dataset["examples"]),
        "skipped_count": len(dataset.get("skipped", [])),
        "profile_id": profile["profile_id"],
        "profile_version": profile["version"],
    }


def validate_dataset_artifact(
    artifact_path: str | Path,
    profile: dict,
    output_format: str | None = None,
) -> dict:
    """Read and validate an existing M5 JSON, JSONL or Parquet artifact."""

    path = Path(artifact_path)
    selected_format = (output_format or path.suffix.lstrip(".")).lower()

    if selected_format not in {"json", "jsonl", "parquet"}:
        return _result([
            _error(
                "UNSUPPORTED_DATASET_FORMAT",
                "$",
                f"Unsupported dataset artifact format: {selected_format}",
            )
        ])

    if path.suffix.lower() != f".{selected_format}":
        return _result([
            _error(
                "DATASET_EXTENSION_MISMATCH",
                "$",
                f"Artifact extension must be .{selected_format}.",
            )
        ])

    if not path.is_file():
        return _result([
            _error("DATASET_ARTIFACT_MISSING", "$", "Artifact file does not exist.")
        ])

    try:
        if selected_format == "json":
            dataset = strict_json_loads(path.read_text(encoding="utf-8"))
            report = validate_generated_dataset(dataset, profile)
            report["artifact_format"] = selected_format
            return report

        if selected_format == "jsonl":
            examples = []
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        return _result([
                            _error(
                                "JSONL_BLANK_LINE",
                                f"line[{line_number}]",
                                "Blank JSONL lines are not permitted.",
                            )
                        ])
                    try:
                        example = strict_json_loads(line)
                    except (ValueError, json.JSONDecodeError) as exc:
                        return _result([
                            _error(
                                "JSONL_PARSE_ERROR",
                                f"line[{line_number}]",
                                str(exc),
                            )
                        ])
                    if not isinstance(example, dict):
                        return _result([
                            _error(
                                "JSONL_RECORD_TYPE_INVALID",
                                f"line[{line_number}]",
                                "Each JSONL line must contain an object.",
                            )
                        ])
                    examples.append(example)

            dataset = {
                "report_type": "datumor.generated_dataset",
                "profile": {
                    "profile_id": profile.get("profile_id"),
                    "profile_version": profile.get("version"),
                },
                "examples": examples,
            }
            report = validate_generated_dataset(dataset, profile)
            report["artifact_format"] = selected_format
            return report

        import pyarrow.parquet as pq

        table = pq.read_table(path)
        examples = table.to_pylist()

        dataset = {
            "report_type": "datumor.generated_dataset",
            "profile": {
                "profile_id": profile.get("profile_id"),
                "profile_version": profile.get("version"),
            },
            "examples": examples,
        }
        report = validate_generated_dataset(dataset, profile)
        report["artifact_format"] = selected_format
        return report

    except (OSError, ValueError, TypeError) as exc:
        return _result([
            _error("DATASET_ARTIFACT_READ_ERROR", "$", str(exc))
        ])
    except Exception as exc:
        return _result([
            _error("DATASET_ARTIFACT_VALIDATION_ERROR", "$", str(exc))
        ])
