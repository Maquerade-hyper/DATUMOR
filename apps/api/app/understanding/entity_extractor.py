import hashlib
import re


ENTITY_SCHEMA_VERSION = "1.0"

PATTERNS = {
    "email": re.compile(
        r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
        re.IGNORECASE,
    ),
    "url": re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE),
    "ipv4": re.compile(
        r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])"
    ),
    "date": re.compile(
        r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
        r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
        r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:,\s*\d{4})?)\b",
        re.IGNORECASE,
    ),
    "phone": re.compile(
        r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?"
        r"(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\w)"
    ),
}

TECHNOLOGIES = {
    "python", "javascript", "typescript", "java", "c", "c++", "c#",
    "go", "golang", "rust", "php", "ruby", "kotlin", "swift",
    "react", "next.js", "node.js", "fastapi", "django", "flask",
    "pytorch", "tensorflow", "ollama", "qwen", "hugging face",
    "transformers", "tree-sitter", "postgresql", "postgres",
    "mysql", "redis", "mongodb", "sqlite", "qdrant",
    "docker", "kubernetes", "git", "github", "linux",
    "windows", "html", "css", "tailwind", "vite",
    "pandas", "polars", "numpy", "opencv",
    "celery", "fastapi", "rest api", "graphql",
}

LOCATIONS = {
    "india", "united states", "usa", "united kingdom", "uk",
    "canada", "australia", "germany", "france", "japan",
    "china", "brazil", "russia", "new york", "london",
    "paris", "tokyo", "delhi", "new delhi", "mumbai",
    "bengaluru", "bangalore", "hyderabad", "chennai",
    "kolkata", "bhagalpur", "bihar", "jharkhand",
}

ORG_SUFFIXES = (
    " inc", " incorporated", " llc", " ltd", " limited",
    " corporation", " corp", " university", " institute",
    " foundation", " company", " technologies", " systems",
    " labs", " laboratory", " department", " organization",
)

ORGANIZATION_NAMES = {
    "openai", "google", "microsoft", "apple", "amazon",
    "meta", "nvidia", "anthropic", "deepmind", "ibm",
    "oracle", "adobe", "samsung", " tesla",
}

PERSON_CONTEXT = re.compile(
    r"\b(?:by|author|written by|created by|founded by|"
    r"developed by|maintained by)\s+"
    r"([A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?"
    r"(?:\s+[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?){0,3})"
)

PROPER_PHRASE = re.compile(
    r"\b[A-Z][a-zA-Z0-9&'+-]*"
    r"(?:\s+[A-Z][a-zA-Z0-9&'+-]*){1,4}\b"
)

CONCEPT_TERMS = {
    "machine learning", "deep learning", "artificial intelligence",
    "data intelligence", "entity extraction", "semantic understanding",
    "knowledge graph", "natural language processing",
    "large language model", "retrieval augmented generation",
    "data quality", "data lineage", "fine tuning",
}

CODE_RECORD_TYPES = {"declaration", "import"}


def _normalize(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _stable_id(
    checksum: str,
    entity_type: str,
    normalized: str,
    start: int,
    end: int,
) -> str:
    material = (
        f"{checksum}|{entity_type}|{normalized}|{start}|{end}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _extract_segments(result: dict) -> list[dict]:
    """Select source-grounded text segments without duplicating content."""
    content = result.get("content")
    records = result.get("records") or []

    if isinstance(content, str) and content:
        if result.get("format") == "pdf":
            page_records = [
                record for record in records
                if isinstance(record, dict)
                and record.get("record_type") == "page"
                and isinstance(record.get("text"), str)
            ]
            if page_records:
                return [
                    {
                        "text": record["text"],
                        "page_number": record.get("page_number"),
                        "record_number": None,
                        "segment_type": "page",
                    }
                    for record in page_records
                ]

        return [{
            "text": content,
            "page_number": None,
            "record_number": None,
            "segment_type": "content",
        }]

    if isinstance(content, (dict, list)):
        text = str(content)
        return [{
            "text": text,
            "page_number": None,
            "record_number": None,
            "segment_type": "structured_content",
        }]

    segments = []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            continue
        value = (
            record.get("text")
            or record.get("source_code")
            or record.get("value")
        )
        if isinstance(value, (dict, list)):
            value = str(value)
        if isinstance(value, str) and value:
            segments.append({
                "text": value,
                "page_number": record.get("page_number"),
                "record_number": record.get("record_number", index),
                "segment_type": record.get("record_type", "record"),
            })
    return segments


def extract_entities(
    extraction_result: dict,
    *,
    source_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Extract evidence-backed entities from a DATUMOR extraction result."""
    if not isinstance(extraction_result, dict):
        raise TypeError("extraction_result must be a dictionary")

    metadata = extraction_result.get("metadata") or {}
    source_metadata = metadata.get("source") or {}
    source_identity = metadata.get("source_identity") or {}

    checksum = (
        source_metadata.get("checksum_sha256")
        or extraction_result.get("checksum_sha256")
        or ""
    )
    filename = (
        extraction_result.get("source_filename")
        or source_metadata.get("filename")
    )
    resolved_source_id = (
        source_id
        or source_identity.get("source_id")
        or extraction_result.get("source_id")
    )
    resolved_project_id = (
        project_id
        or source_identity.get("project_id")
        or extraction_result.get("project_id")
    )

    segments = _extract_segments(extraction_result)
    entities = []
    seen = set()

    def add_entity(
        entity_type: str,
        value: str,
        text: str,
        start: int,
        end: int,
        confidence: float,
        method: str,
        segment: dict,
    ) -> None:
        value = value.strip()
        if not value or start < 0 or end <= start:
            return

        normalized = _normalize(value)
        key = (
            entity_type, normalized, segment.get("page_number"),
            start, end,
        )
        if key in seen:
            return
        seen.add(key)

        evidence = text[max(0, start - 80):min(len(text), end + 80)]
        entity = {
            "entity_id": _stable_id(
                checksum, entity_type, normalized, start, end
            ),
            "entity_type": entity_type,
            "value": value,
            "normalized_value": normalized,
            "confidence": confidence,
            "extraction_method": method,
            "evidence": {
                "text": evidence,
                "matched_text": text[start:end],
                "start_offset": start,
                "end_offset": end,
                "start_line": _line_number(text, start),
                "end_line": _line_number(text, max(start, end - 1)),
                "page_number": segment.get("page_number"),
                "record_number": segment.get("record_number"),
                "segment_type": segment.get("segment_type"),
            },
            "source": {
                "source_id": resolved_source_id,
                "project_id": resolved_project_id,
                "filename": filename,
                "path": source_metadata.get("path"),
                "checksum_sha256": checksum or None,
            },
        }
        entities.append(entity)

    for segment in segments:
        text = segment["text"]

        for entity_type, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                value = match.group(0).rstrip(".,;:)")
                end = match.start() + len(value)
                add_entity(
                    entity_type, value, text, match.start(), end,
                    0.99, "regex", segment,
                )

        for technology in sorted(TECHNOLOGIES, key=len, reverse=True):
            pattern = re.compile(
                r"(?<![\w])" + re.escape(technology) + r"(?![\w])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                add_entity(
                    "technology", match.group(0), text,
                    match.start(), match.end(), 0.98,
                    "technology_lexicon", segment,
                )

        for concept in sorted(CONCEPT_TERMS, key=len, reverse=True):
            pattern = re.compile(re.escape(concept), re.IGNORECASE)
            for match in pattern.finditer(text):
                add_entity(
                    "concept", match.group(0), text,
                    match.start(), match.end(), 0.97,
                    "concept_lexicon", segment,
                )

        for location in sorted(LOCATIONS, key=len, reverse=True):
            pattern = re.compile(
                r"(?<![\w])" + re.escape(location) + r"(?![\w])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                add_entity(
                    "location", match.group(0), text,
                    match.start(), match.end(), 0.96,
                    "location_lexicon", segment,
                )

        for match in PERSON_CONTEXT.finditer(text):
            value = match.group(1)
            start = match.start(1)
            add_entity(
                "person", value, text, start, match.end(1),
                0.78, "person_context_pattern", segment,
            )

        # Recognize common standalone organization names.
        for organization in sorted(ORGANIZATION_NAMES, key=len, reverse=True):
            organization = organization.strip()
            pattern = re.compile(
                r"(?<![\\w])" + re.escape(organization) + r"(?![\\w])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                following = text[match.end():].lstrip()
                next_word = re.match(r"[A-Za-z]+", following)
                if next_word and next_word.group(0).casefold() in {
                    suffix.strip() for suffix in ORG_SUFFIXES
                }:
                    continue

                add_entity(
                    "organization",
                    match.group(0),
                    text,
                    match.start(),
                    match.end(),
                    0.90,
                    "organization_name_lexicon",
                    segment,
                )

        for match in PROPER_PHRASE.finditer(text):
            value = match.group(0)
            normalized = _normalize(value)
            if normalized in TECHNOLOGIES or normalized in CONCEPT_TERMS:
                continue
            if normalized in LOCATIONS:
                continue

            entity_type = None
            lowered = normalized
            if any(lowered.endswith(suffix) for suffix in ORG_SUFFIXES):
                entity_type = "organization"

            if entity_type:
                add_entity(
                    entity_type, value, text, match.start(), match.end(),
                    0.80, "proper_name_pattern", segment,
                )

    # Code declarations and imports are authoritative parser outputs.
    for record in extraction_result.get("records") or []:
        if not isinstance(record, dict):
            continue
        if record.get("record_type") not in CODE_RECORD_TYPES:
            continue

        value = record.get("name") or record.get("source_code")
        if not isinstance(value, str) or not value.strip():
            continue

        declaration_type = record.get("declaration_type")
        entity_type = (
            "code_symbol" if declaration_type
            else "code_import"
        )
        line = record.get("start_line")
        source_code = record.get("source_code", value)

        material = f"{checksum}|{entity_type}|{_normalize(value)}|{line}"
        entity_id = hashlib.sha256(material.encode("utf-8")).hexdigest()

        entities.append({
            "entity_id": entity_id,
            "entity_type": entity_type,
            "value": value,
            "normalized_value": _normalize(value),
            "confidence": 1.0,
            "extraction_method": "tree_sitter_record",
            "evidence": {
                "text": source_code,
                "matched_text": value,
                "start_offset": None,
                "end_offset": None,
                "start_line": line,
                "end_line": record.get("end_line"),
                "page_number": None,
                "record_number": None,
                "segment_type": "code_record",
            },
            "source": {
                "source_id": resolved_source_id,
                "project_id": resolved_project_id,
                "filename": filename,
                "path": record.get("file_path") or source_metadata.get("path"),
                "checksum_sha256": checksum or None,
            },
        })

    entities.sort(
        key=lambda item: (
            item["evidence"].get("page_number") or 0,
            item["evidence"].get("start_line") or 0,
            item["entity_type"],
            item["normalized_value"],
        )
    )

    counts = {}
    for entity in entities:
        kind = entity["entity_type"]
        counts[kind] = counts.get(kind, 0) + 1

    return {
        "entity_schema_version": ENTITY_SCHEMA_VERSION,
        "source": {
            "source_id": resolved_source_id,
            "project_id": resolved_project_id,
            "filename": filename,
            "path": source_metadata.get("path"),
            "checksum_sha256": checksum or None,
        },
        "summary": {
            "entity_count": len(entities),
            "entity_type_counts": counts,
            "segment_count": len(segments),
        },
        "entities": entities,
        "warnings": [
            "Rule-based entity extraction is not full semantic NER.",
            "Person and organization detections are heuristic and require validation.",
        ],
    }
