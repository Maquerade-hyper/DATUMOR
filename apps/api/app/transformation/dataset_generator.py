"""Evidence-grounded, profile-specific AI training dataset generation."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
import json
from datetime import datetime, timezone

from apps.api.app.transformation.profile_registry import validate_profile


REPORT_TYPE = "datumor.generated_dataset"
REPORT_VERSION = "1.0.0"


def _get_text(value: Any) -> str | None:
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


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _identity(dukr: dict) -> dict:
    source = dukr.get("source", {})
    return {
        "source_id": source.get("source_id"),
        "project_id": source.get("project_id"),
        "filename": source.get("filename"),
        "checksum_sha256": source.get("checksum_sha256"),
    }


def _provenance(dukr: dict, item: dict | None, evidence: str) -> dict:
    item = item or {}

    result = {
        **_identity(dukr),
        "evidence_text": evidence,
    }

    for key in (
        "start_offset", "end_offset", "start_line", "end_line",
        "page_number", "page", "record_index", "segment_id",
        "context_id", "evidence_id",
    ):
        if key in item:
            result[key] = item[key]

    if item.get("source_id"):
        result["source_id"] = item["source_id"]

    if item.get("checksum_sha256"):
        result["checksum_sha256"] = item["checksum_sha256"]

    return result


def _stable_id(profile_id: str, source_id: Any, evidence: str, task: str) -> str:
    payload = json.dumps(
        [profile_id, source_id, evidence, task],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _iter_items(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _semantic_items(dukr: dict):
    semantics = dukr.get("semantics", {})
    if not isinstance(semantics, dict):
        return

    for category in ("facts", "claims"):
        for item in _iter_items(semantics.get(category)):
            evidence = _get_text(item.get("evidence")) or _get_text(item)
            if evidence:
                yield category, item, evidence


def _context_items(dukr: dict):
    context = dukr.get("context", {})
    if not isinstance(context, dict):
        return

    for item in _iter_items(context.get("context_units")):
        evidence = _get_text(item.get("text")) or _get_text(item.get("content"))
        if evidence:
            yield item, evidence


def _explicit_records(dukr: dict):
    source = dukr.get("source", {})
    records = source.get("source_records", []) if isinstance(source, dict) else []

    for index, record in enumerate(_iter_items(records)):
        instruction = _string(record.get("instruction") or record.get("prompt"))
        response = _string(record.get("response") or record.get("answer"))
        if instruction and response:
            yield index, record, instruction, response


def _make_example(
    dukr: dict,
    profile: dict,
    task: str,
    instruction: str,
    response: str,
    evidence: str,
    item: dict | None = None,
    extra: dict | None = None,
) -> dict:
    source = _identity(dukr)
    example = {
        "example_id": _stable_id(
            profile["profile_id"],
            source.get("source_id"),
            evidence,
            task,
        ),
        "task_type": task,
        "instruction": instruction,
        "response": response,
        "provenance": _provenance(dukr, item, evidence),
    }

    if extra:
        example.update(extra)

    return example


def _generate_general(dukr: dict, profile: dict):
    examples = []
    skipped = []

    for index, record, instruction, response in _explicit_records(dukr):
        evidence = _get_text(record.get("evidence")) or response
        examples.append(_make_example(
            dukr, profile, "explicit_instruction_response",
            instruction, response, evidence, record,
            {"record_index": index},
        ))

    if examples:
        return examples, skipped

    for category, item, evidence in _semantic_items(dukr):
        examples.append(_make_example(
            dukr,
            profile,
            category,
            "Answer using only the supplied source evidence. What does the source state?",
            evidence,
            evidence,
            item,
        ))

    if not examples:
        skipped.append({
            "reason": "No explicit instruction/response records or evidence-backed facts/claims were available."
        })

    return examples, skipped


def _generate_coding(dukr: dict, profile: dict):
    examples = []
    skipped = []

    for index, record, instruction, response in _explicit_records(dukr):
        evidence = _get_text(record.get("evidence")) or response
        examples.append(_make_example(
            dukr, profile, "explicit_coding_instruction_response",
            instruction, response, evidence, record,
            {"record_index": index},
        ))

    if not examples:
        skipped.append({
            "reason": (
                "No explicit coding instruction/response pairs were found. "
                "DATUMOR does not invent code solutions or infer expected outputs."
            )
        })

    return examples, skipped


def _generate_research(dukr: dict, profile: dict):
    examples = []
    skipped = []

    for category, item, evidence in _semantic_items(dukr):
        subject = _string(item.get("subject"))
        predicate = _string(item.get("predicate"))
        obj = _string(item.get("object"))

        if subject and predicate and obj:
            question = f"What does the source state about {subject} and {obj}?"
        elif subject:
            question = f"What does the source state about {subject}?"
        else:
            question = "What does the source state?"

        examples.append(_make_example(
            dukr,
            profile,
            category,
            question,
            evidence,
            evidence,
            item,
            {
                "evidence": evidence,
                "question": question,
                "answer": evidence,
            },
        ))

    if not examples:
        skipped.append({
            "reason": "No evidence-backed facts or claims were available for research examples."
        })

    return examples, skipped
def _generate_retrieval(dukr: dict, profile: dict):
    examples = []
    skipped = []

    entities = [
        entity for entity in _iter_items(dukr.get("entities", []))
        if _string(entity.get("normalized_value"))
        or _string(entity.get("value"))
    ]

    for context_item, evidence in _context_items(dukr):
        matching_entities = []

        for entity in entities:
            value = _string(entity.get("normalized_value")) or _string(entity.get("value"))
            if value and value.casefold() in evidence.casefold():
                matching_entities.append(value)

        if not matching_entities:
            continue

        query_entity = matching_entities[0]
        query = f"What does the source say about {query_entity}?"

        examples.append(_make_example(
            dukr,
            profile,
            "retrieval_pair",
            query,
            evidence,
            evidence,
            context_item,
            {
                "query": query,
                "positive": evidence,
            },
        ))

    if not examples:
        skipped.append({
            "reason": (
                "No context units containing identifiable source-grounded entities "
                "were available for retrieval pairs."
            )
        })

    return examples, skipped


_GENERATORS = {
    "general_llm": _generate_general,
    "coding": _generate_coding,
    "research": _generate_research,
    "retrieval": _generate_retrieval,
}


def generate_dataset(dukr_documents: list[dict], profile: dict) -> dict:
    """Generate deterministic, source-grounded examples for one profile."""

    if not isinstance(dukr_documents, list) or not dukr_documents:
        raise ValueError("dukr_documents must be a non-empty list")

    if not isinstance(profile, dict):
        raise TypeError("profile must be a dictionary")

    validation = validate_profile(profile)
    if not validation["valid"]:
        raise ValueError("Invalid profile: " + "; ".join(validation["errors"]))

    profile_id = profile["profile_id"]
    generator = _GENERATORS.get(profile_id)

    if generator is None:
        raise ValueError(f"Unsupported generation profile: {profile_id}")

    snapshots = [
        json.dumps(document, sort_keys=True, ensure_ascii=False)
        for document in dukr_documents
    ]

    examples = []
    skipped = []
    seen = set()
    document_results = []

    for document_index, dukr in enumerate(dukr_documents):
        if not isinstance(dukr, dict):
            raise TypeError("Every DUKR document must be a dictionary")

        source = dukr.get("source")
        if not isinstance(source, dict):
            raise ValueError(f"DUKR document {document_index} has no source object")

        generated, document_skipped = generator(dukr, profile)
        accepted = 0

        for example in generated:
            fingerprint = sha256(
                json.dumps(
                    {
                        key: value
                        for key, value in example.items()
                        if key != "example_id"
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()

            if fingerprint in seen:
                skipped.append({
                    "source_id": source.get("source_id"),
                    "reason": "Duplicate generated example removed.",
                })
                continue

            seen.add(fingerprint)
            examples.append(example)
            accepted += 1

        for item in document_skipped:
            skipped.append({
                "source_id": source.get("source_id"),
                **item,
            })

        document_results.append({
            "source": _identity(dukr),
            "examples_generated": accepted,
        })

    if snapshots != [
        json.dumps(document, sort_keys=True, ensure_ascii=False)
        for document in dukr_documents
    ]:
        raise RuntimeError("Dataset generation modified an input DUKR document")

    required_fields = profile["required_fields"]
    for index, example in enumerate(examples):
        missing = [
            field for field in required_fields
            if field not in example or example[field] is None
        ]
        if missing:
            raise RuntimeError(
                f"Generated example {index} is missing required fields: {missing}"
            )

    return {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "profile": {
            "profile_id": profile_id,
            "profile_version": profile["version"],
            "task_type": profile["task_type"],
            "output_format": profile["output_format"],
            "quality_threshold": profile["quality_threshold"],
        },
        "summary": {
            "documents_assessed": len(dukr_documents),
            "examples_generated": len(examples),
            "examples_skipped": len(skipped),
            "unique_examples": len(examples),
        },
        "documents": document_results,
        "examples": examples,
        "skipped": skipped,
        "automatic_source_changes": False,
    }
