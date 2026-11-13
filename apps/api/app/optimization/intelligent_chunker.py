"""Token-aware, provenance-preserving intelligent chunking."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from apps.api.app.optimization.tokenization_engine import (
    TokenizationEngine,
)


class ChunkingError(ValueError):
    """Raised when chunk generation or validation fails."""


def _stable_id(value: dict) -> str:
    serialized = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_settings(
    chunk_size: int,
    overlap: int,
) -> None:
    for name, value in (
        ("chunk_size", chunk_size),
        ("overlap", overlap),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ChunkingError(f"{name} must be an integer")
        if value < 0 or (name == "chunk_size" and value == 0):
            raise ChunkingError(f"Invalid {name}")

    if overlap >= chunk_size:
        raise ChunkingError("overlap must be smaller than chunk_size")


def _source_metadata(source: dict | None) -> dict:
    if source is None:
        return {}

    if not isinstance(source, dict):
        raise ChunkingError("source must be a dictionary")

    allowed = (
        "source_id",
        "project_id",
        "filename",
        "checksum_sha256",
        "media_type",
        "uri",
    )
    return {
        key: source[key]
        for key in allowed
        if key in source
    }


def _split_boundaries(text: str, content_type: str) -> list[tuple[int, int]]:
    """Return ordered sentence/paragraph/code-aware text spans."""

    if not text:
        return []

    if content_type == "code":
        # Prefer line boundaries; retain newline characters in each span.
        spans = []
        start = 0
        for match in re.finditer(r"\n", text):
            end = match.end()
            spans.append((start, end))
            start = end
        if start < len(text):
            spans.append((start, len(text)))
        return spans

    # Keep paragraph boundaries first, then sentence boundaries.
    spans = []
    pattern = re.compile(r".+?(?:\n\s*\n|(?<=[.!?])\s+|$)", re.DOTALL)
    for match in pattern.finditer(text):
        if match.start() < match.end():
            spans.append((match.start(), match.end()))

    if not spans:
        return [(0, len(text))]

    return spans


class IntelligentChunker:
    """Build chunks whose exact tokenizer counts fit a configured limit."""

    def __init__(self, tokenizer: TokenizationEngine) -> None:
        if not isinstance(tokenizer, TokenizationEngine):
            raise ChunkingError("A TokenizationEngine instance is required")
        self.tokenizer = tokenizer

    def chunk_text(
        self,
        text: str,
        source: dict | None = None,
        content_type: str = "text",
        chunk_size: int = 512,
        overlap: int = 64,
        add_special_tokens: bool = False,
    ) -> dict[str, Any]:
        _validate_settings(chunk_size, overlap)

        if not isinstance(text, str):
            raise ChunkingError("text must be a string")

        if content_type not in {"text", "code"}:
            raise ChunkingError("content_type must be text or code")

        source_info = _source_metadata(source)
        source_fingerprint = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        if not text:
            return {
                "status": "completed",
                "content_type": content_type,
                "source": source_info,
                "source_content_sha256": source_fingerprint,
                "tokenizer": self.tokenizer.identity.copy(),
                "configuration": {
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                    "add_special_tokens": add_special_tokens,
                },
                "summary": {
                    "chunk_count": 0,
                    "source_characters": 0,
                    "total_chunk_tokens": 0,
                },
                "chunks": [],
            }

        boundaries = _split_boundaries(text, content_type)
        chunks = []
        cursor = 0
        chunk_index = 0

        while cursor < len(text):
            remaining = text[cursor:]
            remaining_result = self.tokenizer.count_text(
                remaining,
                content_type=content_type,
                add_special_tokens=add_special_tokens,
            )

            if remaining_result["token_count"] <= chunk_size:
                end = len(text)
            else:
                # Find the furthest valid structural boundary within the
                # token budget, then fall back to a token-safe character
                # boundary when one structural unit is too large.
                candidates = [
                    end
                    for start, end in boundaries
                    if end > cursor
                ]

                valid_ends = []
                for end_candidate in candidates:
                    if end_candidate <= cursor:
                        continue
                    candidate = text[cursor:end_candidate]
                    count = self.tokenizer.count_text(
                        candidate,
                        content_type=content_type,
                        add_special_tokens=add_special_tokens,
                    )["token_count"]
                    if count <= chunk_size:
                        valid_ends.append(end_candidate)
                    elif valid_ends:
                        break

                if valid_ends:
                    end = max(valid_ends)
                else:
                    # A single line or sentence may exceed the limit.
                    # Binary search for the largest fitting character span.
                    low = cursor + 1
                    high = len(text)
                    best = cursor

                    while low <= high:
                        middle = (low + high) // 2
                        count = self.tokenizer.count_text(
                            text[cursor:middle],
                            content_type=content_type,
                            add_special_tokens=add_special_tokens,
                        )["token_count"]

                        if count <= chunk_size:
                            best = middle
                            low = middle + 1
                        else:
                            high = middle - 1

                    if best == cursor:
                        raise ChunkingError(
                            "Unable to fit even one character within chunk_size"
                        )
                    end = best

            chunk_text = text[cursor:end]
            token_result = self.tokenizer.count_text(
                chunk_text,
                content_type=content_type,
                add_special_tokens=add_special_tokens,
            )
            token_count = token_result["token_count"]

            if token_count > chunk_size:
                raise ChunkingError("Generated chunk exceeds token limit")

            chunk = {
                "chunk_index": chunk_index,
                "chunk_id": "",
                "text": chunk_text,
                "start_char": cursor,
                "end_char": end,
                "token_count": token_count,
                "content_type": content_type,
                "source": source_info.copy(),
                "source_content_sha256": source_fingerprint,
                "tokenizer_fingerprint": (
                    self.tokenizer.identity["fingerprint_sha256"]
                ),
                "previous_chunk_id": (
                    chunks[-1]["chunk_id"] if chunks else None
                ),
                "next_chunk_id": None,
                "overlap_with_previous_chars": 0,
            }

            chunk["chunk_id"] = _stable_id({
                "source_content_sha256": source_fingerprint,
                "source": source_info,
                "chunk_index": chunk_index,
                "start_char": cursor,
                "end_char": end,
                "text": chunk_text,
            })

            if chunks:
                previous = chunks[-1]
                previous["next_chunk_id"] = chunk["chunk_id"]

            chunks.append(chunk)
            chunk_index += 1

            if end >= len(text):
                break

            # Target overlap by tokens, while avoiding an infinite loop.
            next_cursor = end
            if overlap:
                low = cursor
                high = end
                overlap_start = end

                while low <= high:
                    middle = (low + high) // 2
                    count = self.tokenizer.count_text(
                        text[middle:end],
                        content_type=content_type,
                        add_special_tokens=add_special_tokens,
                    )["token_count"]

                    if count <= overlap:
                        overlap_start = middle
                        high = middle - 1
                    else:
                        low = middle + 1

                next_cursor = overlap_start

            if next_cursor <= cursor:
                next_cursor = end

            chunks[-1]["overlap_with_next_chars"] = end - next_cursor
            cursor = next_cursor

        for index, chunk in enumerate(chunks):
            if index == 0:
                chunk["overlap_with_previous_chars"] = 0
            else:
                chunk["overlap_with_previous_chars"] = (
                    chunks[index - 1]["end_char"] - chunk["start_char"]
                )

            if index == len(chunks) - 1:
                chunk["overlap_with_next_chars"] = 0

        result = {
            "status": "completed",
            "content_type": content_type,
            "source": source_info,
            "source_content_sha256": source_fingerprint,
            "tokenizer": self.tokenizer.identity.copy(),
            "configuration": {
                "chunk_size": chunk_size,
                "overlap": overlap,
                "add_special_tokens": add_special_tokens,
            },
            "summary": {
                "chunk_count": len(chunks),
                "source_characters": len(text),
                "total_chunk_tokens": sum(
                    chunk["token_count"] for chunk in chunks
                ),
                "maximum_chunk_tokens": max(
                    chunk["token_count"] for chunk in chunks
                ),
            },
            "chunks": chunks,
        }

        validation = validate_chunk_result(result)
        if not validation["valid"]:
            raise ChunkingError(
                "Generated chunk result is invalid: "
                + "; ".join(validation["errors"])
            )

        return result


def validate_chunk_result(result: dict) -> dict:
    errors = []

    if not isinstance(result, dict):
        raise ChunkingError("result must be a dictionary")

    chunks = result.get("chunks")
    if not isinstance(chunks, list):
        raise ChunkingError("chunks must be a list")

    configuration = result.get("configuration", {})
    chunk_size = configuration.get("chunk_size")

    ids = set()
    previous_end = 0

    for index, chunk in enumerate(chunks):
        if chunk.get("chunk_index") != index:
            errors.append(f"Invalid chunk ordering at index {index}")

        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            errors.append(f"Missing chunk ID at index {index}")
        elif chunk_id in ids:
            errors.append(f"Duplicate chunk ID at index {index}")
        ids.add(chunk_id)

        token_count = chunk.get("token_count")
        if (
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
        ):
            errors.append(f"Invalid token count at index {index}")
        elif isinstance(chunk_size, int) and token_count > chunk_size:
            errors.append(f"Chunk exceeds token limit at index {index}")

        start = chunk.get("start_char")
        end = chunk.get("end_char")
        text = chunk.get("text")

        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not isinstance(text, str)
            or start < 0
            or end < start
            or end - start != len(text)
        ):
            errors.append(f"Invalid source offsets at index {index}")
            continue

        if index > 0 and start > previous_end:
            errors.append(f"Source gap before chunk {index}")

        previous_end = max(previous_end, end)

        if index > 0:
            if chunk.get("previous_chunk_id") != chunks[index - 1].get("chunk_id"):
                errors.append(f"Invalid previous chunk reference at {index}")
        elif chunk.get("previous_chunk_id") is not None:
            errors.append("First chunk must not have a previous reference")

        if index < len(chunks) - 1:
            if chunk.get("next_chunk_id") != chunks[index + 1].get("chunk_id"):
                errors.append(f"Invalid next chunk reference at {index}")
        elif chunk.get("next_chunk_id") is not None:
            errors.append("Last chunk must not have a next reference")

    if chunks:
        source_length = result.get("summary", {}).get("source_characters")
        if previous_end != source_length:
            errors.append("Chunks do not cover the source through its final character")

    return {"valid": not errors, "errors": errors}
