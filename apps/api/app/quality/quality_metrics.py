"""Explainable, evidence-backed quality metrics for DATUMOR DUKR."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.api.app.understanding.dukr_generator import validate_dukr

METRICS_VERSION = "0.1.0"

WEIGHTS = {
    "structural_integrity": 0.20,
    "content_preservation": 0.20,
    "evidence_coverage": 0.20,
    "provenance_completeness": 0.15,
    "semantic_linkage": 0.15,
    "context_completeness": 0.10,
}


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(100.0 * numerator / denominator, 2)


def _has_evidence(item: dict) -> bool:
    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        return False

    start = evidence.get("start_offset")
    end = evidence.get("end_offset")

    return (
        isinstance(start, int)
        and isinstance(end, int)
        and start >= 0
        and end > start
    )


def _provenance_present(source: dict) -> dict:
    fields = (
        "source_id",
        "project_id",
        "filename",
        "path",
        "checksum_sha256",
    )
    return {
        field: source.get(field) not in (None, "")
        for field in fields
    }


def _dimension(name: str, score: float | None, details: dict) -> dict:
    return {
        "name": name,
        "score": score,
        "status": (
            "not_assessed" if score is None
            else "pass" if score >= 90
            else "warning" if score >= 70
            else "fail"
        ),
        "details": details,
    }


def calculate_quality_metrics(dukr: dict) -> dict:
    """Calculate transparent quality dimensions from a DUKR document."""
    if not isinstance(dukr, dict):
        raise TypeError("dukr must be a dictionary.")

    if dukr.get("dukr_schema") != "datumor.dukr":
        raise ValueError("Unsupported DUKR schema.")

    source = dukr.get("source") or {}
    entities = dukr.get("entities") or []
    relationships = dukr.get("relationships") or []
    semantics = dukr.get("semantics") or {}
    statements = semantics.get("statements") or []
    context = dukr.get("context") or {}
    context_units = context.get("context_units") or []
    graph = dukr.get("knowledge_graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    for name, value in (
        ("entities", entities),
        ("relationships", relationships),
        ("statements", statements),
        ("context_units", context_units),
        ("graph nodes", nodes),
        ("graph edges", edges),
    ):
        if not isinstance(value, list):
            raise ValueError(f"DUKR {name} must be a list.")

    validation = validate_dukr(dukr)
    content = source.get("original_content")
    content = content if isinstance(content, str) else ""

    # Structural integrity
    node_ids = [node.get("node_id") for node in nodes]
    duplicate_node_ids = len(node_ids) - len(set(node_ids))
    structural_errors = len(validation.get("errors") or [])

    structural_score = max(
        0.0,
        100.0 - min(
            100.0,
            structural_errors * 20.0 + duplicate_node_ids * 20.0,
        ),
    )

    structural = _dimension(
        "structural_integrity",
        round(structural_score, 2),
        {
            "validation_passed": validation.get("valid", False),
            "validation_errors": validation.get("errors", []),
            "duplicate_node_ids": duplicate_node_ids,
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    )

    # Content preservation
    reconstructed = "".join(
        unit.get("text", "") for unit in context_units
    )
    context_available = bool(context_units) or not content
    exact_reconstruction = (
        reconstructed == content if context_available else None
    )
    expected_hash = source.get("content_sha256")
    hash_valid = (
        content is not None
        and expected_hash is not None
        and __import__("hashlib").sha256(
            content.encode("utf-8")
        ).hexdigest() == expected_hash
    ) if expected_hash else None

    preservation_checks = [
        value for value in (exact_reconstruction, hash_valid)
        if value is not None
    ]
    preservation_score = (
        round(100.0 * sum(preservation_checks) / len(preservation_checks), 2)
        if preservation_checks else None
    )

    preservation = _dimension(
        "content_preservation",
        preservation_score,
        {
            "context_available": context_available,
            "exact_reconstruction": exact_reconstruction,
            "content_hash_valid": hash_valid,
            "original_content_characters": len(content),
            "reconstructed_characters": len(reconstructed),
        },
    )

    # Evidence coverage across knowledge artifacts
    evidence_items = entities + relationships + statements
    evidence_count = sum(_has_evidence(item) for item in evidence_items)
    evidence_score = _ratio(evidence_count, len(evidence_items))

    evidence = _dimension(
        "evidence_coverage",
        evidence_score,
        {
            "artifacts_with_evidence": evidence_count,
            "artifact_count": len(evidence_items),
            "entities_with_evidence": sum(
                _has_evidence(item) for item in entities
            ),
            "relationships_with_evidence": sum(
                _has_evidence(item) for item in relationships
            ),
            "statements_with_evidence": sum(
                _has_evidence(item) for item in statements
            ),
        },
    )

    # Source provenance completeness
    provenance = _provenance_present(source)
    provenance_count = sum(provenance.values())
    provenance_score = _ratio(provenance_count, len(provenance))

    provenance_dimension = _dimension(
        "provenance_completeness",
        provenance_score,
        {
            "fields_present": provenance_count,
            "fields_expected": len(provenance),
            "field_status": provenance,
        },
    )

    # Semantic linkage: relationships must resolve to entities;
    # statements may link to entities through entity_ids.
    entity_ids = {
        item.get("entity_id")
        for item in entities
        if item.get("entity_id")
    }

    relationship_endpoints = []
    for relationship in relationships:
        relationship_endpoints.extend([
            relationship.get("subject_entity_id"),
            relationship.get("object_entity_id"),
        ])

    resolved_endpoints = sum(
        endpoint in entity_ids
        for endpoint in relationship_endpoints
    )
    endpoint_score = _ratio(
        resolved_endpoints, len(relationship_endpoints)
    )

    statement_references = [
        entity_id
        for statement in statements
        for entity_id in (statement.get("entity_ids") or [])
    ]
    resolved_statement_references = sum(
        entity_id in entity_ids for entity_id in statement_references
    )
    statement_link_score = _ratio(
        resolved_statement_references, len(statement_references)
    )

    linkage_checks = [
        score for score in (endpoint_score, statement_link_score)
        if score is not None
    ]
    linkage_score = (
        round(sum(linkage_checks) / len(linkage_checks), 2)
        if linkage_checks else None
    )

    linkage = _dimension(
        "semantic_linkage",
        linkage_score,
        {
            "relationship_endpoints_resolved": resolved_endpoints,
            "relationship_endpoint_count": len(relationship_endpoints),
            "statement_entity_references_resolved": (
                resolved_statement_references
            ),
            "statement_entity_reference_count": len(statement_references),
        },
    )

    # Context completeness
    sentence_count = sum(
        len(unit.get("sentences") or []) for unit in context_units
    )
    context_checks = {
        "context_units_present": bool(context_units) or not content,
        "context_summary_matches": (
            context.get("summary", {}).get("context_unit_count")
            == len(context_units)
            if context.get("summary") else False
        ),
        "sentences_present": sentence_count > 0 or not content,
        "context_links_valid": validation.get(
            "checks", {}
        ).get("context_references_resolved", False),
    }
    context_score = round(
        100.0 * sum(context_checks.values()) / len(context_checks), 2
    )

    context_dimension = _dimension(
        "context_completeness",
        context_score,
        {
            "context_unit_count": len(context_units),
            "sentence_count": sentence_count,
            "checks": context_checks,
        },
    )

    dimensions = [
        structural,
        preservation,
        evidence,
        provenance_dimension,
        linkage,
        context_dimension,
    ]

    assessed_weight = sum(
        WEIGHTS[dimension["name"]]
        for dimension in dimensions
        if dimension["score"] is not None
    )

    weighted_score = (
        round(
            sum(
                dimension["score"] * WEIGHTS[dimension["name"]]
                for dimension in dimensions
                if dimension["score"] is not None
            ) / assessed_weight,
            2,
        )
        if assessed_weight else None
    )

    # Missing dimensions cannot silently earn full credit.
    if weighted_score is not None and assessed_weight < 1.0:
        weighted_score = round(
            weighted_score * assessed_weight, 2
        )

    warnings = list(validation.get("warnings") or [])
    warnings.extend(
        f"{dimension['name']} is not assessable for this input."
        for dimension in dimensions
        if dimension["score"] is None
    )
    warnings.extend(
        f"{dimension['name']} scored {dimension['score']}."
        for dimension in dimensions
        if dimension["score"] is not None
        and dimension["score"] < 90
    )

    return {
        "metrics_schema": "datumor.quality_metrics",
        "metrics_version": METRICS_VERSION,
        "representation_id": dukr.get("representation_id"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "overall_score": weighted_score,
        "overall_status": (
            "not_assessed" if weighted_score is None
            else "pass" if weighted_score >= 90
            else "warning" if weighted_score >= 70
            else "fail"
        ),
        "dimensions": {
            dimension["name"]: dimension
            for dimension in dimensions
        },
        "weights": WEIGHTS,
        "assessed_weight": round(assessed_weight, 4),
        "counts": {
            "entities": len(entities),
            "relationships": len(relationships),
            "statements": len(statements),
            "context_units": len(context_units),
            "graph_nodes": len(nodes),
            "graph_edges": len(edges),
            "source_characters": len(content),
        },
        "warnings": warnings,
        "validation": validation,
    }
