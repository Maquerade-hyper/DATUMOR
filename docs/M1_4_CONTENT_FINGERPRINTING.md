# DATUMOR M1.4 â€” Content Fingerprinting and Duplicate Detection

Exact file identity uses SHA-256 of raw bytes. GitHub repository identity uses
SHA-256 of a canonical JSON manifest of normalized relative paths, file SHA-256
hashes and file sizes. Fingerprints are scoped by source type.

A PostgreSQL `fingerprint_claims` table identifies one canonical source per
(source_type, checksum_sha256). Transaction-scoped advisory locks serialize
simultaneous claims; existing historical duplicate source rows are preserved.
Startup backfills claims to the oldest historical source without deleting data.

Ingestion responses preserve the existing `data` and `source` fields and add
`duplicate` and `canonical_source_id`. For duplicates, redundant staged content
is removed. The canonical source remains accessible through existing routes.

The system detects exact content duplicates only; semantic or near-duplicate
content analysis belongs to later quality milestones. M1.5 will move canonical
staged objects into permanent S3-compatible storage.
