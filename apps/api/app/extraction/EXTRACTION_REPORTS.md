# DATUMOR Extraction Reports ? M2.5

The report generator converts one or more extraction results into a
JSON-serializable report and a human-readable Markdown report.

## API

- `generate_extraction_report(results, report_id=None, project_id=None)`
- `render_extraction_report_markdown(report)`
- `write_extraction_report(report, output_directory, basename=...)`

`results` can be one extraction result or an iterable of extraction results.
Failed sources can be represented with `status="failed"` and an `error`
message. Partial results can use `status="partial"`.

## Report contents

- Report ID, schema version, project ID and UTC generation timestamp
- Overall success, failure or partial status
- Source counts and format counts
- Extracted record, warning and syntax-error counts
- Per-source source identity, path, media type, size and SHA-256
- Parser metadata, warnings, syntax errors and failure messages

## Output formats

- JSON for programmatic consumption and downstream integrations
- Markdown for readable operational and customer-facing summaries

The report deliberately excludes full extracted content. Original source data
and extracted records remain in their existing storage and dataset workflows.

## Provenance

Source IDs and project IDs are included only when present in extraction
metadata or explicitly supplied result fields. The report generator does not
invent registry identifiers.
