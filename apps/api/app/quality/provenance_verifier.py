from __future__ import annotations

import hashlib
import json


def _pick(obj, *keys):
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if value is not None:
                return value
    return None


def _source(dukr):
    return dukr.get("source", {}) if isinstance(dukr.get("source"), dict) else {}


def _content(dukr):
    source = _source(dukr)
    return (
        source.get("original_content")
        or dukr.get("original_content")
        or (dukr.get("document") or {}).get("original_content")
    )


def _source_id(dukr):
    return _pick(_source(dukr), "source_id", "id")


def _stable_id(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _add(findings, category, status, message, source_id=None,
         element_id=None, evidence=None):
    payload = {
        "category": category,
        "status": status,
        "message": message,
        "source_id": source_id,
        "element_id": element_id,
        "evidence": evidence,
    }
    findings.append({"finding_id": _stable_id(payload), **payload})


def _verify_source(dukr, findings):
    source = _source(dukr)
    source_id = _source_id(dukr)
    content = _content(dukr)

    if source_id:
        _add(findings, "source_identity", "verified",
             "Source identity is present.", source_id)
    else:
        _add(findings, "source_identity", "unverifiable",
             "Source identity is missing from the canonical DUKR source.",
             None)

    if not isinstance(content, str):
        _add(findings, "source_content", "unverifiable",
             "Original source content is unavailable.", source_id)
        return

    recorded_checksum = _pick(source, "checksum_sha256", "sha256")
    if recorded_checksum:
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        status = (
            "verified"
            if actual.lower() == str(recorded_checksum).lower()
            else "failed"
        )
        _add(findings, "source_checksum", status,
             "Source checksum matches original content."
             if status == "verified"
             else "Source checksum does not match original content.",
             source_id, evidence={"expected": recorded_checksum,
                                  "actual": actual})
    else:
        _add(findings, "source_checksum", "unverifiable",
             "Original source checksum is missing.", source_id)

    content_hash = _pick(source, "content_sha256")

    # Legacy fixtures use checksum_sha256 as their content hash.
    if not content_hash:
        content_hash = source.get("checksum_sha256")

    if content_hash:
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        status = (
            "verified"
            if actual.lower() == str(content_hash).lower()
            else "failed"
        )
        _add(
            findings,
            "source_content_hash",
            status,
            "DUKR content hash matches original content."
            if status == "verified"
            else "DUKR content hash does not match original content.",
            source_id,
            evidence={"expected": content_hash, "actual": actual},
        )
    else:
        _add(
            findings,
            "source_content_hash",
            "unverifiable",
            "DUKR content hash is missing.",
            source_id,
        )


def _verify_element(element, content, source_id, category, findings):
    if not isinstance(element, dict):
        _add(findings, category, "unverifiable",
             "Knowledge element is not a structured object.", source_id)
        return

    element_id = _pick(
        element, "entity_id", "relationship_id", "statement_id",
        "claim_id", "fact_id", "context_unit_id", "id"
    )

    provenance = element.get("provenance", {})
    if isinstance(provenance, dict):
        referenced = _pick(provenance, "source_id")
        if isinstance(referenced, dict):
            referenced = _pick(referenced, "source_id", "id")
        if referenced and source_id and referenced != source_id:
            _add(findings, category, "failed",
                 "Element references a different source identity.",
                 source_id, element_id,
                 {"referenced_source_id": referenced})
            return

    evidence = _pick(element, "evidence_text", "text")
    evidence_obj = element.get("evidence")
    if isinstance(evidence_obj, dict):
        evidence = evidence or _pick(evidence_obj, "text", "evidence_text")
    elif isinstance(evidence_obj, str):
        evidence = evidence or evidence_obj

    start = _pick(element, "start_offset", "character_start")
    end = _pick(element, "end_offset", "character_end")

    if not isinstance(content, str):
        _add(findings, category, "unverifiable",
             "Original content is unavailable.", source_id, element_id)
        return

    if not isinstance(evidence, str) or not evidence:
        _add(findings, category, "unverifiable",
             "Evidence text is missing.", source_id, element_id)
        return

    if not isinstance(start, int) or not isinstance(end, int):
        _add(findings, category, "unverifiable",
             "Evidence offsets are missing or invalid.",
             source_id, element_id, {"evidence_text": evidence})
        return

    if start < 0 or end < start or end > len(content):
        _add(findings, category, "failed",
             "Evidence offsets fall outside original content.",
             source_id, element_id, {"start": start, "end": end})
        return

    actual = content[start:end]
    if actual != evidence:
        _add(findings, category, "failed",
             "Evidence text does not match original content at its offsets.",
             source_id, element_id,
             {"expected": evidence, "actual": actual,
              "start": start, "end": end})
        return

    _add(findings, category, "verified",
         "Evidence matches original content at recorded offsets.",
         source_id, element_id, {"start": start, "end": end})


def _list(value):
    return value if isinstance(value, list) else []


def verify_provenance(dukr_documents: list[dict]) -> dict:
    if not isinstance(dukr_documents, list):
        raise TypeError("dukr_documents must be a list")

    findings = []

    for dukr in dukr_documents:
        if not isinstance(dukr, dict):
            _add(findings, "document", "failed",
                 "DUKR document must be an object.")
            continue

        source_id = _source_id(dukr)
        content = _content(dukr)
        _verify_source(dukr, findings)

        for item in _list(dukr.get("entities")):
            _verify_element(item, content, source_id,
                            "entity_evidence", findings)

        for item in _list(dukr.get("relationships")):
            _verify_element(item, content, source_id,
                            "relationship_evidence", findings)

        semantics = dukr.get("semantics", {})
        if not isinstance(semantics, dict):
            semantics = {}

        statements = (
            _list(semantics.get("statements"))
            + _list(semantics.get("facts"))
            + _list(semantics.get("claims"))
            + _list(dukr.get("facts"))
            + _list(dukr.get("claims"))
        )
        seen = set()
        for item in statements:
            marker = id(item)
            if marker not in seen:
                seen.add(marker)
                _verify_element(item, content, source_id,
                                "semantic_evidence", findings)

        context = dukr.get("context", {})
        units = _list(context.get("context_units")) if isinstance(context, dict) else []
        for unit in units:
            _verify_element(unit, content, source_id,
                            "context_evidence", findings)

    counts = {
        status: sum(1 for f in findings if f["status"] == status)
        for status in ("verified", "failed", "unverifiable")
    }

    return {
        "report_type": "datumor.provenance_verification",
        "version": "1.0.0",
        "status": (
            "failed" if counts["failed"]
            else "incomplete" if counts["unverifiable"]
            else "verified"
        ),
        "summary": {
            "documents_assessed": len(dukr_documents),
            "total_findings": len(findings),
            **counts,
        },
        "findings": findings,
        "automatic_changes_made": False,
    }
