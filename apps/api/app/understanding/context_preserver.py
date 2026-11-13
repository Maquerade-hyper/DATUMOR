"""Lossless context preservation for DATUMOR."""

from __future__ import annotations

import hashlib
import re

CONTEXT_SCHEMA_VERSION = "0.1.0"


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

def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _paragraph_spans(content: str) -> list[dict]:
    """Split at blank lines while retaining every original character."""
    if not content:
        return []

    spans = []
    cursor = 0

    for match in re.finditer(r"(?:\r?\n[ \t]*){2,}", content):
        # Include the paragraph separator in the preceding span.
        end = match.end()
        spans.append({
            "start_offset": cursor,
            "end_offset": end,
            "text": content[cursor:end],
        })
        cursor = end

    if cursor < len(content):
        spans.append({
            "start_offset": cursor,
            "end_offset": len(content),
            "text": content[cursor:],
        })

    if not spans:
        spans.append({
            "start_offset": 0,
            "end_offset": len(content),
            "text": content,
        })

    return spans


def _sentence_spans(content: str, paragraph: dict) -> list[dict]:
    """Extract sentence-like spans with exact offsets into original content."""
    start = paragraph["start_offset"]
    end = paragraph["end_offset"]
    paragraph_text = content[start:end]

    # Punctuation boundaries are deterministic approximations, not full NLP.
    pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)
    results = []

    for match in pattern.finditer(paragraph_text):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        local_start = match.start() + leading
        local_end = match.start() + trailing

        if local_end <= local_start:
            continue

        absolute_start = start + local_start
        absolute_end = start + local_end

        results.append({
            "start_offset": absolute_start,
            "end_offset": absolute_end,
            "text": content[absolute_start:absolute_end],
            "start_line": _line_number(content, absolute_start),
            "end_line": _line_number(content, absolute_end - 1),
        })

    return results


def _overlaps(start: int | None, end: int | None, span: dict) -> bool:
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and end > start
        and start < span["end_offset"]
        and end > span["start_offset"]
    )


def _entity_links(entities: list[dict], span: dict) -> list[dict]:
    linked = []

    for entity in entities:
        evidence = entity.get("evidence") or {}
        start = evidence.get("start_offset")
        end = evidence.get("end_offset")

        if _overlaps(start, end, span):
            linked.append({
                "entity_id": entity.get("entity_id"),
                "entity_type": entity.get("entity_type"),
                "value": entity.get("value"),
                "evidence_start_offset": start,
                "evidence_end_offset": end,
                "page_number": evidence.get("page_number"),
                "record_number": evidence.get("record_number"),
                "start_line": evidence.get("start_line"),
                "end_line": evidence.get("end_line"),
                "segment_type": evidence.get("segment_type"),
            })

    return linked


def _relationship_links(relationships: list[dict], span: dict) -> list[dict]:
    linked = []

    for relationship in relationships:
        evidence = relationship.get("evidence") or {}

        if _overlaps(
            evidence.get("start_offset"),
            evidence.get("end_offset"),
            span,
        ):
            linked.append({
                "relationship_id": relationship.get("relationship_id"),
                "subject_entity_id": (
                    relationship.get("subject") or {}
                ).get("entity_id"),
                "predicate": relationship.get("predicate"),
                "object_entity_id": (
                    relationship.get("object") or {}
                ).get("entity_id"),
                "start_offset": evidence.get("start_offset"),
                "end_offset": evidence.get("end_offset"),
            })

    return linked


def _statement_links(statements: list[dict], span: dict) -> list[dict]:
    linked = []

    for statement in statements:
        evidence = statement.get("evidence") or {}

        if _overlaps(
            evidence.get("start_offset"),
            evidence.get("end_offset"),
            span,
        ):
            linked.append({
                "statement_id": statement.get("statement_id"),
                "text": statement.get("text"),
                "epistemic_status": statement.get("epistemic_status"),
                "start_offset": evidence.get("start_offset"),
                "end_offset": evidence.get("end_offset"),
            })

    return linked


def preserve_context(
    extraction_result: dict,
    entity_result: dict | None = None,
    semantic_result: dict | None = None,
    relationship_result: dict | None = None,
) -> dict:
    """Build lossless document context units and preserve knowledge links."""
    if not isinstance(extraction_result, dict):
        raise TypeError("extraction_result must be a dictionary.")

    content = extraction_result.get("content")
    if not isinstance(content, str):
        raise ValueError("M2 extraction result must contain string content.")

    for name, value in (
        ("entity_result", entity_result),
        ("semantic_result", semantic_result),
        ("relationship_result", relationship_result),
    ):
        if value is not None and not isinstance(value, dict):
            raise TypeError(f"{name} must be a dictionary when supplied.")

    entity_result = entity_result or {}
    semantic_result = semantic_result or {}
    relationship_result = relationship_result or {}

    entities = entity_result.get("entities") or []
    relationships = relationship_result.get("relationships") or []
    facts = semantic_result.get("facts") or []
    claims = semantic_result.get("claims") or []

    if not isinstance(entities, list):
        raise ValueError("entity_result.entities must be a list.")
    if not isinstance(relationships, list):
        raise ValueError("relationship_result.relationships must be a list.")
    if not isinstance(facts, list) or not isinstance(claims, list):
        raise ValueError("Semantic facts and claims must be lists.")

    source = _source_identity(extraction_result)
    identity_material = (
        source.get("checksum_sha256")
        or hashlib.sha256(content.encode("utf-8")).hexdigest()
    )

    paragraphs = _paragraph_spans(content)
    context_units = []
    sentence_count = 0

    for index, paragraph in enumerate(paragraphs):
        paragraph_id = hashlib.sha256(
            f"{identity_material}|paragraph|{index}|"
            f"{paragraph['start_offset']}|{paragraph['end_offset']}".encode()
        ).hexdigest()

        sentences = _sentence_spans(content, paragraph)
        sentence_units = []

        for sentence_index, sentence in enumerate(sentences):
            sentence_count += 1
            sentence_id = hashlib.sha256(
                f"{identity_material}|sentence|"
                f"{sentence['start_offset']}|{sentence['end_offset']}".encode()
            ).hexdigest()

            sentence_units.append({
                "sentence_id": sentence_id,
                **sentence,
                "previous_sentence_id": (
                    sentence_units[-1]["sentence_id"]
                    if sentence_units else None
                ),
                "next_sentence_id": None,
                "entity_links": _entity_links(entities, sentence),
                "relationship_links": _relationship_links(
                    relationships, sentence
                ),
                "fact_links": _statement_links(facts, sentence),
                "claim_links": _statement_links(claims, sentence),
            })

        for sentence_index in range(len(sentence_units) - 1):
            sentence_units[sentence_index]["next_sentence_id"] = (
                sentence_units[sentence_index + 1]["sentence_id"]
            )

        context_units.append({
            "context_unit_id": paragraph_id,
            "unit_type": "paragraph",
            "sequence": index,
            **paragraph,
            "start_line": _line_number(content, paragraph["start_offset"]),
            "end_line": _line_number(
                content, max(paragraph["start_offset"],
                             paragraph["end_offset"] - 1)
            ),
            "previous_context_unit_id": None,
            "next_context_unit_id": None,
            "sentences": sentence_units,
            "entity_links": _entity_links(entities, paragraph),
            "relationship_links": _relationship_links(
                relationships, paragraph
            ),
            "fact_links": _statement_links(facts, paragraph),
            "claim_links": _statement_links(claims, paragraph),
        })

    for index in range(len(context_units)):
        if index:
            context_units[index]["previous_context_unit_id"] = (
                context_units[index - 1]["context_unit_id"]
            )
        if index + 1 < len(context_units):
            context_units[index]["next_context_unit_id"] = (
                context_units[index + 1]["context_unit_id"]
            )

    reconstructed = "".join(unit["text"] for unit in context_units)
    if reconstructed != content:
        raise RuntimeError("Context segmentation failed lossless reconstruction.")

    source_records = extraction_result.get("records") or []

    return {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "source": source,
        "document": {
            "original_content": content,
            "content_length": len(content),
            "content_sha256": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            "format": extraction_result.get("format"),
            "source_filename": extraction_result.get("source_filename"),
            "source_metadata": (
                extraction_result.get("metadata") or {}
            ),
            "source_warnings": extraction_result.get("warnings") or [],
        },
        "context_units": context_units,
        "source_records": source_records,
        "summary": {
            "context_unit_count": len(context_units),
            "sentence_count": sentence_count,
            "entity_link_count": sum(
                len(unit["entity_links"]) for unit in context_units
            ),
            "relationship_link_count": sum(
                len(unit["relationship_links"]) for unit in context_units
            ),
            "fact_link_count": sum(
                len(unit["fact_links"]) for unit in context_units
            ),
            "claim_link_count": sum(
                len(unit["claim_links"]) for unit in context_units
            ),
            "original_content_preserved": reconstructed == content,
        },
        "warnings": [
            "Sentence boundaries use deterministic punctuation heuristics.",
            "Paragraph separators remain attached to their preceding context unit.",
            "Page and record references are retained only when supplied by upstream evidence.",
            "Context links are based on overlapping source offsets, not inferred semantic proximity.",
        ],
    }
