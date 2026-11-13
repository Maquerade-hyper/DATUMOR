"""DATUMOR Universal Knowledge Representation (DUKR) generator."""

from __future__ import annotations

import hashlib
import json

DUKR_SCHEMA_VERSION = "1.0.0"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source(extraction: dict) -> dict:
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
        "format": extraction.get("format"),
        "media_type": (
            source_identity.get("media_type")
            or source_metadata.get("media_type")
        ),
        "checksum_sha256": (
            source_identity.get("checksum_sha256")
            or source_metadata.get("checksum_sha256")
            or extraction.get("checksum_sha256")
        ),
    }

def _evidence(item: dict) -> dict:
    value = item.get("evidence")
    return value if isinstance(value, dict) else {}


def _stable_id(prefix: str, identity: str, index: int, item: dict) -> str:
    supplied = (
        item.get("entity_id")
        or item.get("relationship_id")
        or item.get("statement_id")
        or item.get("context_unit_id")
    )
    if supplied:
        return str(supplied)

    evidence = _evidence(item)
    material = json.dumps(
        {
            "identity": identity,
            "index": index,
            "value": item.get("value") or item.get("text"),
            "start": evidence.get("start_offset", item.get("start_offset")),
            "end": evidence.get("end_offset", item.get("end_offset")),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return f"{prefix}_{_digest(material)[:24]}"


def _statement_items(semantic: dict) -> list[dict]:
    statements = []

    for key, default_status in (
        ("facts", "observed"),
        ("claims", "observed_claim"),
    ):
        items = semantic.get(key) or []
        if not isinstance(items, list):
            raise ValueError(f"semantic_result.{key} must be a list.")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"semantic_result.{key} contains an invalid item.")

            statement = dict(item)
            statement.setdefault("epistemic_status", default_status)
            statement["statement_kind"] = key[:-1] if key.endswith("s") else key
            statements.append(statement)

    return statements


def validate_dukr(dukr: dict) -> dict:
    """Validate internal references, provenance and lossless content."""
    errors = []
    warnings = []

    if not isinstance(dukr, dict):
        return {"valid": False, "errors": ["DUKR must be a dictionary."], "warnings": []}

    graph = dukr.get("knowledge_graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    node_ids = [node.get("node_id") for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("Duplicate knowledge graph node identifiers.")

    known_nodes = set(node_ids)
    for edge in edges:
        if edge.get("subject_node_id") not in known_nodes:
            errors.append(
                f"Relationship subject reference is unresolved: {edge.get('subject_node_id')}"
            )
        if edge.get("object_node_id") not in known_nodes:
            errors.append(
                f"Relationship object reference is unresolved: {edge.get('object_node_id')}"
            )

    entity_ids = {
        entity.get("entity_id")
        for entity in dukr.get("entities", [])
        if entity.get("entity_id")
    }

    for relationship in dukr.get("relationships", []):
        subject_id = relationship.get("subject_entity_id")
        object_id = relationship.get("object_entity_id")

        if subject_id not in entity_ids:
            errors.append(
                f"Canonical relationship subject reference is unresolved: {subject_id}"
            )
        if object_id not in entity_ids:
            errors.append(
                f"Canonical relationship object reference is unresolved: {object_id}"
            )
    relationship_ids = {
        relationship.get("relationship_id")
        for relationship in dukr.get("relationships", [])
        if relationship.get("relationship_id")
    }

    for unit in dukr.get("context", {}).get("context_units", []):
        for link in unit.get("entity_links", []):
            if link.get("entity_id") not in entity_ids:
                errors.append(
                    f"Context references unknown entity: {link.get('entity_id')}"
                )
        for link in unit.get("relationship_links", []):
            if link.get("relationship_id") not in relationship_ids:
                errors.append(
                    "Context references unknown relationship: "
                    f"{link.get('relationship_id')}"
                )

    original = dukr.get("source", {}).get("original_content", "")
    context_units = dukr.get("context", {}).get("context_units", [])
    context_reconstruction_verified = False

    if context_units:
        reconstructed = "".join(unit.get("text", "") for unit in context_units)
        context_reconstruction_verified = reconstructed == original
        if not context_reconstruction_verified:
            errors.append("Context units do not reconstruct original source content.")
    elif original:
        warnings.append(
            "No context units supplied; lossless context reconstruction was not verified."
        )
    else:
        context_reconstruction_verified = True

    expected_hash = dukr.get("source", {}).get("content_sha256")
    if expected_hash and _digest(original) != expected_hash:
        errors.append("Original source content checksum mismatch.")

    if not dukr.get("source", {}).get("source_id"):
        warnings.append("No source_id was supplied by upstream ingestion.")

    if not dukr.get("source", {}).get("checksum_sha256"):
        warnings.append("No ingestion checksum was supplied by upstream ingestion.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "unique_node_ids": len(node_ids) == len(set(node_ids)),
            "relationship_endpoints_resolved": not any(
                "Relationship subject" in error
                or "Relationship object" in error
                for error in errors
            ),
            "context_references_resolved": not any(
                "Context references" in error for error in errors
            ),
            "lossless_content": context_reconstruction_verified,
            "content_checksum": not any(
                "checksum mismatch" in error for error in errors
            ),
        },
    }


def generate_dukr(
    extraction_result: dict,
    entity_result: dict | None = None,
    semantic_result: dict | None = None,
    relationship_result: dict | None = None,
    context_result: dict | None = None,
) -> dict:
    """Combine M2 and M3 outputs into a validated, model-independent DUKR."""
    if not isinstance(extraction_result, dict):
        raise TypeError("extraction_result must be a dictionary.")

    content = extraction_result.get("content")
    if not isinstance(content, str):
        raise ValueError("M2 extraction result must contain string content.")

    inputs = {
        "entity_result": entity_result,
        "semantic_result": semantic_result,
        "relationship_result": relationship_result,
        "context_result": context_result,
    }
    for name, value in inputs.items():
        if value is not None and not isinstance(value, dict):
            raise TypeError(f"{name} must be a dictionary when supplied.")

    entity_result = entity_result or {}
    semantic_result = semantic_result or {}
    relationship_result = relationship_result or {}
    context_result = context_result or {}

    entities = entity_result.get("entities") or []
    relationships = relationship_result.get("relationships") or []
    context_units = context_result.get("context_units") or []

    for name, collection in (
        ("entities", entities),
        ("relationships", relationships),
        ("context_units", context_units),
    ):
        if not isinstance(collection, list):
            raise ValueError(f"{name} must be a list.")
        if not all(isinstance(item, dict) for item in collection):
            raise ValueError(f"{name} must contain dictionaries.")

    statements = _statement_items(semantic_result)
    source = _source(extraction_result)
    content_hash = _digest(content)
    identity = source.get("checksum_sha256") or content_hash

    canonical_entities = []
    entity_node_ids = {}

    for index, entity in enumerate(entities):
        entity_id = _stable_id("entity", identity, index, entity)
        if entity_id in entity_node_ids:
            raise ValueError(f"Duplicate entity identifier: {entity_id}")

        entity_node_ids[entity_id] = entity_id
        canonical_entities.append({
            "entity_id": entity_id,
            "entity_type": entity.get("entity_type"),
            "value": entity.get("value"),
            "normalized_value": entity.get("normalized_value"),
            "confidence": entity.get("confidence"),
            "extraction_method": entity.get("method"),
            "evidence": _evidence(entity),
            "provenance": {
                "source_id": source.get("source_id"),
                "source_filename": source.get("filename"),
                "source_checksum_sha256": source.get("checksum_sha256"),
            },
            "upstream": entity,
        })

    canonical_relationships = []
    for index, relationship in enumerate(relationships):
        relationship_id = _stable_id(
            "relationship", identity, index, relationship
        )
        subject = relationship.get("subject") or {}
        object_ = relationship.get("object") or {}

        subject_id = subject.get("entity_id")
        object_id = object_.get("entity_id")

        canonical_relationships.append({
            "relationship_id": relationship_id,
            "subject_entity_id": subject_id,
            "predicate": relationship.get("predicate"),
            "object_entity_id": object_id,
            "direction": relationship.get("direction"),
            "confidence": relationship.get("confidence"),
            "extraction_method": relationship.get("extraction_method"),
            "evidence": _evidence(relationship),
            "provenance": relationship.get("provenance") or {
                "source_id": source.get("source_id"),
                "source_checksum_sha256": source.get("checksum_sha256"),
            },
            "upstream": relationship,
        })

    canonical_statements = []
    for index, statement in enumerate(statements):
        statement_id = _stable_id("statement", identity, index, statement)
        canonical_statements.append({
            "statement_id": statement_id,
            "statement_kind": statement.get("statement_kind"),
            "text": statement.get("text"),
            "epistemic_status": statement.get("epistemic_status"),
            "confidence": statement.get("confidence"),
            "evidence": _evidence(statement),
            "entity_ids": statement.get("entity_ids") or [],
            "provenance": {
                "source_id": source.get("source_id"),
                "source_checksum_sha256": source.get("checksum_sha256"),
            },
            "upstream": statement,
        })

    nodes = []
    for entity in canonical_entities:
        nodes.append({
            "node_id": entity["entity_id"],
            "node_type": "entity",
            "label": entity.get("value"),
            "entity_type": entity.get("entity_type"),
        })

    statement_node_ids = {}
    for statement in canonical_statements:
        node_id = f"statement_{statement['statement_id']}"
        statement_node_ids[statement["statement_id"]] = node_id
        nodes.append({
            "node_id": node_id,
            "node_type": "statement",
            "label": statement.get("text"),
            "epistemic_status": statement.get("epistemic_status"),
        })

    edges = []
    for relationship in canonical_relationships:
        edges.append({
            "edge_id": relationship["relationship_id"],
            "edge_type": "semantic_relationship",
            "subject_node_id": relationship["subject_entity_id"],
            "predicate": relationship.get("predicate"),
            "object_node_id": relationship["object_entity_id"],
            "confidence": relationship.get("confidence"),
            "evidence": relationship.get("evidence"),
        })

    for statement in canonical_statements:
        statement_node_id = statement_node_ids[statement["statement_id"]]
        for entity_id in statement.get("entity_ids", []):
            edges.append({
                "edge_id": f"{statement['statement_id']}:{entity_id}",
                "edge_type": "statement_mentions_entity",
                "subject_node_id": statement_node_id,
                "predicate": "mentions",
                "object_node_id": entity_id,
            })

    semantic_summary = {
        key: semantic_result.get(key)
        for key in (
            "overview", "summary", "topics", "content_classifications",
            "classifications", "intents", "observed_subjects", "warnings"
        )
        if key in semantic_result
    }

    if context_units:
        reconstructed = "".join(
            unit.get("text", "") for unit in context_units
        )
        if reconstructed != content:
            raise ValueError(
                "M3.4 context units do not exactly reconstruct M2 content."
            )

    dukr = {
        "dukr_schema": "datumor.dukr",
        "dukr_schema_version": DUKR_SCHEMA_VERSION,
        "representation_id": f"dukr_{content_hash[:24]}",
        "source": {
            **source,
            "original_content": content,
            "content_length": len(content),
            "content_sha256": content_hash,
            "source_metadata": extraction_result.get("metadata") or {},
            "source_records": extraction_result.get("records") or [],
            "extraction_warnings": extraction_result.get("warnings") or [],
        },
        "entities": canonical_entities,
        "semantics": {
            "summary": semantic_summary,
            "statements": canonical_statements,
            "upstream": semantic_result,
        },
        "relationships": canonical_relationships,
        "context": {
            "context_schema_version": context_result.get(
                "context_schema_version"
            ),
            "context_units": context_units,
            "summary": context_result.get("summary") or {},
            "warnings": context_result.get("warnings") or [],
        },
        "knowledge_graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "upstream_artifacts": {
            "entity_result": entity_result,
            "semantic_result": semantic_result,
            "relationship_result": relationship_result,
            "context_result": context_result,
        },
    }

    validation = validate_dukr(dukr)
    dukr["validation"] = validation

    return dukr
