"""Model-independent Hugging Face tokenization engine."""

from __future__ import annotations

import hashlib
import math
import statistics
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer


class TokenizationError(ValueError):
    """Raised when tokenizer loading or tokenization fails."""


def _positive_integer(value: int | None, name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise TokenizationError(f"{name} must be a positive integer")


class TokenizationEngine:
    """Reproducible token counting through Hugging Face tokenizers."""

    def __init__(
        self,
        tokenizer: Tokenizer,
        identity: dict[str, Any],
    ) -> None:
        self._tokenizer = tokenizer
        self.identity = identity

    @classmethod
    def load(
        cls,
        tokenizer_json: str | Path | None = None,
        model_id: str | None = None,
        revision: str = "main",
        cache_dir: str | Path | None = None,
    ) -> "TokenizationEngine":
        if (tokenizer_json is None) == (model_id is None):
            raise TokenizationError(
                "Provide exactly one of tokenizer_json or model_id"
            )

        try:
            if tokenizer_json is not None:
                path = Path(tokenizer_json).expanduser().resolve()
                if not path.is_file():
                    raise TokenizationError(
                        f"Tokenizer file does not exist: {path}"
                    )
                tokenizer = Tokenizer.from_file(str(path))
                source = str(path)
                source_type = "local"
            else:
                if not isinstance(model_id, str) or not model_id.strip():
                    raise TokenizationError("model_id cannot be empty")
                if not isinstance(revision, str) or not revision.strip():
                    raise TokenizationError("revision cannot be empty")

                tokenizer = Tokenizer.from_pretrained(
                    model_id.strip(),
                    revision=revision,
                    cache_dir=str(cache_dir) if cache_dir else None,
                )
                source = model_id.strip()
                source_type = "huggingface"

            serialized = tokenizer.to_str()
            fingerprint = hashlib.sha256(
                serialized.encode("utf-8")
            ).hexdigest()

            identity = {
                "provider": "huggingface-tokenizers",
                "source_type": source_type,
                "source": source,
                "revision": revision if source_type == "huggingface" else None,
                "fingerprint_sha256": fingerprint,
                "vocabulary_size": tokenizer.get_vocab_size(
                    with_added_tokens=True
                ),
                "tokenizer_library": "tokenizers",
            }

            return cls(tokenizer, identity)

        except TokenizationError:
            raise
        except Exception as exc:
            raise TokenizationError(
                f"Unable to load tokenizer: {exc}"
            ) from exc

    def count_text(
        self,
        text: str,
        content_type: str = "text",
        add_special_tokens: bool = True,
        max_context_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(text, str):
            raise TokenizationError("text must be a string")

        if content_type not in {"text", "code"}:
            raise TokenizationError(
                "content_type must be 'text' or 'code'"
            )

        _positive_integer(max_context_tokens, "max_context_tokens")

        try:
            encoding = self._tokenizer.encode(
                text,
                add_special_tokens=add_special_tokens,
            )
            count = len(encoding.ids)
        except Exception as exc:
            raise TokenizationError(
                f"Tokenization failed: {exc}"
            ) from exc

        overflow = (
            max_context_tokens is not None
            and count > max_context_tokens
        )

        return {
            "token_count": count,
            "content_type": content_type,
            "character_count": len(text),
            "add_special_tokens": add_special_tokens,
            "max_context_tokens": max_context_tokens,
            "context_overflow": overflow,
            "context_usage_ratio": (
                count / max_context_tokens
                if max_context_tokens is not None
                else None
            ),
            "tokenizer_fingerprint": self.identity["fingerprint_sha256"],
        }

    def count_batch(
        self,
        texts: list[str],
        content_type: str = "text",
        add_special_tokens: bool = True,
        max_context_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(texts, list):
            raise TokenizationError("texts must be a list")

        _positive_integer(max_context_tokens, "max_context_tokens")

        results = [
            self.count_text(
                text=text,
                content_type=content_type,
                add_special_tokens=add_special_tokens,
                max_context_tokens=max_context_tokens,
            )
            for text in texts
        ]

        counts = [item["token_count"] for item in results]

        return {
            "tokenizer": self.identity.copy(),
            "item_count": len(results),
            "total_tokens": sum(counts),
            "minimum_tokens": min(counts) if counts else 0,
            "maximum_tokens": max(counts) if counts else 0,
            "average_tokens": statistics.fmean(counts) if counts else 0.0,
            "overflow_count": sum(
                item["context_overflow"] for item in results
            ),
            "items": results,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "tokenizer": self.identity.copy(),
            "supported_content_types": ["text", "code"],
            "supports_batch_processing": True,
            "supports_context_overflow_detection": True,
            "counting_mode": "exact_tokenizer_encoding",
        }


def validate_tokenization_result(result: dict[str, Any]) -> None:
    """Validate the structure and numerical integrity of a result."""

    if not isinstance(result, dict):
        raise TokenizationError("Result must be a dictionary")

    count = result.get("token_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TokenizationError("Invalid token_count")

    ratio = result.get("context_usage_ratio")
    if ratio is not None and (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not math.isfinite(ratio)
        or ratio < 0
    ):
        raise TokenizationError("Invalid context_usage_ratio")
