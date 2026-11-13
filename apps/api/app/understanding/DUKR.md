# M3.5 ? DUKR Generation

## Definition
DUKR (DATUMOR Universal Knowledge Representation) is the canonical,
model-independent knowledge representation produced from M2 extraction
and M3 understanding artifacts.

## Public interface
- `generate_dukr(extraction_result, entity_result, semantic_result,
  relationship_result, context_result)`
- `validate_dukr(dukr)`

## Top-level structure
- `dukr_schema`, `dukr_schema_version`, `representation_id`
- `source`: original content, hash, identity, metadata and extraction records
- `entities`: canonical entity records with evidence and provenance
- `semantics`: overview, topics, classifications, intents, facts and claims
- `relationships`: directed subject-predicate-object relations
- `context`: lossless M3.4 context units and their references
- `knowledge_graph`: entity/statement nodes and relationship edges
- `upstream_artifacts`: original M3 input artifacts retained for traceability
- `validation`: structural integrity and reference checks

## Evidence and epistemic status
Evidence offsets are zero-based Python string character offsets with an
exclusive end. Original evidence objects and upstream artifacts are retained.
Observed facts and claims remain distinct from inferred semantic summaries.
DUKR does not independently verify assertions found in source documents.

## Determinism
The representation identifier is based on the source content SHA-256.
Fallback artifact identifiers are deterministic from source identity,
position and evidence. Existing upstream identifiers are preserved.

## Validation
Checks include unique graph node identifiers, relationship endpoint
resolution, context entity/relationship references, lossless reconstruction
of original content, and content checksum integrity.

A missing ingestion source ID or checksum is a warning, not an invented value.

## Testing
`python -m pytest tests/unit/test_dukr_generation.py -q`
