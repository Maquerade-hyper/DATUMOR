# M4.2 ? Duplicate Detection

## Purpose
Identify exact, normalized and near-duplicate DUKR source documents
without modifying, deleting or merging original data.

## Public interface
`detect_duplicates(dukr_documents, near_duplicate_threshold=0.90)`

## Detection methods

1. Exact: SHA-256 of original UTF-8 content.
2. Normalized: Unicode NFKC, case-folding, punctuation normalization
   and whitespace normalization.
3. Near duplicate: `difflib.SequenceMatcher` ratio over normalized text.
   Default threshold is 0.90 and can be configured per invocation.

Exact and normalized matches receive similarity 1.0. Near-duplicate
matches are marked for review.

## Cross-source behavior
Documents with different source IDs are compared. Each result records
source ID, project ID, filename, path, ingestion checksum and computed
content checksum where available. Same-source representations are skipped.

## Grouping
Connected duplicate pairs are grouped using deterministic group identifiers.
Groups identify candidate relationships only; they do not represent
automatic deduplication or data consolidation.

## Safety and limits
- No source content is modified.
- No records are deleted or merged.
- Maximum 500 DUKR documents per invocation.
- Maximum 2,000,000 characters per document.
- Near-duplicate matching is character-sequence similarity, not semantic
  equivalence. Review candidates before taking action.

## Output
A report includes summary counts, pair-level matches, detection method,
similarity, source references, cross-source flag, review requirement,
duplicate group IDs and warnings.

## Testing
`python -m pytest tests/unit/test_duplicate_detection.py -q`
