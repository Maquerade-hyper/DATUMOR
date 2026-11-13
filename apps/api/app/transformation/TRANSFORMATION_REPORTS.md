# M5.5 ? Transformation Reports

## Public functions

- `generate_transformation_report(dataset, profile, serialization_reports=None, quality_report=None)`
- `render_transformation_report_markdown(report)`
- `export_transformation_report(report, output_directory, filename="transformation_report")`

## Report outputs

JSON and Markdown reports include:

- Profile identity and transformation settings
- Generated, skipped, and total example counts
- Explicit empty-output status
- Skip reasons and warnings
- Provenance, evidence, and source identity coverage
- Optional externally supplied quality report
- Export formats, sizes, SHA-256 checksums, and statuses
- Dataset snapshot hash and report payload hash

## Status rules

- `completed`: generation completed, no skipped examples, and no failed exports
- `incomplete`: generation is incomplete, examples were skipped, or an export failed
- `failed`: generation explicitly failed

An empty dataset is reported as empty. It is not represented as a successful non-empty training dataset.

## Quality

Quality assessment is marked `not_assessed` unless a quality report is explicitly supplied. No quality score is inferred.

## Integrity

Report generation is read-only. JSON and Markdown report files are written atomically.
