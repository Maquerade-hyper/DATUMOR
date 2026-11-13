# M8.1 — Schema Validation

## Scope

Central validation entry points for DATUMOR's eight existing Draft 2020-12
contract schemas, canonical DUKR documents, multimodal records, generated
M5 datasets, and serialized JSON, JSONL, and Parquet artifacts.

## Module

`apps/api/app/validation/schema_validation.py`

## Public functions

- `validate_contract_schemas()` checks all eight contract schema definitions.
- `validate_schema_instance(schema_name, instance)` validates an in-memory
  value against one existing contract schema.
- `validate_dukr_document(dukr)` delegates to the canonical DUKR validator.
- `validate_multimodal_document(record)` delegates to the multimodal validator
  using a deep copy because the existing validator updates its input.
- `validate_generated_dataset(dataset, profile)` reuses the existing M5
  serializer's dataset validation rules without writing an artifact.
- `validate_dataset_artifact(path, profile, output_format=None)` validates
  existing JSON, JSONL, or Parquet output.

## Error format

Each error contains `code`, `path`, `message`, and `severity`.
Validation reports include `valid`, `status`, `errors`, `warnings`,
`error_count`, and `warning_count`.

## Strict parsing

`strict_json_loads` rejects duplicate object keys and non-standard numeric
constants such as NaN and Infinity.

## Boundaries

- Existing schemas and M5 contracts are not changed.
- CSV is not supported by the current M5 serializer and is not accepted here.
- DUKR and multimodal semantic checks remain delegated to their canonical
  implementations.
- This milestone validates structure and integrity; it does not certify
  training quality or model performance.
