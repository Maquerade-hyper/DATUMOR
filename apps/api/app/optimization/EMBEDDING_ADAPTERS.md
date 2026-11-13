# DATUMOR Embedding Provider Adapters

## Purpose

M7.3 provides an optional provider-independent interface for generating
vectors from M7.2 text chunks.

Embedding generation is not required for ingestion, extraction,
transformation, or dataset delivery.

## Common interface

`EmbeddingProvider` defines:

- `metadata`: provider and model identity.
- `embed(texts)`: one vector per input string.

`EmbeddingEngine` handles chunk batching, fingerprints, provenance,
dimension consistency and output validation.

## Ollama

Ollama uses its local `/api/embed` endpoint.

```python
from apps.api.app.optimization.embedding_adapters import (
    OllamaEmbeddingAdapter,
    EmbeddingEngine,
)

provider = OllamaEmbeddingAdapter(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434",
)

engine = EmbeddingEngine(provider)
result = engine.embed_chunks(chunks, batch_size=16)
```

The selected embedding model must be available in Ollama.
Generation requests disable truncation.

## Hugging Face

Hugging Face uses the optional `sentence-transformers` package.

Install it only when this adapter is required:

`python -m pip install sentence-transformers`

```python
from apps.api.app.optimization.embedding_adapters import (
    HuggingFaceEmbeddingAdapter,
    EmbeddingEngine,
)

provider = HuggingFaceEmbeddingAdapter(
    model_id="sentence-transformers/all-MiniLM-L6-v2",
)

engine = EmbeddingEngine(provider)
result = engine.embed_chunks(chunks, batch_size=16)
```

Model download, local cache and hardware requirements depend on the
selected model.

## Output and provenance

Every embedding record preserves:

- Original chunk ID.
- Source metadata and source-content fingerprint.
- Input-text SHA-256.
- Tokenizer fingerprint when provided by the chunk.
- Provider and model identity.
- Vector dimensions and numerical values.

The original chunks are never modified.

## Validation

The engine validates vector count, non-empty vectors, finite numerical
values, consistent dimensions and unique chunk IDs.

Vectors produced by different models or providers must not be assumed
compatible, even if their dimensions happen to match.

## Limitations

- Ollama must have a compatible embedding model installed.
- Hugging Face requires optional `sentence-transformers` and its model
  dependencies.
- No embedding model is downloaded automatically.
- Provider-specific model identity and versioning remain provider-dependent.
- This step generates vectors but does not persist them to Qdrant.

## Live Ollama Integration Verification

Verified against a running local Ollama instance using `nomic-embed-text`.

- Provider: Ollama API (`/api/embed`)
- Model: `nomic-embed-text`
- Actual vector dimensions: 768
- Input chunks: 2
- Embedded chunks: 2
- Batch size: 2
- Embedding record validation: passed
- Provenance metadata: generated
- Original source chunks modified: false
- Execution status: completed

The live integration verified the DATUMOR `OllamaEmbeddingAdapter` and
`EmbeddingEngine` together. Hugging Face inference has only been tested
using a mocked model; real Hugging Face inference remains unverified.
