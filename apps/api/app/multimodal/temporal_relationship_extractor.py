"""Temporal event extraction and cross-modal relationship analysis."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REPORT_TYPE = "datumor.temporal_analysis"
REPORT_VERSION = "1.0.0"


class TemporalValidationError(ValueError):
    """Invalid temporal input or inconsistent event references."""


def _load_artifact(value, label):
    if isinstance(value, dict):
        return value
    path = Path(value)
    if not path.is_file():
        raise TemporalValidationError(f"{label} artifact does not exist.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise TemporalValidationError(
            f"Could not read {label} artifact: {exc}"
        ) from exc


def _stable_id(*parts):
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _number(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TemporalValidationError(
            f"Invalid numeric timestamp: {field}"
        ) from exc
    if result < 0:
        raise TemporalValidationError(
            f"Negative timestamp is not supported: {field}"
        )
    return result


def _event(event_type, modality, source_id, start, end, evidence,
           observed=True, metadata=None):
    start = _number(start, "start")
    end = _number(end, "end")
    if end < start:
        raise TemporalValidationError("Event end precedes event start.")

    identity = _stable_id(
        modality, source_id, event_type, start, end, evidence
    )
    return {
        "event_id": f"event-{identity}",
        "event_type": event_type,
        "modality": modality,
        "source_id": source_id,
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": round(end - start, 6),
        "evidence": evidence,
        "timestamp_origin": "observed" if observed else "inferred",
        "metadata": metadata or {},
    }


def _source_id(artifact):
    source = artifact.get("source") or {}
    return source.get("source_id") or source.get("source_name") or "unknown"


def _video_events(video):
    events = []
    source_id = _source_id(video)
    frames = (video.get("frame_extraction") or {}).get("frames", [])

    for frame in frames:
        timestamp = _number(
            frame.get("timestamp_seconds"), "frame.timestamp_seconds"
        )
        evidence = {
            "frame_id": frame.get("frame_id"),
            "filename": frame.get("filename"),
            "checksum_sha256": frame.get("checksum_sha256"),
            "path": frame.get("path"),
        }
        events.append(_event(
            "video_frame",
            "video",
            source_id,
            timestamp,
            timestamp,
            evidence,
            metadata={
                "frame_index": frame.get("frame_index"),
                "extraction_method": frame.get("extraction_method"),
            },
        ))

    return events


def _audio_events(audio):
    events = []
    source_id = _source_id(audio)
    transcription = audio.get("transcription") or {}

    for index, segment in enumerate(transcription.get("segments", [])):
        start = segment.get("start_seconds")
        end = segment.get("end_seconds")
        evidence = {
            "segment_id": segment.get("segment_id", f"segment-{index + 1}"),
            "text": segment.get("text", ""),
            "evidence_method": segment.get("evidence_method"),
        }
        events.append(_event(
            "speech_segment",
            "audio",
            source_id,
            start,
            end,
            evidence,
            metadata={
                "speaker_id": segment.get("speaker_id"),
                "confidence": segment.get("confidence"),
            },
        ))

        for word_index, word in enumerate(segment.get("words", [])):
            word_evidence = {
                "segment_id": evidence["segment_id"],
                "word_index": word_index,
                "text": word.get("text", ""),
                "probability": word.get("probability"),
            }
            events.append(_event(
                "speech_word",
                "audio",
                source_id,
                word.get("start_seconds"),
                word.get("end_seconds"),
                word_evidence,
                metadata={"speaker_id": segment.get("speaker_id")},
            ))

    return events


def _validate_events(events, duration=None):
    ids = set()
    for event in events:
        event_id = event["event_id"]
        if event_id in ids:
            raise TemporalValidationError(
                f"Duplicate event ID: {event_id}"
            )
        ids.add(event_id)

        start = event["start_seconds"]
        end = event["end_seconds"]

        if start < 0 or end < start:
            raise TemporalValidationError(
                f"Invalid event interval: {event_id}"
            )

        # A duration mapping keeps independent media timelines separate.
        # A scalar remains supported for backwards compatibility.
        if isinstance(duration, dict):
            modality_duration = duration.get(event["modality"])
        else:
            modality_duration = duration

        if (
            modality_duration is not None
            and end > modality_duration + 0.05
        ):
            raise TemporalValidationError(
                f"Event exceeds {event['modality']} duration: {event_id}"
            )
    return True


def _relationship(source, target, relation, method, confidence,
                  evidence=None):
    return {
        "relationship_id": "relation-" + _stable_id(
            source["event_id"], target["event_id"], relation, method
        ),
        "source_event_id": source["event_id"],
        "target_event_id": target["event_id"],
        "predicate": relation,
        "method": method,
        "confidence": confidence,
        "evidence": evidence or {},
        "relationship_origin": "inferred",
    }


def _temporal_relation(first, second, tolerance):
    a_start, a_end = first["start_seconds"], first["end_seconds"]
    b_start, b_end = second["start_seconds"], second["end_seconds"]

    if a_start == b_start and a_end == b_end:
        return "coincident"

    if a_end < b_start:
        if b_start - a_end <= tolerance:
            return "near_simultaneous"
        return "before"

    if b_end < a_start:
        if a_start - b_end <= tolerance:
            return "near_simultaneous"
        return "after"

    if a_start <= b_start and a_end >= b_end:
        return "contains"

    if b_start <= a_start and b_end >= a_end:
        return "during"

    return "overlaps"


def extract_temporal_relationships(
    video_analysis=None,
    audio_analysis=None,
    alignment_tolerance_seconds=1.0,
    near_simultaneous_tolerance_seconds=0.25,
):
    """Build a unified timeline from video frame and audio transcript artifacts."""

    if alignment_tolerance_seconds < 0:
        raise ValueError("Alignment tolerance cannot be negative.")
    if near_simultaneous_tolerance_seconds < 0:
        raise ValueError("Near-simultaneous tolerance cannot be negative.")

    video = (
        _load_artifact(video_analysis, "video")
        if video_analysis is not None else None
    )
    audio = (
        _load_artifact(audio_analysis, "audio")
        if audio_analysis is not None else None
    )

    events = []
    durations = []

    if video is not None:
        video_duration = (video.get("video") or {}).get("duration_seconds")
        if video_duration is not None:
            durations.append(_number(video_duration, "video.duration"))
        events.extend(_video_events(video))

    if audio is not None:
        audio_duration = (audio.get("audio") or {}).get("duration_seconds")
        if audio_duration is not None:
            durations.append(_number(audio_duration, "audio.duration"))
        events.extend(_audio_events(audio))

    duration_by_modality = {}
    if video is not None:
        video_duration = (video.get("video") or {}).get("duration_seconds")
        if video_duration is not None:
            duration_by_modality["video"] = _number(
                video_duration, "video.duration"
            )
    if audio is not None:
        audio_duration = (audio.get("audio") or {}).get("duration_seconds")
        if audio_duration is not None:
            duration_by_modality["audio"] = _number(
                audio_duration, "audio.duration"
            )

    # Unified timeline spans the longest supplied media timeline.
    duration = max(duration_by_modality.values()) if duration_by_modality else None
    _validate_events(events, duration_by_modality)

    ordered = sorted(
        events,
        key=lambda item: (
            item["start_seconds"],
            item["end_seconds"],
            item["modality"],
            item["event_id"],
        ),
    )

    relationships = []

    # Temporal relationships between all distinct events.
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            relation = _temporal_relation(
                first, second, near_simultaneous_tolerance_seconds
            )
            if relation == "after":
                # Ordered list means this should not occur, but retain safety.
                continue
            relationships.append(_relationship(
                first,
                second,
                relation,
                "interval_comparison",
                1.0,
                {
                    "first_interval": [
                        first["start_seconds"], first["end_seconds"]
                    ],
                    "second_interval": [
                        second["start_seconds"], second["end_seconds"]
                    ],
                },
            ))

    # Cross-modal frame-to-speech alignment by nearest frame timestamp.
    frames = [e for e in ordered if e["event_type"] == "video_frame"]
    speech = [e for e in ordered if e["event_type"] == "speech_segment"]

    for segment in speech:
        midpoint = (
            segment["start_seconds"] + segment["end_seconds"]
        ) / 2
        if not frames:
            continue

        nearest = min(
            frames,
            key=lambda frame: abs(frame["start_seconds"] - midpoint),
        )
        delta = abs(nearest["start_seconds"] - midpoint)

        if delta <= alignment_tolerance_seconds:
            relationships.append(_relationship(
                segment,
                nearest,
                "temporally_aligned",
                "nearest_frame_midpoint",
                max(0.0, 1.0 - delta / max(
                    alignment_tolerance_seconds, 0.000001
                )),
                {
                    "speech_midpoint_seconds": midpoint,
                    "frame_timestamp_seconds": nearest["start_seconds"],
                    "absolute_delta_seconds": delta,
                    "alignment_tolerance_seconds": (
                        alignment_tolerance_seconds
                    ),
                },
            ))

    event_ids = {event["event_id"] for event in ordered}
    for relationship in relationships:
        if (
            relationship["source_event_id"] not in event_ids
            or relationship["target_event_id"] not in event_ids
        ):
            raise TemporalValidationError(
                "Relationship references an unknown event."
            )

    return {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "timeline": {
            "duration_seconds": duration,
            "event_count": len(ordered),
            "relationship_count": len(relationships),
            "events": ordered,
            "relationships": relationships,
        },
        "summary": {
            "video_frame_events": sum(
                e["event_type"] == "video_frame" for e in ordered
            ),
            "speech_segment_events": sum(
                e["event_type"] == "speech_segment" for e in ordered
            ),
            "speech_word_events": sum(
                e["event_type"] == "speech_word" for e in ordered
            ),
            "cross_modal_alignments": sum(
                r["predicate"] == "temporally_aligned"
                for r in relationships
            ),
        },
        "capabilities": {
            "temporal_event_representation": True,
            "chronological_ordering": True,
            "interval_relationships": True,
            "cross_modal_alignment": bool(video and audio),
            "semantic_event_understanding": False,
            "causal_inference": False,
        },
        "provenance": {
            "video_source": (
                video.get("source") if video else None
            ),
            "audio_source": (
                audio.get("source") if audio else None
            ),
            "timestamp_policy": (
                "Source timestamps are preserved; relationships are inferred."
            ),
        },
        "warnings": [],
    }


def validate_temporal_report(report):
    """Validate event intervals, ordering and relationship references."""

    if report.get("report_type") != REPORT_TYPE:
        raise TemporalValidationError("Invalid temporal report type.")

    timeline = report.get("timeline") or {}
    events = timeline.get("events") or []
    relationships = timeline.get("relationships") or []

    _validate_events(events, timeline.get("duration_seconds"))

    ids = [event.get("event_id") for event in events]
    if len(ids) != len(set(ids)):
        raise TemporalValidationError("Duplicate event identifiers.")

    if events != sorted(
        events,
        key=lambda item: (
            item["start_seconds"],
            item["end_seconds"],
            item["modality"],
            item["event_id"],
        ),
    ):
        raise TemporalValidationError("Events are not chronologically ordered.")

    known = set(ids)
    relationship_ids = set()

    for relationship in relationships:
        rid = relationship.get("relationship_id")
        if not rid or rid in relationship_ids:
            raise TemporalValidationError(
                "Missing or duplicate relationship ID."
            )
        relationship_ids.add(rid)

        if (
            relationship.get("source_event_id") not in known
            or relationship.get("target_event_id") not in known
        ):
            raise TemporalValidationError(
                "Relationship references an unknown event."
            )
        if relationship.get("relationship_origin") != "inferred":
            raise TemporalValidationError(
                "Temporal relationship origin must be explicit."
            )

    if timeline.get("event_count") != len(events):
        raise TemporalValidationError("Event count mismatch.")
    if timeline.get("relationship_count") != len(relationships):
        raise TemporalValidationError("Relationship count mismatch.")

    return {
        "valid": True,
        "event_count": len(events),
        "relationship_count": len(relationships),
        "errors": [],
    }


def export_temporal_report(report, output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    validation = validate_temporal_report(report)
    if not validation["valid"]:
        raise TemporalValidationError("Temporal report validation failed.")

    path = output / "temporal_analysis.json"
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "status": "completed",
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "event_count": validation["event_count"],
        "relationship_count": validation["relationship_count"],
    }
