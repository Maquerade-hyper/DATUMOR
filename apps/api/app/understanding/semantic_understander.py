"""Deterministic, source-grounded semantic understanding for DATUMOR."""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from apps.api.app.understanding.entity_extractor import extract_entities

SEMANTIC_SCHEMA_VERSION = "0.1.0"

DOMAIN_TERMS = {
    "software_engineering": {
        "software", "programming", "code", "python", "javascript",
        "typescript", "api", "database", "backend", "frontend",
        "fastapi", "react", "postgresql", "algorithm", "function",
        "class", "repository", "deployment",
    },
    "artificial_intelligence": {
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "model", "training", "inference", "embedding",
        "tokenization", "dataset", "llm", "transformer",
    },
    "business": {
        "business", "company", "customer", "revenue", "market",
        "product", "service", "pricing", "subscription", "sales",
    },
    "science": {
        "experiment", "research", "hypothesis", "analysis",
        "measurement", "observation", "scientific",
    },
    "education": {
        "education", "student", "teacher", "course", "lesson",
        "learning", "university", "school", "assignment",
    },
    "healthcare": {
        "patient", "clinical", "diagnosis", "treatment", "medical",
        "health", "hospital", "medicine",
    },
    "finance": {
        "financial", "finance", "investment", "profit", "loss",
        "budget", "payment", "invoice", "cost", "revenue",
    },
}

INTENT_PATTERNS = {
    "instructional": (
        r"\b(?:follow these steps|how to|step \d+|install|configure|"
        r"run the following|you should|must be)\b",
    ),
    "request": (
        r"\b(?:please|request|could you|would you|we need|"
        r"i need|submit|provide)\b",
    ),
    "scheduling": (
        r"\b(?:scheduled|schedule|deadline|appointment|meeting|"
        r"due date|will take place|on \d{4}-\d{2}-\d{2})\b",
    ),
    "explanatory": (
        r"\b(?:because|therefore|this means|in other words|"
        r"consists of|works by|is defined as)\b",
    ),
    "informational": (
        r"\b(?:is|are|was|were|includes|contains|provides|"
        r"develops|supports|uses)\b",
    ),
}

CONTENT_PATTERNS = {
    "technical_documentation": (
        r"\b(?:api|endpoint|function|class|database|install|"
        r"configuration|implementation|software|code)\b",
    ),
    "report": (
        r"\b(?:report|results|findings|summary|analysis|"
        r"conclusion|performance)\b",
    ),
    "communication": (
        r"\b(?:dear|hello|regards|sincerely|please contact|"
        r"contact us|email)\b",
    ),
    "schedule": (
        r"\b(?:schedule|deadline|appointment|meeting|"
        r"202\d-\d{2}-\d{2})\b",
    ),
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _sentences(content: str) -> list[dict]:
    """Split content while retaining exact character offsets."""
    results = []
    pattern = re.compile(r"\S(?:.*?\S)?(?<=[.!?])(?=\s|$)", re.DOTALL)

    for match in pattern.finditer(content):
        value = match.group(0).strip()
        if not value:
            continue

        start = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
        end = start + len(value)
        results.append({
            "text": value,
            "start_offset": start,
            "end_offset": end,
            "start_line": content.count("\n", 0, start) + 1,
            "end_line": content.count("\n", 0, max(start, end - 1)) + 1,
        })

    if not results and content.strip():
        start = len(content) - len(content.lstrip())
        value = content.strip()
        results.append({
            "text": value,
            "start_offset": start,
            "end_offset": start + len(value),
            "start_line": content.count("\n", 0, start) + 1,
            "end_line": content.count("\n", 0, start + len(value) - 1) + 1,
        })

    return results


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

def _detect_topics(content: str, entities: list[dict]) -> list[dict]:
    normalized = _normalize(content)
    topics = []

    for domain, terms in DOMAIN_TERMS.items():
        matches = []
        for term in sorted(terms, key=len, reverse=True):
            pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
            count = len(re.findall(pattern, normalized))
            if count:
                matches.append({"term": term, "occurrences": count})

        if matches:
            score = min(
                0.99,
                0.55 + sum(item["occurrences"] for item in matches) * 0.08,
            )
            topics.append({
                "topic": domain,
                "confidence": round(score, 2),
                "matched_terms": matches,
                "classification_method": "domain_lexicon",
            })

    entity_types = Counter(
        item.get("entity_type", "unknown") for item in entities
    )
    if entity_types:
        topics.append({
            "topic": "entity_rich_content",
            "confidence": 0.70,
            "matched_terms": [
                {"term": kind, "occurrences": count}
                for kind, count in sorted(entity_types.items())
            ],
            "classification_method": "entity_distribution",
        })

    return sorted(
        topics,
        key=lambda item: (-item["confidence"], item["topic"]),
    )


def _classify_content(content: str) -> list[dict]:
    normalized = _normalize(content)
    classifications = []

    for label, patterns in CONTENT_PATTERNS.items():
        matches = [
            pattern for pattern in patterns
            if re.search(pattern, normalized)
        ]
        if matches:
            classifications.append({
                "label": label,
                "confidence": min(0.95, 0.65 + 0.10 * len(matches)),
                "matched_patterns": matches,
                "method": "rule_based",
            })

    if not classifications:
        classifications.append({
            "label": "general_text",
            "confidence": 0.60,
            "matched_patterns": [],
            "method": "fallback",
        })

    return classifications


def _detect_intents(sentences: list[dict]) -> list[dict]:
    matches = []

    for sentence in sentences:
        normalized = sentence["text"].casefold()
        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, normalized)
                if match:
                    matches.append({
                        "intent": intent,
                        "confidence": 0.82,
                        "evidence": {
                            "text": sentence["text"],
                            "start_offset": sentence["start_offset"],
                            "end_offset": sentence["end_offset"],
                            "start_line": sentence["start_line"],
                            "end_line": sentence["end_line"],
                            "matched_text": match.group(0),
                        },
                        "method": "rule_based",
                    })
                    break

    if not matches:
        matches.append({
            "intent": "informational",
            "confidence": 0.50,
            "evidence": None,
            "method": "fallback",
        })

    unique = {}
    for item in matches:
        key = (
            item["intent"],
            item["evidence"]["start_offset"] if item["evidence"] else None,
        )
        unique[key] = item

    return list(unique.values())


def _extract_facts_and_claims(
    sentences: list[dict],
    entities: list[dict],
) -> tuple[list[dict], list[dict]]:
    facts = []
    claims = []

    for sentence in sentences:
        text = sentence["text"]
        normalized = text.casefold()

        if len(text.split()) < 3:
            continue

        referenced_entities = []
        for entity in entities:
            value = entity.get("value", "")
            if value and value.casefold() in normalized:
                referenced_entities.append(entity["entity_id"])

        evidence = {
            "text": text,
            "matched_text": text,
            "start_offset": sentence["start_offset"],
            "end_offset": sentence["end_offset"],
            "start_line": sentence["start_line"],
            "end_line": sentence["end_line"],
            "page_number": None,
            "entity_ids": referenced_entities,
        }

        material = (
            f"{sentence['start_offset']}|{sentence['end_offset']}|{text}"
        )
        statement_id = hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()

        statement = {
            "statement_id": statement_id,
            "text": text,
            "statement_type": "source_observation",
            "epistemic_status": "observed",
            "confidence": 1.0,
            "evidence": evidence,
        }

        facts.append(statement)

        claims.append({
            **statement,
            "claim_type": "source_assertion",
            "interpretation": None,
        })

    return facts, claims


def understand_semantics(
    extraction_result: dict,
    entity_result: dict | None = None,
) -> dict:
    """Generate model-independent semantic understanding from M2 output."""
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
    topics = _detect_topics(content, entities)
    classifications = _classify_content(content)
    intents = _detect_intents(sentences)
    facts, claims = _extract_facts_and_claims(sentences, entities)

    observed_subjects = sorted({
        entity.get("normalized_value")
        for entity in entities
        if entity.get("normalized_value")
    })

    primary_topic = topics[0]["topic"] if topics else "unclassified"

    # This is an interpretation, not a source-stated fact.
    inferred_overview = {
        "text": (
            f"The content appears primarily related to {primary_topic.replace('_', ' ')}."
            if topics else
            "The content could not be assigned a reliable domain topic."
        ),
        "epistemic_status": "inferred",
        "confidence": topics[0]["confidence"] if topics else 0.30,
        "method": "topic_aggregation",
        "evidence": [
            item["topic"] for item in topics
        ],
    }

    return {
        "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
        "source": _source_identity(extraction_result),
        "overview": inferred_overview,
        "subjects": {
            "observed_entities": observed_subjects,
            "entity_count": len(entities),
        },
        "topics": topics,
        "classifications": classifications,
        "intents": intents,
        "facts": facts,
        "claims": claims,
        "summary": {
            "sentence_count": len(sentences),
            "topic_count": len(topics),
            "classification_count": len(classifications),
            "intent_count": len(intents),
            "fact_count": len(facts),
            "claim_count": len(claims),
            "observed_statement_count": len(facts),
            "inferred_statement_count": 1,
        },
        "warnings": [
            "Semantic analysis uses deterministic rules and lexical signals.",
            "Topic, classification and intent predictions are heuristic.",
            "Source observations preserve original statements; they are not independently verified facts.",
            "The overview is an inference and must not be treated as source text.",
        ],
    }
