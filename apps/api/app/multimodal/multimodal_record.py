"""Canonical multimodal record generation for DATUMOR."""

from __future__ import annotations

import copy
import hashlib
import math
import json
import uuid

from datetime import datetime, timezone
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_VERSION = "1.0.0"


class MultimodalRecordError(ValueError):
    """Raised when upstream modality reports cannot form a record."""


def _validate_report(report: dict, expected_type: str) -> None:
    if not isinstance(report, dict):
        raise MultimodalRecordError(
            f"{expected_type} analysis must be a dictionary"
        )

    if report.get("status") != "completed":
        raise MultimodalRecordError(
            f"{expected_type} analysis is not completed"
        )

    source = report.get("source")
    if not isinstance(source, dict):
        raise MultimodalRecordError(
            f"{expected_type} report has no valid source metadata"
        )

    checksum = source.get("checksum_sha256")
    if checksum is not None:
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in checksum)
        ):
            raise MultimodalRecordError(
                f"{expected_type} report has an invalid SHA-256 checksum"
            )


def _source_entry(modality: str, report: dict) -> dict:
    source = report["source"]
    checksum = source.get("checksum_sha256")

    return {
        "modality": modality,
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "checksum_sha256": checksum,
        "media_type": source.get("media_type"),
        "size_bytes": source.get("size_bytes"),
    }


def _report_reference(modality: str, report: dict) -> dict:
    canonical = json.dumps(
        report,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return {
        "modality": modality,
        "report_type": report.get("report_type"),
        "report_version": report.get("version"),
        "checksum_sha256": hashlib.sha256(canonical).hexdigest(),
        "created_at": report.get("created_at"),
    }


def _warnings(reports: list[tuple[str, dict]]) -> list[str]:
    result = []

    for modality, report in reports:
        for warning in report.get("warnings", []):
            message = f"{modality}: {warning}"
            if message not in result:
                result.append(message)

        capabilities = report.get("capabilities", {})
        if not isinstance(capabilities, dict):
            continue

        for capability, available in capabilities.items():
            if available is False:
                message = f"{modality}: capability unavailable: {capability}"
                if message not in result:
                    result.append(message)

    return result



def _derived_source_links(
    audio_analysis: dict | None,
    video_analysis: dict | None,
) -> list[dict]:
    """Describe audio artifacts explicitly extracted from a video source."""

    if audio_analysis is None or video_analysis is None:
        return []

    video_audio = video_analysis.get("audio")
    if not isinstance(video_audio, dict):
        return []

    extraction_path = video_audio.get("extracted_path")
    if not isinstance(extraction_path, str) or not extraction_path.strip():
        return []

    audio_source = audio_analysis["source"]
    audio_name = audio_source.get("source_name")
    if not isinstance(audio_name, str) or not audio_name.strip():
        raise MultimodalRecordError(
            "Extracted audio report has no source name"
        )

    if Path(extraction_path).name.casefold() != Path(audio_name).name.casefold():
        raise MultimodalRecordError(
            "Extracted audio filename does not match the video's "
            "recorded extraction path"
        )

    return [{
        "relationship": "extracted_from",
        "derived_source": _source_entry("audio", audio_analysis),
        "parent_source": _source_entry("video", video_analysis),
        "extraction_path": extraction_path,
    }]

def generate_multimodal_record(
    images: list[dict] | None = None,
    audio_analysis: dict | None = None,
    video_analysis: dict | None = None,
    temporal_analysis: dict | None = None,
) -> dict:
    """Generate a canonical record from completed modality reports."""

    images = images or []

    if not isinstance(images, list):
        raise MultimodalRecordError("images must be a list")

    reports: list[tuple[str, dict]] = []

    for image in images:
        _validate_report(image, "image")
        reports.append(("image", image))

    if audio_analysis is not None:
        _validate_report(audio_analysis, "audio")
        reports.append(("audio", audio_analysis))

    if video_analysis is not None:
        _validate_report(video_analysis, "video")
        reports.append(("video", video_analysis))

    if not reports:
        raise MultimodalRecordError(
            "At least one completed modality report is required"
        )

    if temporal_analysis is not None:
        if not isinstance(temporal_analysis, dict):
            raise MultimodalRecordError(
                "temporal_analysis must be a dictionary"
            )

        if temporal_analysis.get("status") == "invalid":
            raise MultimodalRecordError(
                "Temporal analysis is marked invalid"
            )

    sources = []
    upstream_reports = []

    for modality, report in reports:
        sources.append(_source_entry(modality, report))
        upstream_reports.append(_report_reference(modality, report))

    record = {
        "record_id": str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modalities": {
            "images": copy.deepcopy(images),
            "audio": copy.deepcopy(audio_analysis),
            "video": copy.deepcopy(video_analysis),
        },
        "temporal": copy.deepcopy(temporal_analysis),
        "provenance": {
            "sources": sources,
            "upstream_reports": upstream_reports,
            "derived_sources": _derived_source_links(
                audio_analysis, video_analysis
            ),
        },
        "warnings": _warnings(reports),
        "validation": {
            "status": "pending",
            "errors": [],
        },
    }

    return record



def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value):
    raise ValueError(f"Non-finite JSON number is not permitted: {value}")


def export_multimodal_record(
    record: dict,
    output_path: str | Path,
) -> Path:
    """Validate and write a record as deterministic, atomic JSON."""

    validation = validate_multimodal_record(record)
    if not validation["valid"]:
        raise MultimodalRecordError(
            "Cannot export invalid multimodal record: "
            + "; ".join(validation["errors"])
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    temporary = destination.with_name(destination.name + ".tmp")

    try:
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    return destination


def load_multimodal_record(path: str | Path) -> dict:
    """Load, parse strictly, and validate an exported multimodal record."""

    source = Path(path)

    try:
        with source.open("r", encoding="utf-8") as handle:
            record = json.load(
                handle,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_constant,
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise MultimodalRecordError(
            f"Unable to load multimodal record: {exc}"
        ) from exc

    if not isinstance(record, dict):
        raise MultimodalRecordError("Record JSON must contain an object")

    validation = validate_multimodal_record(record)
    if not validation["valid"]:
        raise MultimodalRecordError(
            "Loaded multimodal record is invalid: "
            + "; ".join(validation["errors"])
        )

    return record



def validate_multimodal_record(record: dict) -> dict:
    """Validate canonical structure, provenance and temporal references."""

    errors = []

    if not isinstance(record, dict):
        raise MultimodalRecordError("Record must be a dictionary")

    schema_path = (
        Path(__file__).resolve().parents[4]
        / "contracts"
        / "schemas"
        / "multimodal-record.schema.json"
    )

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))

        # Validate the candidate record as a final-state record.
        # The generator's initial "pending" status is an internal state.
        candidate = copy.deepcopy(record)
        candidate["validation"] = {
            "status": "valid",
            "errors": [],
        }

        validator = Draft202012Validator(
            schema, format_checker=FormatChecker()
        )
        errors.extend(
            f"Schema: {error.message}"
            for error in validator.iter_errors(candidate)
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise MultimodalRecordError(
            f"Unable to load multimodal schema: {exc}"
        ) from exc

    if errors:
        return {"valid": False, "errors": errors}

    modalities = record["modalities"]
    reports = []

    for image in modalities["images"]:
        reports.append(("image", image))

    if modalities["audio"] is not None:
        reports.append(("audio", modalities["audio"]))

    if modalities["video"] is not None:
        reports.append(("video", modalities["video"]))

    expected_sources = [
        _source_entry(modality, report)
        for modality, report in reports
    ]

    if record["provenance"]["sources"] != expected_sources:
        errors.append("Provenance source entries do not match modality reports")

    expected_reports = [
        _report_reference(modality, report)
        for modality, report in reports
    ]

    if record["provenance"]["upstream_reports"] != expected_reports:
        errors.append("Upstream report references do not match modality reports")

    expected_derived_sources = _derived_source_links(
        modalities["audio"], modalities["video"]
    )
    if record["provenance"].get("derived_sources", []) != expected_derived_sources:
        errors.append("Derived-source provenance does not match modality reports")

    identities = {}
    for modality, report in reports:
        source = report["source"]
        source_id = source.get("source_id")
        checksum = source.get("checksum_sha256")

        if source_id is not None:
            key = str(source_id)
            if key in identities:
                previous = identities[key]
                if previous != checksum:
                    errors.append(
                        f"Conflicting checksums for source identity {key}"
                    )
            else:
                identities[key] = checksum

    temporal = record["temporal"]
    if temporal is not None:
        from apps.api.app.multimodal.temporal_relationship_extractor import (
            validate_temporal_report,
        )

        try:
            validate_temporal_report(temporal)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"Temporal report invalid: {exc}")

        timeline = temporal.get("timeline") or {}
        events = timeline.get("events") or []
        relationships = timeline.get("relationships") or []

        event_ids = [event.get("event_id") for event in events]
        known_ids = set(event_ids)

        if len(event_ids) != len(known_ids):
            errors.append("Duplicate temporal event references")

        durations = {}
        if modalities["video"] is not None:
            duration = (
                modalities["video"].get("video") or {}
            ).get("duration_seconds")
            if duration is not None:
                durations["video"] = duration

        if modalities["audio"] is not None:
            duration = (
                modalities["audio"].get("audio") or {}
            ).get("duration_seconds")
            if duration is not None:
                durations["audio"] = duration

        for modality, duration in durations.items():
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration < 0
            ):
                errors.append(f"Invalid {modality} media duration")

        timeline_duration = timeline.get("duration_seconds")
        if durations:
            if (
                isinstance(timeline_duration, bool)
                or not isinstance(timeline_duration, (int, float))
                or not math.isfinite(timeline_duration)
                or timeline_duration < 0
            ):
                errors.append("Invalid unified timeline duration")
            elif abs(timeline_duration - max(durations.values())) > 0.05:
                errors.append(
                    "Unified timeline duration does not match modality durations"
                )

        for event in events:
            modality = event.get("modality")
            start = event.get("start_seconds")
            end = event.get("end_seconds")

            if modality not in {"video", "audio"}:
                errors.append(
                    f"Unsupported temporal event modality: {modality}"
                )
                continue

            for label, value in (("start", start), ("end", end)):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    errors.append(
                        f"Invalid {label} timestamp in event "
                        f"{event.get('event_id')}"
                    )

            if (
                isinstance(start, (int, float))
                and not isinstance(start, bool)
                and isinstance(end, (int, float))
                and not isinstance(end, bool)
                and start > end
            ):
                errors.append(
                    f"Event starts after it ends: {event.get('event_id')}"
                )

            duration = durations.get(modality)
            if (
                duration is not None
                and isinstance(end, (int, float))
                and not isinstance(end, bool)
                and math.isfinite(end)
                and end > duration + 0.001
            ):
                errors.append(
                    f"Event exceeds {modality} duration: "
                    f"{event.get('event_id')}"
                )

        for relationship in relationships:
            if (
                relationship.get("source_event_id") not in known_ids
                or relationship.get("target_event_id") not in known_ids
            ):
                errors.append("Temporal relationship has unresolved event reference")

    record["validation"] = {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
    }

    return {
        "valid": not errors,
        "errors": errors,
        "source_count": len(expected_sources),
        "temporal_event_count": (
            len((temporal.get("timeline") or {}).get("events") or [])
            if temporal else 0
        ),
    }
