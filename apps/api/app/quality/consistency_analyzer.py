"""Evidence-backed cross-document consistency analysis for DATUMOR."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone

from apps.api.app.understanding.dukr_generator import validate_dukr

ANALYZER_VERSION = "0.1.0"

NEGATION_PATTERN = re.compile(
    r"\b(not|never|no|cannot|can't|doesn't|does not|isn't|is not|"
    r"wasn't|was not|aren't|are not|without|neither)\b",
    re.IGNORECASE,
)

TEMPORAL_PATTERN = re.compile(
    r"\b(19\d{2}|20\d{2}|21\d{2}|"
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"today|yesterday|currently|previously|formerly|"
    r"since|until|between)\b",
    re.IGNORECASE,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _source_ref(dukr: dict, index: int) -> dict:
    source = dukr.get("source") or {}
    return {
        "document_index": index,
        "representation_id": dukr.get("representation_id"),
        "source_id": source.get("source_id"),
        "project_id": source.get("project_id"),
        "filename": source.get("filename"),
        "path": source.get("path"),
        "checksum_sha256": source.get("checksum_sha256"),
    }


def _finding(
    category: str,
    finding_type: str,
    severity: str,
    description: str,
    sources: list[dict],
    evidence: list[dict],
    confidence: float,
    review_required: bool = True,
) -> dict:
    identity = (
        category + "|" + finding_type + "|" +
        "|".join(
            str(source.get("source_id") or source.get("document_index"))
            for source in sources
        ) + "|" + description
    )

    return {
        "finding_id": "consistency_" + _digest(identity)[:24],
        "category": category,
        "finding_type": finding_type,
        "severity": severity,
        "description": description,
        "confidence": confidence,
        "sources": sources,
        "evidence": evidence,
        "review_required": review_required,
        "resolution_status": "unresolved",
        "automatic_changes_made": False,
    }


def _validate_document(dukr: dict, index: int) -> list[dict]:
    findings = []
    validation = validate_dukr(dukr)
    source = _source_ref(dukr, index)

    for error in validation.get("errors", []):
        findings.append(
            _finding(
                "structural",
                "dukr_integrity_error",
                "high",
                error,
                [source],
                [],
                1.0,
            )
        )

    graph = dukr.get("knowledge_graph") or {}
    node_ids = [
        node.get("node_id")
        for node in graph.get("nodes", [])
    ]

    if len(node_ids) != len(set(node_ids)):
        findings.append(
            _finding(
                "structural",
                "duplicate_graph_node_id",
                "high",
                "Knowledge graph contains duplicate node identifiers.",
                [source],
                [],
                1.0,
            )
        )

    return findings


def _entity_analysis(documents: list[dict]) -> list[dict]:
    findings = []
    groups = defaultdict(list)

    for document in documents:
        dukr = document["dukr"]
        source = document["source"]

        for entity in dukr.get("entities", []):
            key = (
                _normalized(entity.get("entity_type")),
                _normalized(
                    entity.get("normalized_value")
                    or entity.get("value")
                ),
            )

            if not key[0] or not key[1]:
                continue

            groups[key].append({
                "source": source,
                "entity": entity,
            })

    for (entity_type, normalized_value), occurrences in groups.items():
        source_ids = {
            occurrence["source"].get("source_id")
            for occurrence in occurrences
            if occurrence["source"].get("source_id") is not None
        }

        if len(source_ids) < 2:
            continue

        display_values = {}
        for occurrence in occurrences:
            value = occurrence["entity"].get("value")
            if isinstance(value, str):
                display_values.setdefault(value, []).append(occurrence)

        if len(display_values) > 1:
            sources = []
            evidence = []

            for value, value_occurrences in display_values.items():
                for occurrence in value_occurrences:
                    sources.append(occurrence["source"])
                    entity = occurrence["entity"]
                    evidence.append({
                        "entity_id": entity.get("entity_id"),
                        "entity_type": entity.get("entity_type"),
                        "value": value,
                        "normalized_value": entity.get("normalized_value"),
                        "evidence": entity.get("evidence") or {},
                    })

            findings.append(
                _finding(
                    "entity",
                    "entity_representation_variance",
                    "low",
                    (
                        f"Entity key '{entity_type}:{normalized_value}' "
                        "has multiple display representations across sources. "
                        "This is a representation difference, not proof "
                        "of contradictory identity."
                    ),
                    sources,
                    evidence,
                    0.95,
                )
            )

    return findings


def _relationship_analysis(documents: list[dict]) -> list[dict]:
    findings = []
    groups = defaultdict(list)

    for document in documents:
        dukr = document["dukr"]
        source = document["source"]

        entities = {
            entity.get("entity_id"): entity
            for entity in dukr.get("entities", [])
            if entity.get("entity_id")
        }

        for relationship in dukr.get("relationships", []):
            subject = entities.get(
                relationship.get("subject_entity_id"), {}
            )
            object_ = entities.get(
                relationship.get("object_entity_id"), {}
            )

            subject_key = (
                _normalized(subject.get("entity_type")),
                _normalized(
                    subject.get("normalized_value")
                    or subject.get("value")
                ),
            )
            object_key = (
                _normalized(object_.get("entity_type")),
                _normalized(
                    object_.get("normalized_value")
                    or object_.get("value")
                ),
            )
            predicate = _normalized(relationship.get("predicate"))

            if not all(subject_key) or not all(object_key) or not predicate:
                continue

            key = (subject_key, predicate)
            groups[key].append({
                "source": source,
                "relationship": relationship,
                "subject": subject,
                "object": object_,
                "object_key": object_key,
            })

    for (subject_key, predicate), occurrences in groups.items():
        by_source = defaultdict(list)
        for occurrence in occurrences:
            source_id = occurrence["source"].get("source_id")
            if source_id is not None:
                by_source[source_id].append(occurrence)

        # A disagreement within one source may be legitimate multi-valued
        # information. Cross-source disagreement is reported for review.
        if len(by_source) < 2:
            continue

        object_keys = {
            occurrence["object_key"] for occurrence in occurrences
        }

        if len(object_keys) < 2:
            continue

        sources = []
        evidence = []

        for occurrence in occurrences:
            sources.append(occurrence["source"])
            relationship = occurrence["relationship"]
            evidence.append({
                "subject": occurrence["subject"].get("value"),
                "predicate": relationship.get("predicate"),
                "object": occurrence["object"].get("value"),
                "relationship_id": relationship.get("relationship_id"),
                "evidence": relationship.get("evidence") or {},
            })

        findings.append(
            _finding(
                "relationship",
                "relationship_object_disagreement",
                "medium",
                (
                    f"Sources disagree on the object of "
                    f"{subject_key[0]}:{subject_key[1]} "
                    f"with predicate '{predicate}'. "
                    "Temporal, contextual and multi-valued explanations "
                    "must be reviewed before classifying this as a conflict."
                ),
                sources,
                evidence,
                0.85,
            )
        )

    return findings


def _semantic_proposition(text: str) -> tuple[str, bool, bool]:
    """Normalize a statement for conservative polarity comparison."""
    normalized = _normalized(text)

    # Detect negation before removing it from the comparison proposition.
    polarity = bool(NEGATION_PATTERN.search(normalized))
    temporal_context = bool(TEMPORAL_PATTERN.search(normalized))

    proposition = NEGATION_PATTERN.sub(" ", normalized)

    # Remove temporal tokens from the comparison key. Their original
    # presence remains recorded in evidence and affects severity.
    proposition = TEMPORAL_PATTERN.sub(" ", proposition)

    # Normalize common inflection differences such as develops/develop
    # and supports/supports. This is intentionally a small deterministic
    # suffix normalizer, not a full linguistic stemmer.
    tokens = []
    for token in proposition.split():
        if len(token) > 5 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 5 and token.endswith("ing"):
            token = token[:-3]
        elif len(token) > 4 and token.endswith("ed"):
            token = token[:-2]
        elif len(token) > 4 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 3 and token.endswith("s"):
            token = token[:-1]

        tokens.append(token)

    return " ".join(tokens), polarity, temporal_context


def _semantic_analysis(documents: list[dict]) -> list[dict]:
    findings = []
    groups = defaultdict(list)

    for document in documents:
        dukr = document["dukr"]
        source = document["source"]

        for statement in (
            dukr.get("semantics", {}).get("statements", [])
        ):
            text = statement.get("text")
            if not isinstance(text, str) or not text.strip():
                continue

            proposition, polarity, temporal_context = (
                _semantic_proposition(text)
            )

            if not proposition:
                continue

            groups[proposition].append({
                "source": source,
                "statement": statement,
                "polarity": polarity,
                "temporal_context": temporal_context,
            })

    for proposition, occurrences in groups.items():
        source_ids = {
            occurrence["source"].get("source_id")
            for occurrence in occurrences
            if occurrence["source"].get("source_id") is not None
        }

        if len(source_ids) < 2:
            continue

        polarities = {
            occurrence["polarity"] for occurrence in occurrences
        }

        if len(polarities) < 2:
            continue

        sources = []
        evidence = []
        has_temporal_context = False

        for occurrence in occurrences:
            sources.append(occurrence["source"])
            statement = occurrence["statement"]
            has_temporal_context = (
                has_temporal_context or occurrence["temporal_context"]
            )

            evidence.append({
                "statement_id": statement.get("statement_id"),
                "text": statement.get("text"),
                "epistemic_status": statement.get("epistemic_status"),
                "polarity": occurrence["polarity"],
                "temporal_context_detected": occurrence["temporal_context"],
                "evidence": statement.get("evidence") or {},
            })

        findings.append(
            _finding(
                "semantic",
                "opposing_statement_polarity",
                "medium" if has_temporal_context else "high",
                (
                    "Sources contain statements with potentially opposing "
                    "polarity and similar wording. "
                    + (
                        "Temporal language was detected; the statements "
                        "may describe different periods."
                        if has_temporal_context
                        else "Review context before treating them as a contradiction."
                    )
                ),
                sources,
                evidence,
                0.70,
            )
        )

    return findings


def analyze_consistency(dukr_documents: list[dict]) -> dict:
    """Analyze structural, entity, relationship and semantic consistency."""
    if not isinstance(dukr_documents, list):
        raise TypeError("dukr_documents must be a list.")

    documents = []

    for index, dukr in enumerate(dukr_documents):
        if not isinstance(dukr, dict):
            raise TypeError(
                f"Document at index {index} must be a dictionary."
            )

        if dukr.get("dukr_schema") != "datumor.dukr":
            raise ValueError(
                f"Document at index {index} has an unsupported DUKR schema."
            )

        source = _source_ref(dukr, index)
        documents.append({
            "dukr": dukr,
            "source": source,
        })

    findings = []

    for index, document in enumerate(documents):
        findings.extend(
            _validate_document(document["dukr"], index)
        )

    findings.extend(_entity_analysis(documents))
    findings.extend(_relationship_analysis(documents))
    findings.extend(_semantic_analysis(documents))

    findings.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(
                item["severity"], 3
            ),
            item["category"],
            item["finding_id"],
        )
    )

    counts = {
        category: sum(
            finding["category"] == category for finding in findings
        )
        for category in (
            "structural", "entity", "relationship", "semantic"
        )
    }

    severity_counts = {
        severity: sum(
            finding["severity"] == severity for finding in findings
        )
        for severity in ("high", "medium", "low")
    }

    return {
        "report_schema": "datumor.consistency_report",
        "analyzer_version": ANALYZER_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "documents_analyzed": len(documents),
            "findings_count": len(findings),
            "category_counts": counts,
            "severity_counts": severity_counts,
            "automatic_changes_made": False,
        },
        "findings": findings,
        "warnings": [
            "Consistency findings are candidates for review, not automatic corrections.",
            "Entity identity resolution is limited to matching entity type and normalized value.",
            "Relationship disagreements may be temporal, contextual or multi-valued.",
            "Semantic polarity matching uses deterministic lexical heuristics, not full natural-language reasoning.",
            "No source data or DUKR artifact is modified.",
        ],
    }
