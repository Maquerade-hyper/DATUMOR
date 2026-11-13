from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.app.lineage.lineage_model import LineageEventModel


CONTRACT_VERSION = "1.0.0"

EVENT_TYPES = frozenset({
    "source_added",
    "extracted",
    "understood",
    "quality_checked",
    "transformed",
    "optimized",
    "validated",
    "exported",
})

REQUIRED_FIELDS = frozenset({
    "contract_version",
    "event_id",
    "dataset_id",
    "dataset_version",
    "event_type",
    "actor",
    "timestamp",
    "input_references",
    "output_checksum_sha256",
    "metadata",
})

CHECKSUM_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class LineageValidationError(ValueError):
    """Invalid lineage event."""


class LineagePersistenceError(RuntimeError):
    """Lineage persistence operation failed."""


class DuplicateLineageEventError(LineagePersistenceError):
    """An event ID was reused with different content."""


def _parse_uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise LineageValidationError(f"{field} must be a UUID string.")

    try:
        return str(UUID(value))
    except ValueError as exc:
        raise LineageValidationError(
            f"{field} must be a valid UUID."
        ) from exc


def validate_lineage_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise LineageValidationError("Lineage event must be an object.")

    missing = REQUIRED_FIELDS - set(event)
    unknown = set(event) - REQUIRED_FIELDS

    if missing:
        raise LineageValidationError(
            f"Missing required fields: {sorted(missing)}"
        )

    if unknown:
        raise LineageValidationError(
            f"Unknown lineage fields: {sorted(unknown)}"
        )

    normalized = dict(event)

    if normalized["contract_version"] != CONTRACT_VERSION:
        raise LineageValidationError(
            f"contract_version must be {CONTRACT_VERSION}."
        )

    normalized["event_id"] = _parse_uuid(
        normalized["event_id"], "event_id"
    )
    normalized["dataset_id"] = _parse_uuid(
        normalized["dataset_id"], "dataset_id"
    )

    version = normalized["dataset_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise LineageValidationError(
            "dataset_version must be an integer greater than zero."
        )

    if normalized["event_type"] not in EVENT_TYPES:
        raise LineageValidationError("Unsupported lineage event_type.")

    actor = normalized["actor"]
    if not isinstance(actor, str) or not actor.strip():
        raise LineageValidationError("actor must be a non-empty string.")

    normalized["actor"] = actor.strip()

    timestamp = normalized["timestamp"]
    if not isinstance(timestamp, str):
        raise LineageValidationError("timestamp must be an ISO date-time.")

    try:
        parsed_timestamp = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise LineageValidationError(
            "timestamp must be a valid ISO date-time."
        ) from exc

    if parsed_timestamp.tzinfo is None:
        raise LineageValidationError(
            "timestamp must include a timezone."
        )

    normalized["timestamp"] = parsed_timestamp.astimezone(timezone.utc)

    references = normalized["input_references"]
    if (
        not isinstance(references, list)
        or any(not isinstance(item, str) for item in references)
    ):
        raise LineageValidationError(
            "input_references must be an array of strings."
        )

    checksum = normalized["output_checksum_sha256"]
    if checksum is not None:
        if not isinstance(checksum, str) or not CHECKSUM_PATTERN.fullmatch(
            checksum
        ):
            raise LineageValidationError(
                "output_checksum_sha256 must be null or 64 hexadecimal characters."
            )
        normalized["output_checksum_sha256"] = checksum.lower()

    metadata = normalized["metadata"]
    if not isinstance(metadata, dict):
        raise LineageValidationError("metadata must be an object.")

    # Ensure metadata and references are JSON-compatible and reject NaN.
    import json

    try:
        json.dumps(
            {"metadata": metadata, "input_references": references},
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LineageValidationError(
            f"Lineage metadata must contain strict JSON values: {exc}"
        ) from exc

    return normalized


def _event_to_dict(model: LineageEventModel) -> dict:
    timestamp = model.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return {
        "contract_version": model.contract_version,
        "event_id": model.event_id,
        "dataset_id": model.dataset_id,
        "dataset_version": model.dataset_version,
        "event_type": model.event_type,
        "actor": model.actor,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "input_references": list(model.input_references),
        "output_checksum_sha256": model.output_checksum_sha256,
        "metadata": dict(model.metadata_json),
    }


def record_lineage_event(session: Session, event: dict) -> dict:
    """Persist an event. Identical event submissions are idempotent."""
    normalized = validate_lineage_event(event)

    existing = session.get(
        LineageEventModel, normalized["event_id"]
    )

    if existing is not None:
        if _event_to_dict(existing) == {
            **normalized,
            "timestamp": normalized["timestamp"].isoformat(),
        }:
            return _event_to_dict(existing)

        raise DuplicateLineageEventError(
            "Event ID already exists with different content."
        )

    model = LineageEventModel(
        event_id=normalized["event_id"],
        contract_version=normalized["contract_version"],
        dataset_id=normalized["dataset_id"],
        dataset_version=normalized["dataset_version"],
        event_type=normalized["event_type"],
        actor=normalized["actor"],
        timestamp=normalized["timestamp"],
        input_references=normalized["input_references"],
        output_checksum_sha256=normalized["output_checksum_sha256"],
        metadata_json=normalized["metadata"],
    )

    try:
        session.add(model)
        session.flush()
        session.refresh(model)
        return _event_to_dict(model)
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateLineageEventError(
            "Lineage event could not be inserted because its ID already exists."
        ) from exc
    except Exception:
        session.rollback()
        raise


def get_lineage_event(session: Session, event_id: str) -> dict | None:
    normalized_id = _parse_uuid(event_id, "event_id")
    model = session.get(LineageEventModel, normalized_id)
    return _event_to_dict(model) if model else None


def list_lineage_events(
    session: Session,
    dataset_id: str,
    *,
    dataset_version: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    normalized_dataset_id = _parse_uuid(dataset_id, "dataset_id")

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise LineageValidationError("limit must be between 1 and 1000.")

    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise LineageValidationError("offset must be zero or greater.")

    if dataset_version is not None:
        if (
            isinstance(dataset_version, bool)
            or not isinstance(dataset_version, int)
            or dataset_version < 1
        ):
            raise LineageValidationError(
                "dataset_version must be a positive integer."
            )

    if event_type is not None and event_type not in EVENT_TYPES:
        raise LineageValidationError("Unsupported lineage event_type.")

    statement = select(LineageEventModel).where(
        LineageEventModel.dataset_id == normalized_dataset_id
    )

    if dataset_version is not None:
        statement = statement.where(
            LineageEventModel.dataset_version == dataset_version
        )

    if event_type is not None:
        statement = statement.where(
            LineageEventModel.event_type == event_type
        )

    statement = (
        statement
        .order_by(
            LineageEventModel.timestamp.asc(),
            LineageEventModel.event_id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    return [
        _event_to_dict(model)
        for model in session.scalars(statement).all()
    ]
