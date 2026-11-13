"""Evidence-grounded relationship extraction for DATUMOR."""

from __future__ import annotations

import hashlib
import re

from apps.api.app.understanding.entity_extractor import extract_entities

RELATIONSHIP_SCHEMA_VERSION = "0.1.0"

# Connectors are intentionally explicit. Mere co-occurrence is not a relation.
FORWARD_RELATIONS = {
    "works with": "collaborates_with",
    "collaborates with": "collaborates_with",
    "develops": "develops",
    "creates": "creates",
    "created": "creates",
    "uses": "uses",
    "built with": "built_with",
    "builds with": "built_with",
    "located in": "located_in",
    "is located in": "located_in",
    "are located in": "located_in",
    "was located in": "located_in",
    "were located in": "located_in",
    "is based in": "based_in",
    "are based in": "based_in",
    "was based in": "based_in",
    "were based in": "based_in",
    "based in": "based_in",
    "operates in": "operates_in",
    "part of": "part_of",
    "depends on": "depends_on",
    "supports": "supports",
    "integrates with": "integrates_with",
    "connects to": "connects_to",
    "contains": "contains",
    "includes": "includes",
    "founded": "founded",
    "owns": "owns",
    "maintains": "maintains",
    "scheduled for": "scheduled_for",
}

# In these constructions the entity on the right is the actor/subject.
REVERSE_RELATIONS = {
    "developed by": "develops",
    "was developed by": "develops",
    "were developed by": "develops",
    "is developed by": "develops",
    "are developed by": "develops",
    "created by": "creates",
    "built by": "builds",
    "founded by": "founded",
    "written by": "writes",
    "maintained by": "maintains",
    "owned by": "owns",
    "operated by": "operates",
    "supported by": "supports",
}

def _source_identity(extraction: dict) -> dict:
    metadata = extraction.get("metadata") or {}
    source_metadata = metadata.get("source") or {}
    source_identity = metadata.get("source_identity") or {}

    return {
        "source_id": (
            source_identity.get("source_id")
            or metadata.get("source_id")
            or source_metadata.get("source_id")
        ),
        "project_id": (
            source_identity.get("project_id")
            or metadata.get("project_id")
            or source_metadata.get("project_id")
        ),
        "filename": (
            extraction.get("source_filename")
            or source_identity.get("filename")
            or source_metadata.get("filename")
        ),
        "path": source_identity.get("path") or source_metadata.get("path"),
        "checksum_sha256": (
            source_identity.get("checksum_sha256")
            or source_metadata.get("checksum_sha256")
            or extraction.get("checksum_sha256")
        ),
    }

def _sentences(content: str) -> list[dict]:
    """Split text while preserving exact character offsets and line numbers."""
    output = []
    for match in re.finditer(r"\S(?:.*?\S)?(?<=[.!?])(?=\s|$)", content, re.DOTALL):
        value = match.group(0)
        start = match.start() + len(value) - len(value.lstrip())
        value = value.strip()
        if not value:
            continue
        end = start + len(value)
        output.append({
            "text": value,
            "start_offset": start,
            "end_offset": end,
            "start_line": content.count("\n", 0, start) + 1,
            "end_line": content.count("\n", 0, max(start, end - 1)) + 1,
        })

    if not output and content.strip():
        start = len(content) - len(content.lstrip())
        value = content.strip()
        output.append({
            "text": value,
            "start_offset": start,
            "end_offset": start + len(value),
            "start_line": content.count("\n", 0, start) + 1,
            "end_line": content.count("\n", 0, start + len(value) - 1) + 1,
        })
    return output


def _entity_spans(entities: list[dict], sentence: dict) -> list[dict]:
    spans = []
    for entity in entities:
        evidence = entity.get("evidence") or {}
        start = evidence.get("start_offset")
        end = evidence.get("end_offset")
        value = entity.get("value")

        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not isinstance(value, str)
            or start < sentence["start_offset"]
            or end > sentence["end_offset"]
            or end <= start
        ):
            continue

        spans.append({
            "entity_id": entity.get("entity_id"),
            "entity_type": entity.get("entity_type"),
            "value": value,
            "normalized_value": entity.get("normalized_value", value.casefold()),
            "start": start,
            "end": end,
        })

    return sorted(spans, key=lambda item: (item["start"], item["end"]))


def _match_connector(text: str) -> tuple[str, str, bool] | None:
    """Return predicate, matched connector and whether direction is reversed."""
    normalized = re.sub(r"\s+", " ", text.casefold()).strip(" \t,;:")

    # Longest connectors first to avoid matching a shorter overlapping phrase.
    for connector, predicate in sorted(
        FORWARD_RELATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.fullmatch(
            r"(?:\s|,|;|:)*(?:" + re.escape(connector) + r")(?:\s|,|;|:)*",
            normalized,
        ):
            return predicate, connector, False

    for connector, predicate in sorted(
        REVERSE_RELATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.fullmatch(
            r"(?:\s|,|;|:)*(?:" + re.escape(connector) + r")(?:\s|,|;|:)*",
            normalized,
        ):
            return predicate, connector, True

    return None


def extract_relationships(
    extraction_result: dict,
    entity_result: dict | None = None,
) -> dict:
    """Extract explicit entity relationships from an M2 extraction result."""
    if not isinstance(extraction_result, dict):
        raise TypeError("extraction_result must be a dictionary.")

    content = extraction_result.get("content")
    if not isinstance(content, str):
        raise ValueError("M2 extraction result must contain string content.")

    if entity_result is None:
        entity_result = extract_entities(extraction_result)

    if not isinstance(entity_result, dict):
        raise TypeError("entity_result must be a dictionary.")

    entities = entity_result.get("entities") or []
    if not isinstance(entities, list):
        raise ValueError("entity_result.entities must be a list.")

    sentences = _sentences(content)
    relationships = []
    seen = set()
    checksum = _source_identity(extraction_result).get("checksum_sha256") or ""

    for sentence in sentences:
        spans = _entity_spans(entities, sentence)
        if len(spans) < 2:
            continue

        for left_index, left in enumerate(spans):
            for right in spans[left_index + 1:]:
                # Overlapping spans cannot establish a reliable connector.
                if left["end"] > right["start"]:
                    continue

                connector_text = content[left["end"]:right["start"]]
                matched = _match_connector(connector_text)
                if matched is None:
                    continue

                predicate, connector, reversed_direction = matched
                subject, obj = (
                    (right, left) if reversed_direction else (left, right)
                )

                if not subject["entity_id"] or not obj["entity_id"]:
                    continue
                if subject["entity_id"] == obj["entity_id"]:
                    continue

                relation_key = (
                    subject["entity_id"],
                    predicate,
                    obj["entity_id"],
                    sentence["start_offset"],
                    sentence["end_offset"],
                )
                if relation_key in seen:
                    continue
                seen.add(relation_key)

                relation_material = (
                    f"{checksum}|{subject['entity_id']}|{predicate}|"
                    f"{obj['entity_id']}|{sentence['start_offset']}|"
                    f"{sentence['end_offset']}"
                )
                relationship_id = hashlib.sha256(
                    relation_material.encode("utf-8")
                ).hexdigest()

                relationships.append({
                    "relationship_id": relationship_id,
                    "subject": {
                        "entity_id": subject["entity_id"],
                        "entity_type": subject["entity_type"],
                        "value": subject["value"],
                        "normalized_value": subject["normalized_value"],
                    },
                    "predicate": predicate,
                    "object": {
                        "entity_id": obj["entity_id"],
                        "entity_type": obj["entity_type"],
                        "value": obj["value"],
                        "normalized_value": obj["normalized_value"],
                    },
                    "triple": {
                        "subject": subject["value"],
                        "predicate": predicate,
                        "object": obj["value"],
                    },
                    "direction": "subject_to_object",
                    "confidence": 0.90,
                    "extraction_method": "explicit_connector_pattern",
                    "evidence": {
                        "text": sentence["text"],
                        "matched_text": connector,
                        "connector_text": connector_text,
                        "start_offset": sentence["start_offset"],
                        "end_offset": sentence["end_offset"],
                        "start_line": sentence["start_line"],
                        "end_line": sentence["end_line"],
                        "page_number": (
                            entity_result.get("source", {}).get("page_number")
                            if isinstance(entity_result.get("source"), dict)
                            else None
                        ),
                    },
                    "provenance": _source_identity(extraction_result),
                })

    relationships.sort(
        key=lambda item: (
            item["evidence"]["start_offset"],
            item["predicate"],
            item["relationship_id"],
        )
    )

    return {
        "relationship_schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "source": _source_identity(extraction_result),
        "summary": {
            "relationship_count": len(relationships),
            "predicate_counts": {
                predicate: sum(
                    1 for item in relationships
                    if item["predicate"] == predicate
                )
                for predicate in sorted({
                    item["predicate"] for item in relationships
                })
            },
            "sentence_count": len(sentences),
            "entity_count": len(entities),
        },
        "relationships": relationships,
        "warnings": [
            "Only explicit supported connector patterns produce relationships.",
            "Relationships are heuristic interpretations and require domain validation.",
            "Co-occurrence without an explicit connector does not establish a relationship.",
            "Entities without valid source offsets are excluded from text relationship matching.",
        ],
    }
