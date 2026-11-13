from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION_SCHEMA = "datumor.dataset_version"
VERSION_SCHEMA_VERSION = "1.0.0"

_DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DatasetVersionError(ValueError):
    """Base exception for dataset versioning errors."""


class DatasetVersionNotFound(DatasetVersionError):
    """Requested dataset version does not exist."""


class DatasetVersionConflict(DatasetVersionError):
    """Version creation conflicts with existing history."""


class DatasetVersionIntegrityError(DatasetVersionError):
    """Stored version failed integrity verification."""


def _validate_dataset_id(dataset_id: str) -> str:
    if (
        not isinstance(dataset_id, str)
        or not _DATASET_ID_PATTERN.fullmatch(dataset_id)
    ):
        raise ValueError(
            "dataset_id must contain 1-128 safe filename characters."
        )
    return dataset_id


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DatasetVersionError(
            f"Value cannot be serialized as strict JSON: {exc}"
        ) from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _versions_dir(storage_dir: str | Path, dataset_id: str) -> Path:
    return (
        Path(storage_dir).resolve()
        / _validate_dataset_id(dataset_id)
        / "versions"
    )


def _version_path(
    storage_dir: str | Path,
    dataset_id: str,
    version_number: int,
) -> Path:
    if (
        isinstance(version_number, bool)
        or not isinstance(version_number, int)
        or version_number < 1
    ):
        raise DatasetVersionError(
            "version_number must be a positive integer."
        )

    return _versions_dir(storage_dir, dataset_id) / (
        f"v{version_number:06d}.json"
    )


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _read_version(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            record = json.load(
                handle,
                parse_constant=_reject_constant,
            )
    except FileNotFoundError as exc:
        raise DatasetVersionNotFound(
            f"Version file not found: {path.name}"
        ) from exc
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise DatasetVersionIntegrityError(
            f"Unable to read version {path.name}: {exc}"
        ) from exc

    if not isinstance(record, dict):
        raise DatasetVersionIntegrityError(
            "Version file must contain a JSON object."
        )

    return record


def _verify_record(
    record: dict,
    expected_dataset_id: str,
    expected_number: int,
) -> dict:
    required = {
        "schema",
        "schema_version",
        "version_id",
        "dataset_id",
        "version_number",
        "parent_version_id",
        "created_at",
        "dataset_sha256",
        "content_sha256",
        "dataset",
        "metadata",
    }

    missing = sorted(required - record.keys())
    if missing:
        raise DatasetVersionIntegrityError(
            f"Version record is missing fields: {missing}"
        )

    if record["schema"] != VERSION_SCHEMA:
        raise DatasetVersionIntegrityError(
            "Unsupported version schema."
        )

    if record["schema_version"] != VERSION_SCHEMA_VERSION:
        raise DatasetVersionIntegrityError(
            "Unsupported version schema version."
        )

    if record["dataset_id"] != expected_dataset_id:
        raise DatasetVersionIntegrityError(
            "Dataset ID does not match the requested dataset."
        )

    if record["version_number"] != expected_number:
        raise DatasetVersionIntegrityError(
            "Version number does not match its filename."
        )

    if not isinstance(record["version_id"], str):
        raise DatasetVersionIntegrityError("Invalid version_id.")

    if not isinstance(record["dataset"], dict):
        raise DatasetVersionIntegrityError(
            "Stored dataset must be a JSON object."
        )

    if not isinstance(record["metadata"], dict):
        raise DatasetVersionIntegrityError(
            "Stored metadata must be a JSON object."
        )

    actual_hash = _sha256(record["dataset"])

    if record["dataset_sha256"] != actual_hash:
        raise DatasetVersionIntegrityError(
            f"Dataset checksum mismatch for version {expected_number}."
        )

    if record["content_sha256"] != actual_hash:
        raise DatasetVersionIntegrityError(
            f"Content checksum mismatch for version {expected_number}."
        )

    return {
        "valid": True,
        "dataset_id": expected_dataset_id,
        "version": expected_number,
        "version_number": expected_number,
        "version_id": record["version_id"],
        "content_sha256": actual_hash,
        "dataset_sha256": actual_hash,
    }


def _existing_version_numbers(versions_dir: Path) -> list[int]:
    if not versions_dir.exists():
        return []

    numbers = []

    for path in versions_dir.glob("v*.json"):
        match = re.fullmatch(r"v(\d{6})\.json", path.name)

        if match:
            numbers.append(int(match.group(1)))

    return sorted(numbers)


def _verify_history(
    storage_dir: str | Path,
    dataset_id: str,
    numbers: list[int],
) -> dict | None:
    latest_record = None

    for expected_number, actual_number in enumerate(numbers, start=1):
        if actual_number != expected_number:
            raise DatasetVersionIntegrityError(
                "Version history contains a numbering gap."
            )

        path = _version_path(
            storage_dir,
            dataset_id,
            actual_number,
        )

        record = _read_version(path)
        _verify_record(record, dataset_id, actual_number)

        expected_parent = (
            latest_record["version_id"]
            if latest_record is not None
            else None
        )

        if record["parent_version_id"] != expected_parent:
            raise DatasetVersionIntegrityError(
                f"Invalid parent version reference at version {actual_number}."
            )

        latest_record = record

    return latest_record


def create_dataset_version(
    dataset: dict,
    storage_dir: str | Path,
    dataset_id: str,
    parent_version_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create an immutable, checksummed dataset snapshot."""

    dataset_id = _validate_dataset_id(dataset_id)

    if not isinstance(dataset, dict):
        raise DatasetVersionError("dataset must be a dictionary.")

    if metadata is not None and not isinstance(metadata, dict):
        raise DatasetVersionError(
            "metadata must be a dictionary when provided."
        )

    dataset_snapshot = deepcopy(dataset)
    metadata_snapshot = deepcopy(metadata or {})

    content_hash = _sha256(dataset_snapshot)

    versions_dir = _versions_dir(storage_dir, dataset_id)
    versions_dir.mkdir(parents=True, exist_ok=True)

    numbers = _existing_version_numbers(versions_dir)
    latest_record = _verify_history(
        storage_dir,
        dataset_id,
        numbers,
    )

    latest_number = numbers[-1] if numbers else 0

    if latest_record is None:
        if parent_version_id is not None:
            raise DatasetVersionConflict(
                "Parent version cannot be specified for the first version."
            )
    else:
        expected_parent = latest_record["version_id"]

        if parent_version_id != expected_parent:
            raise DatasetVersionConflict("Parent version (parent_version_id) must match the latest existing version.")

    version_number = latest_number + 1
    version_id = str(uuid.uuid4())

    metadata_snapshot["version_id"] = version_id
    metadata_snapshot["version"] = version_number

    record = {
        "created": True,
        "schema": VERSION_SCHEMA,
        "schema_version": VERSION_SCHEMA_VERSION,
        "version_id": version_id,
        "version": version_number,
        "dataset_id": dataset_id,
        "version_number": version_number,
        "parent_version_id": parent_version_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": content_hash,
        "content_sha256": content_hash,
        "dataset": dataset_snapshot,
        "metadata": metadata_snapshot,
    }

    path = _version_path(
        storage_dir,
        dataset_id,
        version_number,
    )

    serialized = json.dumps(
        record,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.write("\n")
    except FileExistsError as exc:
        raise DatasetVersionConflict(
            f"Version {version_number} already exists. "
            "Existing versions cannot be overwritten."
        ) from exc

    return deepcopy(record)


def list_dataset_versions(
    storage_dir: str | Path,
    dataset_id: str,
) -> dict:
    """List versions in ascending order and verify their integrity."""

    dataset_id = _validate_dataset_id(dataset_id)
    versions_dir = _versions_dir(storage_dir, dataset_id)

    numbers = _existing_version_numbers(versions_dir)

    _verify_history(storage_dir, dataset_id, numbers)

    results = []

    for number in numbers:
        record = _read_version(
            _version_path(storage_dir, dataset_id, number)
        )

        results.append({
            "version_id": record["version_id"],
            "version": number,
            "version_number": number,
            "parent_version_id": record["parent_version_id"],
            "created_at": record["created_at"],
            "content_sha256": record["content_sha256"],
            "dataset_sha256": record["dataset_sha256"],
            "integrity_valid": True,
            "metadata": deepcopy(record["metadata"]),
        })

    return {
        "dataset_id": dataset_id,
        "versions": results,
        "version_count": len(results),
        "total_versions": len(results),
        "latest_version": numbers[-1] if numbers else None,
    }


def load_dataset_version(
    storage_dir: str | Path,
    dataset_id: str,
    version_number: int,
) -> dict:
    """Load a version after verifying its checksum and identity."""

    dataset_id = _validate_dataset_id(dataset_id)

    path = _version_path(
        storage_dir,
        dataset_id,
        version_number,
    )

    record = _read_version(path)
    _verify_record(record, dataset_id, version_number)

    return deepcopy(record)


def _example_map(dataset: dict) -> dict[str, dict]:
    examples = dataset.get("examples", [])

    if not isinstance(examples, list):
        raise DatasetVersionError(
            "Dataset examples must be a list."
        )

    result = {}

    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise DatasetVersionError(
                f"Example at index {index} must be an object."
            )

        example_id = example.get("example_id")

        if not isinstance(example_id, str) or not example_id:
            raise DatasetVersionError(
                f"Example at index {index} requires example_id."
            )

        if example_id in result:
            raise DatasetVersionError(
                f"Duplicate example_id: {example_id}"
            )

        result[example_id] = example

    return result


def compare_dataset_versions(
    storage_dir: str | Path,
    dataset_id: str,
    from_version: int,
    to_version: int,
) -> dict:
    """Compare versions using stable example_id identifiers."""

    first = load_dataset_version(
        storage_dir,
        dataset_id,
        from_version,
    )

    second = load_dataset_version(
        storage_dir,
        dataset_id,
        to_version,
    )

    before = _example_map(first["dataset"])
    after = _example_map(second["dataset"])

    before_ids = set(before)
    after_ids = set(after)

    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)

    common = before_ids & after_ids

    changed = sorted(
        example_id
        for example_id in common
        if _canonical_json(before[example_id])
        != _canonical_json(after[example_id])
    )

    unchanged = sorted(common - set(changed))

    summary = {
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "unchanged": len(unchanged),
    }

    return {
        "dataset_id": dataset_id,
        "from_version": from_version,
        "to_version": to_version,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "added_example_ids": added,
        "removed_example_ids": removed,
        "changed_example_ids": changed,
        "unchanged_example_ids": unchanged,
        "summary": summary,
    }


def verify_dataset_version(
    storage_dir: str | Path,
    dataset_id: str,
    version_number: int,
) -> dict:
    """Verify the identity and content checksum of a stored version."""

    dataset_id = _validate_dataset_id(dataset_id)

    path = _version_path(
        storage_dir,
        dataset_id,
        version_number,
    )

    record = _read_version(path)

    return _verify_record(
        record,
        dataset_id,
        version_number,
    )
