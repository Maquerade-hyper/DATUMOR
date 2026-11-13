"""M8.2 semantic integrity and evidence-grounding validation."""

from __future__ import annotations

import copy
from typing import Any


def _finding(
    code: str,
    path: str,
    message: str,
    severity: str = "error",
    evidence: dict | None = None,
) -> dict:
    result = {
        "code": code,
        "path": path or "$",
        "message": message,
        "severity": severity,
    }
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _report(findings: list[dict], **metadata: Any) -> dict:
    errors = [item for item in findings if item["severity"] == "error"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    return {
        "valid": not errors,
        "status": "valid" if not errors else "invalid",
        "findings": findings,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        **metadata,
    }


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, dict):
        for key in (
            "evidence_text", "text", "quote", "sentence",
            "statement", "content", "original_text",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return None


def _items(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _source_content(dukr: dict) -> str | None:
    source = dukr.get("source")
    if not isinstance(source, dict):
        return None
    content = source.get("original_content")
    return content if isinstance(content, str) else None


def _check_evidence(
    findings: list[dict],
    *,
    evidence: str | None,
    content: str | None,
    path: str,
    item: dict | None = None,
) -> None:
    item = item or {}

    if not evidence:
        findings.append(_finding(
            "EVIDENCE_MISSING",
            path,
            "No explicit evidence text was supplied for this semantic item.",
            "warning",
        ))
        return

    start = item.get("start_offset")
    end = item.get("end_offset")

    if start is not None or end is not None:
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
        ):
            findings.append(_finding(
                "EVIDENCE_OFFSETS_INVALID",
                path,
                "Evidence offsets must be non-negative integer boundaries.",
            ))
            return

        if content is None:
            findings.append(_finding(
                "SOURCE_CONTENT_UNAVAILABLE",
                path,
                "Cannot verify evidence offsets because original source content is unavailable.",
                "warning",
            ))
            return

        if end > len(content):
            findings.append(_finding(
                "EVIDENCE_OFFSET_OUT_OF_RANGE",
                path,
                "Evidence end offset exceeds the original source length.",
                evidence={"start_offset": start, "end_offset": end},
            ))
            return

        extracted = content[start:end]
        if extracted != evidence:
            findings.append(_finding(
                "EVIDENCE_OFFSET_MISMATCH",
                path,
                "Evidence text does not match the original source at the supplied offsets.",
                evidence={
                    "start_offset": start,
                    "end_offset": end,
                    "expected_text": evidence,
                    "source_text": extracted,
                },
            ))
        return

    if content is None:
        findings.append(_finding(
            "SOURCE_CONTENT_UNAVAILABLE",
            path,
            "Cannot verify evidence because original source content is unavailable.",
            "warning",
        ))
    elif evidence not in content:
        findings.append(_finding(
            "EVIDENCE_NOT_GROUNDED",
            path,
            "Evidence text does not occur in the original source content.",
            evidence={"evidence_text": evidence},
        ))


def validate_dukr_semantics(dukr: Any) -> dict:
    """Check DUKR entity, semantic, relationship and context grounding."""

    if not isinstance(dukr, dict):
        return _report([
            _finding("DUKR_TYPE_INVALID", "$", "DUKR must be an object.")
        ])

    snapshot = copy.deepcopy(dukr)
    findings: list[dict] = []
    content = _source_content(dukr)

    if content is None:
        findings.append(_finding(
            "SOURCE_CONTENT_MISSING",
            "$.source.original_content",
            "Original source content is unavailable; grounding checks are limited.",
            "warning",
        ))

    entities = list(_items(dukr.get("entities", [])))
    relationships = list(_items(dukr.get("relationships", [])))
    semantics = dukr.get("semantics")
    semantics = semantics if isinstance(semantics, dict) else {}
    context = dukr.get("context")
    context = context if isinstance(context, dict) else {}
    context_units = list(_items(context.get("context_units", [])))

    entity_ids = {
        item.get("entity_id")
        for item in entities
        if item.get("entity_id") is not None
    }
    relationship_ids = {
        item.get("relationship_id")
        for item in relationships
        if item.get("relationship_id") is not None
    }

    # Entity evidence and source grounding.
    for index, entity in enumerate(entities):
        path = f"$.entities[{index}]"
        evidence = _text(entity.get("evidence")) or _text(entity.get("evidence_text"))
        if evidence is None:
            value = entity.get("normalized_value") or entity.get("value")
            evidence = value if isinstance(value, str) and value.strip() else None

        _check_evidence(
            findings,
            evidence=evidence,
            content=content,
            path=path,
            item=entity,
        )

    # Facts and claims must be traceable to the original source.
    for category in ("facts", "claims"):
        for index, semantic_item in enumerate(_items(semantics.get(category))):
            path = f"$.semantics.{category}[{index}]"
            evidence = _text(semantic_item.get("evidence"))
            if evidence is None:
                evidence = _text(semantic_item)

            _check_evidence(
                findings,
                evidence=evidence,
                content=content,
                path=path,
                item=semantic_item,
            )

            for key in ("subject_entity_id", "object_entity_id", "entity_id"):
                reference = semantic_item.get(key)
                if reference is not None and reference not in entity_ids:
                    findings.append(_finding(
                        "SEMANTIC_ENTITY_REFERENCE_UNRESOLVED",
                        f"{path}.{key}",
                        f"Semantic item references unknown entity: {reference}",
                    ))

    # Relationships must point to existing entities and, when supplied,
    # their evidence must be source-grounded.
    for index, relationship in enumerate(relationships):
        path = f"$.relationships[{index}]"

        for key in ("subject_entity_id", "object_entity_id"):
            reference = relationship.get(key)
            if reference is not None and reference not in entity_ids:
                findings.append(_finding(
                    "RELATIONSHIP_ENTITY_REFERENCE_UNRESOLVED",
                    f"{path}.{key}",
                    f"Relationship references unknown entity: {reference}",
                ))

        evidence = _text(relationship.get("evidence"))
        if evidence is not None:
            _check_evidence(
                findings,
                evidence=evidence,
                content=content,
                path=path,
                item=relationship,
            )

    # Context links must resolve to canonical entity and relationship IDs.
    for index, unit in enumerate(context_units):
        path = f"$.context.context_units[{index}]"

        for link_index, link in enumerate(_items(unit.get("entity_links", []))):
            reference = link.get("entity_id")
            if reference not in entity_ids:
                findings.append(_finding(
                    "CONTEXT_ENTITY_REFERENCE_UNRESOLVED",
                    f"{path}.entity_links[{link_index}].entity_id",
                    f"Context references unknown entity: {reference}",
                ))

        for link_index, link in enumerate(_items(unit.get("relationship_links", []))):
            reference = link.get("relationship_id")
            if reference not in relationship_ids:
                findings.append(_finding(
                    "CONTEXT_RELATIONSHIP_REFERENCE_UNRESOLVED",
                    f"{path}.relationship_links[{link_index}].relationship_id",
                    f"Context references unknown relationship: {reference}",
                ))

        unit_text = _text(unit.get("text"))
        if unit_text and content is not None and unit_text not in content:
            findings.append(_finding(
                "CONTEXT_NOT_GROUNDED",
                f"{path}.text",
                "Context unit text does not occur in original source content.",
                evidence={"context_text": unit_text},
            ))

    if dukr != snapshot:
        findings.append(_finding(
            "INPUT_MUTATED",
            "$",
            "Semantic validation modified the input DUKR.",
        ))

    return _report(
        findings,
        entity_count=len(entities),
        fact_count=sum(1 for _ in _items(semantics.get("facts"))),
        claim_count=sum(1 for _ in _items(semantics.get("claims"))),
        relationship_count=len(relationships),
        context_unit_count=len(context_units),
    )


def validate_dataset_semantics(
    dataset: Any,
    dukr_documents: Any,
) -> dict:
    """Check generated example evidence against its matching source DUKR."""

    if not isinstance(dataset, dict):
        return _report([
            _finding("DATASET_TYPE_INVALID", "$", "Dataset must be an object.")
        ])

    if not isinstance(dukr_documents, list):
        return _report([
            _finding(
                "DUKR_DOCUMENTS_TYPE_INVALID",
                "$.dukr_documents",
                "dukr_documents must be a list.",
            )
        ])

    snapshot = copy.deepcopy(dataset)
    findings: list[dict] = []

    source_map: dict[str, dict] = {}
    for index, dukr in enumerate(dukr_documents):
        if not isinstance(dukr, dict):
            findings.append(_finding(
                "DUKR_DOCUMENT_TYPE_INVALID",
                f"$.dukr_documents[{index}]",
                "Each DUKR document must be an object.",
            ))
            continue

        source = dukr.get("source")
        if not isinstance(source, dict) or not source.get("source_id"):
            findings.append(_finding(
                "DUKR_SOURCE_ID_MISSING",
                f"$.dukr_documents[{index}].source.source_id",
                "DUKR document has no source_id for dataset matching.",
            ))
            continue

        source_id = str(source["source_id"])
        if source_id in source_map:
            findings.append(_finding(
                "DUKR_SOURCE_ID_DUPLICATE",
                f"$.dukr_documents[{index}].source.source_id",
                f"Multiple DUKR documents use source_id {source_id}.",
            ))
        else:
            source_map[source_id] = dukr

    examples = dataset.get("examples")
    if not isinstance(examples, list):
        findings.append(_finding(
            "DATASET_EXAMPLES_INVALID",
            "$.examples",
            "Dataset examples must be a list.",
        ))
        return _report(findings)

    for index, example in enumerate(examples):
        path = f"$.examples[{index}]"

        if not isinstance(example, dict):
            findings.append(_finding(
                "DATASET_EXAMPLE_INVALID",
                path,
                "Dataset example must be an object.",
            ))
            continue

        provenance = example.get("provenance")
        if not isinstance(provenance, dict):
            findings.append(_finding(
                "DATASET_PROVENANCE_MISSING",
                f"{path}.provenance",
                "Dataset example has no provenance object.",
            ))
            continue

        source_id = provenance.get("source_id")
        if not source_id:
            findings.append(_finding(
                "DATASET_SOURCE_ID_MISSING",
                f"{path}.provenance.source_id",
                "Dataset example has no source_id.",
            ))
            continue

        dukr = source_map.get(str(source_id))
        if dukr is None:
            findings.append(_finding(
                "DATASET_SOURCE_UNRESOLVED",
                f"{path}.provenance.source_id",
                f"No input DUKR matches source_id {source_id}.",
            ))
            continue

        source = dukr.get("source", {})
        content = source.get("original_content")
        evidence = provenance.get("evidence_text")

        if not isinstance(evidence, str) or not evidence.strip():
            findings.append(_finding(
                "DATASET_EVIDENCE_MISSING",
                f"{path}.provenance.evidence_text",
                "Dataset example has no evidence_text.",
                "warning",
            ))
            continue

        if not isinstance(content, str):
            findings.append(_finding(
                "DATASET_SOURCE_CONTENT_UNAVAILABLE",
                f"{path}.provenance.evidence_text",
                "Matching DUKR has no original source content.",
                "warning",
            ))
            continue

        start = provenance.get("start_offset")
        end = provenance.get("end_offset")

        if start is not None or end is not None:
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end < start
                or end > len(content)
            ):
                findings.append(_finding(
                    "DATASET_EVIDENCE_OFFSETS_INVALID",
                    f"{path}.provenance",
                    "Dataset evidence offsets are invalid or outside source bounds.",
                ))
                continue

            if content[start:end] != evidence:
                findings.append(_finding(
                    "DATASET_EVIDENCE_OFFSET_MISMATCH",
                    f"{path}.provenance.evidence_text",
                    "Dataset evidence does not match its source at the supplied offsets.",
                    evidence={
                        "start_offset": start,
                        "end_offset": end,
                        "evidence_text": evidence,
                        "source_text": content[start:end],
                    },
                ))
        elif evidence not in content:
            findings.append(_finding(
                "DATASET_EVIDENCE_NOT_GROUNDED",
                f"{path}.provenance.evidence_text",
                "Dataset evidence does not occur in its declared source.",
                evidence={"evidence_text": evidence},
            ))

    if dataset != snapshot:
        findings.append(_finding(
            "INPUT_MUTATED",
            "$",
            "Dataset semantic validation modified the input.",
        ))

    return _report(
        findings,
        example_count=len(examples),
        source_count=len(source_map),
    )
