# DATUMOR Entity Extraction ? M3.1

M3.1 extracts evidence-backed entities from existing DATUMOR extraction
results. It is deterministic and does not require an external model.

## Entity types

- Email addresses, URLs, IPv4 addresses, dates and phone-like values
- Technologies and concepts from maintained vocabularies
- Locations from a maintained location vocabulary
- Contextual person names and organization names using explicit patterns
- Code symbols and imports from Tree-sitter extraction records

## Output

`extract_entities(extraction_result, source_id=None, project_id=None)`

Returns an entity schema version, source identity, entity counts, and entity
records. Each entity includes a stable SHA-256 identifier, type, original and
normalized values, confidence, extraction method, evidence offsets, line/page
references where available, and source provenance.

## Evidence and confidence

Regex and exact vocabulary matches are evidence-grounded. Person and
organization detection is heuristic and carries lower confidence. The engine
does not claim that heuristic proper-name detection is authoritative.

## Limitations

This is a deterministic baseline, not a complete multilingual named-entity
recognition model. Vocabulary coverage is finite. Phone patterns may match
some non-phone numeric sequences and should be validated for the target data.
Semantic entity disambiguation and cross-document entity resolution are not
performed in M3.1.
