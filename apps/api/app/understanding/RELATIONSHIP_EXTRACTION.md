# M3.3 ? Relationship Extraction

## Purpose
Extract directional, evidence-grounded relationships between M3.1 entities
using M2 source text.

## Public interface
`extract_relationships(extraction_result, entity_result=None)`

When `entity_result` is omitted, the M3.1 entity extractor is called.

## Relationship representation
Each relationship contains:
- Stable relationship ID
- Subject entity and ID
- Predicate
- Object entity and ID
- Subject-predicate-object triple
- Direction
- Confidence and extraction method
- Original sentence and character offsets
- Source provenance

## Detection policy
Only explicit connector patterns between two source-grounded entity spans
are accepted. Co-occurrence alone is not a relationship.

Forward patterns include:
- works with
- develops
- uses
- built with
- located in
- based in
- depends on
- supports
- integrates with
- scheduled for

Reverse constructions include:
- developed by
- created by
- founded by
- written by
- maintained by
- owned by

Reverse constructions normalize the actor into the subject position.

## Limitations
This is a deterministic relationship baseline, not open-domain relation
extraction. Connectors are finite and language-dependent. Entity spans must
have valid offsets in the original M2 content. Implicit, cross-sentence,
coreference-dependent and domain-specific relationships are not inferred.

## Testing
`python -m pytest tests/unit/test_relationship_extraction.py -q`
