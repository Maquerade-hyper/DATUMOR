# DATUMOR Quality Reports

## M4.5

The quality report generator consolidates the existing quality engines.

### Engines
- Quality metrics and DUKR validation
- Duplicate detection
- Consistency analysis
- Provenance verification

### Public functions
- `generate_quality_report(dukr_documents, near_duplicate_threshold=0.90)`
- `render_quality_report_markdown(report)`
- `export_quality_report(report, output_directory)`

### Output
- `quality_report.json`
- `quality_report.md`

### Status semantics
- `completed`: all DUKR validations pass and provenance has no failed or unverifiable findings.
- `incomplete`: provenance contains unverifiable findings but no failed checks.
- `failed`: at least one DUKR validation or provenance check fails.

Consistency findings and duplicate groups are reported for review; they do not silently modify source data.

Original DUKR documents are treated as read-only inputs.
