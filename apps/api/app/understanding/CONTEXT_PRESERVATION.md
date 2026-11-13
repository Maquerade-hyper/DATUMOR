# M3.4 ? Context Preservation

## Purpose
Preserve source text, document structure, sentence order, context links,
upstream knowledge references and source provenance.

## Public interface
`preserve_context(extraction_result, entity_result=None,
semantic_result=None, relationship_result=None)`

## Output
- `source`: source identity and checksum.
- `document`: original content, content hash, metadata and warnings.
- `context_units`: ordered paragraph units with exact source offsets.
- `sentences`: sentence-like units within each paragraph.
- `entity_links`: source-grounded entity references.
- `relationship_links`: relationship references.
- `fact_links` and `claim_links`: semantic statement references.
- `source_records`: original upstream extraction records.
- `summary`: structural and link counts.

## Lossless preservation
Paragraph units partition the complete original content. Paragraph
separators remain attached to their preceding unit. Concatenating every
context unit's `text` must reproduce the original M2 `content` exactly.

Offsets are zero-based Python string character offsets, with an exclusive
end offset. They refer to the original M2 content string.

## Provenance
Source identifiers, project identifiers, checksums, filenames, paths,
metadata and original extraction records are retained when supplied.
Page, line, record and segment references are carried from entity evidence.

## Limitations
Sentence splitting uses punctuation heuristics. Abbreviations, quoted
punctuation, multilingual segmentation and layout-specific boundaries
may require specialized handling. The original content remains authoritative.
Context links require valid upstream evidence offsets; no missing references
are fabricated.

## Testing
`python -m pytest tests/unit/test_context_preservation.py -q`
