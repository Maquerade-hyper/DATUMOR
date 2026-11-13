# DATUMOR Metadata Extraction ? M2.4

The metadata extraction module adds a common `metadata.source` object to
document and code extraction results while retaining all parser-specific
metadata.

## Common source metadata

- Filename, path and extension
- Detected format and MIME type
- File size in bytes
- SHA-256 checksum
- Text encoding where identifiable
- File creation and modification timestamps (UTC)
- Character and line counts for text content
- Metadata schema version

## Provenance

Call `extract_metadata(..., source_metadata={...})` to attach known source
registry identifiers. The identifiers are preserved under `metadata.source_identity`.
The module does not invent source IDs or project IDs.

## Integration

Document extraction integrates through `_base_result`, so PDF, text,
Markdown, JSON, JSONL and CSV keep their existing metadata. Code extraction
integrates directly with the Tree-sitter parser.

## Limitations

Filesystem creation timestamps can represent metadata-change time rather than
true creation time on some platforms. Encoding is inferred from byte-order
marks and decoding checks; binary or unknown data is labelled accordingly.
MIME type is inferred from the filename extension and is not a content-security
validation result. SHA-256 is calculated from the original file bytes.
