"""Provider-independent embedding adapters and vector generation."""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import requests


class EmbeddingError(ValueError):
    """Raised when embedding generation or validation fails."""


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EmbeddingError(f"{name} must be a positive integer")


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_vector(vector: Any, expected_dimension: int | None = None) -> int:
    if not isinstance(vector, (list, tuple)) or not vector:
        raise EmbeddingError("Embedding vector must be a non-empty list")

    if expected_dimension is not None and len(vector) != expected_dimension:
        raise EmbeddingError(
            f"Expected vector dimension {expected_dimension}, got {len(vector)}"
        )

    for value in vector:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise EmbeddingError("Embedding contains a non-finite or non-numeric value")

    return len(vector)


class EmbeddingProvider(ABC):
    """Common interface implemented by embedding providers."""

    @property
    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HuggingFaceEmbeddingAdapter(EmbeddingProvider):
    """Optional local Sentence Transformers adapter."""

    def __init__(
        self,
        model_id: str,
        device: str | None = None,
        normalize_embeddings: bool = True,
        model: Any | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise EmbeddingError("model_id cannot be empty")

        self.model_id = model_id.strip()
        self.normalize_embeddings = normalize_embeddings

        if model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "Hugging Face embeddings require the optional "
                    "'sentence-transformers' package"
                ) from exc

            try:
                model = SentenceTransformer(
                    self.model_id,
                    device=device,
                )
            except Exception as exc:
                raise EmbeddingError(
                    f"Unable to load embedding model {self.model_id}: {exc}"
                ) from exc

        self._model = model
        self._dimension: int | None = None

        try:
            dimension = model.get_sentence_embedding_dimension()
            if dimension is not None:
                _positive_integer(dimension, "embedding dimension")
                self._dimension = dimension
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(
                f"Unable to inspect embedding model dimension: {exc}"
            ) from exc

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "huggingface",
            "model": self.model_id,
            "dimensions": self._dimension,
            "normalization": self.normalize_embeddings,
            "execution": "sentence-transformers",
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not isinstance(texts, list) or not all(
            isinstance(text, str) for text in texts
        ):
            raise EmbeddingError("texts must be a list of strings")

        if not texts:
            return []

        try:
            result = self._model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False,
            )
            vectors = result.tolist() if hasattr(result, "tolist") else result
        except Exception as exc:
            raise EmbeddingError(
                f"Hugging Face embedding generation failed: {exc}"
            ) from exc

        if not isinstance(vectors, (list, tuple)) or len(vectors) != len(texts):
            raise EmbeddingError(
                "Hugging Face returned an unexpected number of vectors"
            )

        normalized = []
        dimension = self._dimension

        for vector in vectors:
            current_dimension = validate_vector(vector, dimension)
            if dimension is None:
                dimension = current_dimension
            normalized.append([float(value) for value in vector])

        self._dimension = dimension
        return normalized


class OllamaEmbeddingAdapter(EmbeddingProvider):
    """Adapter for Ollama's local /api/embed endpoint."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        dimensions: int | None = None,
        session: Any | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise EmbeddingError("model cannot be empty")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise EmbeddingError("Invalid Ollama base_url")

        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise EmbeddingError("timeout must be a positive finite number")

        if dimensions is not None:
            _positive_integer(dimensions, "dimensions")

        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._dimension = dimensions
        self._session = session or requests.Session()

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "model": self.model,
            "base_url": self.base_url,
            "dimensions": self._dimension,
            "normalization": "provider_default",
            "execution": "ollama_api_embed",
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not isinstance(texts, list) or not all(
            isinstance(text, str) for text in texts
        ):
            raise EmbeddingError("texts must be a list of strings")

        if not texts:
            return []

        payload = {
            "model": self.model,
            "input": texts,
            "truncate": False,
        }

        if self._dimension is not None:
            payload["dimensions"] = self._dimension

        try:
            response = self._session.post(
                f"{self.base_url}/api/embed",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise EmbeddingError(
                f"Ollama embedding request failed: {exc}"
            ) from exc
        except (ValueError, TypeError) as exc:
            raise EmbeddingError(
                f"Ollama returned invalid JSON: {exc}"
            ) from exc

        if not isinstance(body, dict):
            raise EmbeddingError("Ollama response must be an object")

        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError(
                "Ollama returned an unexpected number of embeddings"
            )

        normalized = []
        dimension = self._dimension

        for vector in vectors:
            current_dimension = validate_vector(vector, dimension)
            if dimension is None:
                dimension = current_dimension
            normalized.append([float(value) for value in vector])

        self._dimension = dimension
        return normalized


def validate_embedding_records(records: list[dict]) -> dict:
    errors = []
    expected_dimension = None
    seen_ids = set()

    if not isinstance(records, list):
        raise EmbeddingError("records must be a list")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"Record {index} must be an object")
            continue

        chunk_id = record.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            errors.append(f"Record {index} has no chunk_id")
        elif chunk_id in seen_ids:
            errors.append(f"Duplicate chunk_id: {chunk_id}")
        else:
            seen_ids.add(chunk_id)

        try:
            dimension = validate_vector(
                record.get("embedding"),
                expected_dimension,
            )
            if expected_dimension is None:
                expected_dimension = dimension
        except EmbeddingError as exc:
            errors.append(f"Record {index}: {exc}")

        if not isinstance(record.get("input_sha256"), str):
            errors.append(f"Record {index} has no input fingerprint")

        if not isinstance(record.get("provider"), dict):
            errors.append(f"Record {index} has no provider metadata")

    return {
        "valid": not errors,
        "errors": errors,
        "record_count": len(records),
        "dimensions": expected_dimension,
    }


class EmbeddingEngine:
    """Generate and validate embeddings for chunk collections."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        if not isinstance(provider, EmbeddingProvider):
            raise EmbeddingError("provider must implement EmbeddingProvider")
        self.provider = provider

    def embed_chunks(
        self,
        chunks: list[dict],
        batch_size: int = 32,
    ) -> dict[str, Any]:
        if not isinstance(chunks, list):
            raise EmbeddingError("chunks must be a list")

        _positive_integer(batch_size, "batch_size")

        snapshots = [
            json.dumps(chunk, sort_keys=True, ensure_ascii=False)
            for chunk in chunks
        ]

        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise EmbeddingError(f"Chunk {index} must be an object")
            if not isinstance(chunk.get("chunk_id"), str) or not chunk["chunk_id"]:
                raise EmbeddingError(f"Chunk {index} has no chunk_id")
            if not isinstance(chunk.get("text"), str):
                raise EmbeddingError(f"Chunk {index} has no text")

        records = []

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            texts = [chunk["text"] for chunk in batch]

            vectors = self.provider.embed(texts)
            if len(vectors) != len(batch):
                raise EmbeddingError(
                    "Provider returned a different number of vectors than inputs"
                )

            for chunk, vector in zip(batch, vectors):
                validate_vector(vector)

                records.append({
                    "chunk_id": chunk["chunk_id"],
                    "source": dict(chunk.get("source") or {}),
                    "source_content_sha256": chunk.get(
                        "source_content_sha256"
                    ),
                    "input_sha256": _fingerprint(chunk["text"]),
                    "tokenizer_fingerprint": chunk.get(
                        "tokenizer_fingerprint"
                    ),
                    "provider": self.provider.metadata.copy(),
                    "dimensions": len(vector),
                    "embedding": [float(value) for value in vector],
                })

        if snapshots != [
            json.dumps(chunk, sort_keys=True, ensure_ascii=False)
            for chunk in chunks
        ]:
            raise EmbeddingError("Embedding generation modified input chunks")

        validation = validate_embedding_records(records)
        if not validation["valid"]:
            raise EmbeddingError(
                "Invalid embedding output: " + "; ".join(validation["errors"])
            )

        return {
            "status": "completed",
            "provider": self.provider.metadata.copy(),
            "summary": {
                "input_chunks": len(chunks),
                "embedded_chunks": len(records),
                "dimensions": validation["dimensions"],
                "batch_size": batch_size,
            },
            "embeddings": records,
            "validation": validation,
            "source_chunks_modified": False,
        }
