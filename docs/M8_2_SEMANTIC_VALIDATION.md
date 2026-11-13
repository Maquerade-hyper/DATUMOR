# M8.2 — Semantic Validation

## Purpose

Verify that canonical DUKR semantic records and generated dataset examples
remain traceable to their original source evidence.

## Module

`apps/api/app/validation/semantic_validation.py`

## Public entry points

- `validate_dukr_semantics(dukr)`
- `validate_dataset_semantics(dataset, dukr_documents)`

## DUKR checks

- Entity evidence against original source content.
- Fact and claim evidence against original source content.
- Evidence offsets and exact source slices.
- Semantic item entity references.
- Relationship subject/object entity references.
- Context entity and relationship references.
- Context text grounding.

## Dataset checks

- Example provenance and source identity.
- Matching input DUKR source.
- Evidence text existence in the declared source.
- Evidence offset integrity when offsets are supplied.

## Finding format

Every finding includes a machine-readable code, JSON path, message, and
severity. Evidence details are included when relevant.

Missing evidence or unavailable source content produces a warning.
Demonstrably ungrounded evidence and unresolved references produce errors.

## Safety and scope

- Inputs are not modified.
- No LLM-based truth inference is performed.
- No semantic content is generated or rewritten.
- This validator checks evidence traceability, not whether a source itself
  is factually correct.
- Contradiction detection remains a separate M4 quality-analysis concern.
