# DATUMOR Tokenization Engine

## Purpose

The tokenization engine provides reproducible token counts for natural-language
and code datasets using Hugging Face fast tokenizers.

## Loading a tokenizer

A local tokenizer JSON file:

```python
from apps.api.app.optimization.tokenization_engine import TokenizationEngine

engine = TokenizationEngine.load(
    tokenizer_json="path/to/tokenizer.json"
)
```

A Hugging Face model identifier:

```python
engine = TokenizationEngine.load(
    model_id="Qwen/Qwen3-8B",
    revision="main",
)
```

The Hugging Face identifier requires network access or a suitable cached
tokenizer. Authentication-dependent repositories require separate access
configuration.

## Counting text and code

```python
text_result = engine.count_text(
    "Example natural language input",
    content_type="text",
    max_context_tokens=8192,
)

code_result = engine.count_text(
    "def add(a, b): return a + b",
    content_type="code",
    max_context_tokens=8192,
)
```

`content_type` identifies the input category. Both are tokenized by the
selected tokenizer; the engine does not substitute word-count estimates.

## Batch processing

```python
report = engine.count_batch(
    ["First example", "Second example"],
    max_context_tokens=8192,
)
```

The result includes per-item counts, total, minimum, maximum, average and
context-window overflow count.

## Reproducibility

Each result identifies the tokenizer through its source, revision where
applicable, vocabulary size and SHA-256 fingerprint of its serialized
tokenizer configuration.

The context-window limit is supplied by the caller. The engine does not
guess a model's context window from its tokenizer.

## Limitations

- Fast-tokenizer-compatible Hugging Face tokenizer artifacts are supported.
- Model-specific chat templates are not applied automatically.
- Token counts do not include external prompt wrappers unless supplied
  as part of the input text.
- Ollama does not provide a universal tokenizer-counting API; no Ollama
  token-count fallback is claimed.
- This component does not truncate or modify source datasets.
