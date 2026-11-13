# M3.2 ? Semantic Understanding

## Purpose
Convert M2 extraction output and M3.1 entities into deterministic,
traceable semantic annotations.

## Public interface

`understand_semantics(extraction_result, entity_result=None)`

If no entity result is supplied, the function calls the M3.1 entity extractor.

## Output
- `source`: source identity and checksum where available.
- `overview`: inferred high-level interpretation.
- `subjects`: observed entity values.
- `topics`: domain topic candidates and lexical evidence.
- `classifications`: content type labels.
- `intents`: sentence-level intent signals.
- `facts`: source-observed statements with exact offsets.
- `claims`: source assertions with evidence.
- `summary`: consistent output counts.
- `warnings`: known limitations.

## Epistemic rules
- `observed` means the statement was present in extracted source text.
- `inferred` means a deterministic interpretation derived from source signals.
- Neither status independently proves that a source statement is true.
- Evidence offsets refer to the M2 `content` string.
- Page-level evidence is not fabricated; unavailable page numbers remain null.

## Limitations
This milestone uses deterministic lexical rules, not a foundation model.
Domain vocabulary and intent patterns are finite. It does not establish
causality, resolve contradictions, or independently fact-check source claims.
Low-confidence or ambiguous interpretations must remain marked as heuristic.

## Testing
Run:
`python -m pytest tests/unit/test_semantic_understanding.py -q`
