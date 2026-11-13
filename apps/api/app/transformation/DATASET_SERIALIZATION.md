# M5.4 ? Data Formatting and Serialization

## Public function

`serialize_dataset(dataset, profile, output_path, output_format=None)`

## Supported formats

- JSONL: one complete example per line.
- JSON: dataset envelope with schema, profile, summary, examples, and skipped records.
- Parquet: columnar representation with provenance and additional fields encoded as JSON columns.

## Validation

Before writing:
- Generated dataset type is checked.
- Profile ID and version must match.
- Every example must satisfy the profile required fields.
- Every example must have a stable ID.
- Provenance source identity is required when profile preservation is enabled.
- File extension must match the selected format.

## Integrity

- Writes use temporary files and atomic replacement.
- Output SHA-256 and byte size are recorded.
- Parquet schema metadata records the profile and schema versions.
- Nested provenance is retained.
- Input generated datasets are never modified.

## Scope

This step serializes generated examples. Customer-facing downloads, transformation dashboards, and consolidated transformation reports belong to M5.5 and M9.
