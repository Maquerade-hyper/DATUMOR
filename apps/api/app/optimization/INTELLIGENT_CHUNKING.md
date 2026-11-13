# DATUMOR Intelligent Chunking

## Purpose

M7.2 splits text and code into token-limited chunks using the M7.1
Hugging Face tokenizer engine.

## Usage

```python
from apps.api.app.optimization.tokenization_engine import TokenizationEngine
from apps.api.app.optimization.intelligent_chunker import IntelligentChunker

tokenizer = TokenizationEngine.load(tokenizer_json="tokenizer.json")
chunker = IntelligentChunker(tokenizer)

result = chunker.chunk_text(
    text="Your source text",
    source={
        "source_id": "source-123",
        "filename": "example.txt",
        "checksum_sha256": "source-checksum",
    },
    content_type="text",
    chunk_size=512,
    overlap=64,
)
```

## Features

- Exact token counting through the configured M7.1 tokenizer.
- Configurable maximum token count and overlap.
- Paragraph/sentence boundary preference for text.
- Line boundary preference for code.
- Token-safe fallback for oversized structural units.
- Stable chunk IDs based on source identity, offsets and content.
- Source SHA-256, provenance metadata and character offsets.
- Previous/next chunk references.
- Independent structural validation.
- Input source is never modified.

## Limitations

- Chunking operates on supplied text; it does not extract text from source files.
- Structural boundaries are heuristic, not semantic AI segmentation.
- Code boundaries currently prefer lines; AST-aware code chunking is not claimed.
- Character offsets refer to the original Unicode string.
- Token counts depend on the exact selected tokenizer and special-token setting.
- Overlap is measured in tokenizer tokens, but recorded as character overlap.
- Multimodal payloads are not split by this text chunker.
