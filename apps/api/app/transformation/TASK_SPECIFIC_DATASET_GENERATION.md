# M5.3 ? Task-Specific Dataset Generation

## Purpose

Generate profile-specific training examples from DUKR using source-grounded evidence.

## Public function

`generate_dataset(dukr_documents, profile)`

## Supported profiles

- `general_llm`: explicit instruction/response records, or evidence-backed facts and claims.
- `coding`: explicit coding instruction/response records only.
- `research`: evidence-backed facts and claims with provenance.
- `retrieval`: context units containing identifiable entities.

## Evidence and provenance

Every generated example includes a stable ID and provenance containing source identity, checksum, exact evidence text, and available offsets/page/line/record references.

## Duplicate handling

Duplicate examples are removed deterministically within a generated dataset. Skipped records are reported with reasons.

## Safety

- No invented code solutions or expected outputs.
- No unsupported answers are generated to fill a dataset.
- Missing evidence results in a skipped example.
- Original DUKR documents are never modified.
- Generation is deterministic for the same inputs and profile, excluding report timestamps.

## Scope boundary

This step generates structured in-memory examples. Dataset serialization belongs to M5.4. Transformation reporting enhancements belong to M5.5.
