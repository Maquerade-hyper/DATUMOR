# DATUMOR Document Extraction

`document_extractor.py` extracts PDF, TXT, Markdown, JSON, JSONL and CSV.

PDF extraction uses PyMuPDF and preserves page numbers, page dimensions,
rotation, text, available tables and document metadata.

JSONL preserves record and original line numbers. CSV preserves headers
and row records. Markdown preserves heading hierarchy and line numbers.

The module is independent of ingestion and does not modify source records.
Call `extract_document(path, detected_format)` with a staged local file.
