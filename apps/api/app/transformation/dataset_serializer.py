"""Validated JSONL, JSON, and Parquet dataset serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from apps.api.app.transformation.profile_registry import validate_profile


SERIALIZATION_REPORT_TYPE = "datumor.serialization_result"
SERIALIZATION_VERSION = "1.0.0"

SUPPORTED_FORMATS = {"jsonl", "json", "parquet"}

PARQUET_COLUMNS = [
    "example_id",
    "task_type",
    "instruction",
    "response",
    "question",
    "answer",
    "evidence",
    "query",
    "positive",
    "negative",
    "provenance_json",
    "additional_fields_json",
]


def _canonical_json(value: dict) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_dataset(dataset: dict, profile: dict) -> None:
    if not isinstance(dataset, dict):
        raise TypeError("dataset must be a dictionary")

    if dataset.get("report_type") != "datumor.generated_dataset":
        raise ValueError("Unsupported generated dataset report_type")

    dataset_profile = dataset.get("profile", {})
    if dataset_profile.get("profile_id") != profile["profile_id"]:
        raise ValueError("Dataset profile does not match selected profile")

    if dataset_profile.get("profile_version") != profile["version"]:
        raise ValueError("Dataset profile version does not match selected profile")

    examples = dataset.get("examples")
    if not isinstance(examples, list):
        raise ValueError("dataset.examples must be a list")

    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise ValueError(f"Example {index} must be an object")

        missing = [
            field for field in profile["required_fields"]
            if field not in example
            or example[field] is None
            or (isinstance(example[field], str) and not example[field].strip())
        ]
        if missing:
            raise ValueError(
                f"Example {index} is missing required fields: {missing}"
            )

        if not isinstance(example.get("example_id"), str) or not example["example_id"]:
            raise ValueError(f"Example {index} has no valid example_id")

        provenance = example.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError(f"Example {index} has no provenance object")

        if profile.get("preserve_provenance") and not provenance.get("source_id"):
            raise ValueError(
                f"Example {index} is missing its provenance source_id"
            )


def _atomic_write(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            writer(temporary)

        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _write_jsonl(handle, examples: list[dict]) -> None:
    for example in examples:
        line = json.dumps(example, ensure_ascii=False, separators=(",", ":"))
        handle.write(line.encode("utf-8") + b"\n")


def _write_json(handle, dataset: dict) -> None:
    payload = {
        "schema": "datumor.training_dataset",
        "schema_version": "1.0.0",
        "profile": dataset["profile"],
        "summary": dataset.get("summary", {}),
        "examples": dataset["examples"],
        "skipped": dataset.get("skipped", []),
    }
    handle.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
    )


def _parquet_rows(examples: list[dict]) -> list[dict]:
    rows = []

    for example in examples:
        row = {}

        for column in PARQUET_COLUMNS:
            if column in ("provenance_json", "additional_fields_json"):
                continue
            value = example.get(column)
            row[column] = (
                value if isinstance(value, str) else
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if value is not None else None
            )

        provenance = example.get("provenance", {})
        row["provenance_json"] = json.dumps(
            provenance, ensure_ascii=False, sort_keys=True
        )

        known = set(PARQUET_COLUMNS) - {
            "provenance_json", "additional_fields_json"
        } - {"provenance"}

        additional = {
            key: value
            for key, value in example.items()
            if key not in known and key != "provenance"
        }
        row["additional_fields_json"] = json.dumps(
            additional, ensure_ascii=False, sort_keys=True
        )

        rows.append(row)

    return rows


def _write_parquet(path: Path, examples: list[dict], profile: dict) -> None:
    schema = pa.schema([
        pa.field(column, pa.string(), nullable=True)
        for column in PARQUET_COLUMNS
    ])

    rows = _parquet_rows(examples)
    table = pa.Table.from_pylist(rows, schema=schema)

    metadata = {
        b"datumor.schema": b"datumor.training_dataset",
        b"datumor.schema_version": b"1.0.0",
        b"datumor.profile_id": profile["profile_id"].encode("utf-8"),
        b"datumor.profile_version": profile["version"].encode("utf-8"),
    }
    table = table.replace_schema_metadata(metadata)

    def writer(handle):
        pq.write_table(table, handle, compression="snappy")

    _atomic_write(path, writer)


def serialize_dataset(
    dataset: dict,
    profile: dict,
    output_path: str | Path,
    output_format: str | None = None,
) -> dict:
    """Validate and serialize a generated dataset atomically."""

    if not isinstance(profile, dict):
        raise TypeError("profile must be a dictionary")

    profile_validation = validate_profile(profile)
    if not profile_validation["valid"]:
        raise ValueError(
            "Invalid profile: " + "; ".join(profile_validation["errors"])
        )

    selected_format = output_format or profile["output_format"]
    if selected_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported output format: {selected_format}")

    path = Path(output_path)
    if path.suffix.lower() != f".{selected_format}":
        raise ValueError(
            f"Output path extension must be .{selected_format}"
        )

    _validate_dataset(dataset, profile)

    original_snapshot = _canonical_json(dataset)
    examples = dataset["examples"]

    if selected_format == "jsonl":
        _atomic_write(
            path,
            lambda handle: _write_jsonl(handle, examples),
        )
    elif selected_format == "json":
        _atomic_write(
            path,
            lambda handle: _write_json(handle, dataset),
        )
    else:
        _write_parquet(path, examples, profile)

    if _canonical_json(dataset) != original_snapshot:
        raise RuntimeError("Serialization modified the generated dataset")

    file_hash = _sha256_file(path)
    file_size = path.stat().st_size

    return {
        "report_type": SERIALIZATION_REPORT_TYPE,
        "version": SERIALIZATION_VERSION,
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["version"],
        },
        "output": {
            "path": str(path.resolve()),
            "format": selected_format,
            "size_bytes": file_size,
            "sha256": file_hash,
        },
        "summary": {
            "examples_serialized": len(examples),
            "examples_skipped": len(dataset.get("skipped", [])),
        },
        "integrity": {
            "file_exists": path.is_file(),
            "file_nonempty": file_size > 0,
            "sha256_verified": _sha256_file(path) == file_hash,
            "input_dataset_modified": False,
        },
    }
