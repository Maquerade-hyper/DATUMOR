# M5.2 ? Data Normalization

## Purpose

Create normalized derived data from DUKR while retaining the original canonical representation unchanged.

## Public function

`normalize_dukr(dukr, profile)`

## Supported normalization modes

- `none`: preserve text exactly.
- `conservative`: Unicode NFC, LF line endings, trailing line-whitespace removal.
- `standard`: conservative rules plus horizontal whitespace collapse and limiting repeated blank lines.

Code-sensitive fields such as `code`, `source_code`, `snippet`, `program`, `script`, `query`, `sql`, and `command` are protected from horizontal whitespace collapsing.

## Output

- Profile identity and version.
- Source identity and original source checksums.
- Normalized content and source records.
- Original and normalized content hashes and lengths.
- Per-field change log with before/after hashes and operation names.
- Summary and warnings.

## Integrity

The normalizer never edits the input DUKR. Entity, semantic, relationship, context evidence, and provenance offsets remain untouched in the source artifact. Normalized output is a derived representation; original evidence offsets refer to original content.

## Scope boundary

This step does not generate instruction datasets, retrieval pairs, embeddings, or serialized training exports. Those belong to later M5 steps.
