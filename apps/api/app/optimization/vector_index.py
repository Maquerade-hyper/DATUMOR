from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from qdrant_client import QdrantClient, models


class VectorIndexError(Exception):
    """Raised when vector indexing or retrieval fails."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_vector(vector: Any, dimensions: int | None = None) -> int:
    if not isinstance(vector, list) or not vector:
        raise VectorIndexError("Embedding vector must be a non-empty list.")

    if dimensions is not None and len(vector) != dimensions:
        raise VectorIndexError("Embedding dimension mismatch.")

    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VectorIndexError("Embedding contains a non-numeric value.")
        if not float("-inf") < float(value) < float("inf"):
            raise VectorIndexError("Embedding contains a non-finite value.")

    return len(vector)


def _point_id(collection_name: str, chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_name}:{chunk_id}"))


class QdrantVectorIndex:
    """Provenance-preserving Qdrant vector index."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:6333",
        api_key: str | None = None,
        client: QdrantClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.client = client or QdrantClient(
            url=url,
            api_key=api_key,
            timeout=timeout,
        )

    @staticmethod
    def collection_name(provider: str, model: str, dimensions: int) -> str:
        if not provider or not model or dimensions <= 0:
            raise VectorIndexError("Provider, model and positive dimensions are required.")

        identity = f"{provider}:{model}:{dimensions}"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{provider}-{model}").strip("-")
        slug = slug[:35].lower()
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        return f"datumor-{slug}-{dimensions}-{suffix}"

    def ensure_collection(
        self,
        provider: str,
        model: str,
        dimensions: int,
    ) -> str:
        name = self.collection_name(provider, model, dimensions)

        if self.client.collection_exists(name):
            info = self.client.get_collection(name)
            config = info.config.params.vectors

            if isinstance(config, dict):
                vector_config = config.get("")

                if vector_config is None and len(config) == 1:
                    vector_config = next(iter(config.values()))
            else:
                vector_config = config

            if vector_config is None or vector_config.size != dimensions:
                raise VectorIndexError(
                    "Existing collection has an incompatible vector configuration."
                )

            return name

        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dimensions,
                distance=models.Distance.COSINE,
            ),
        )
        return name

    def index_embeddings(
        self,
        records: list[dict[str, Any]],
        batch_size: int = 64,
    ) -> dict[str, Any]:
        if not records:
            raise VectorIndexError("No embedding records supplied.")

        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise VectorIndexError("batch_size must be a positive integer.")

        first = records[0]
        provider_info = first.get("provider")

        if not isinstance(provider_info, dict):
            raise VectorIndexError("Embedding provider metadata is required.")

        provider = provider_info.get("provider")
        model = provider_info.get("model")
        dimensions = first.get("dimensions")

        if not isinstance(provider, str) or not provider:
            raise VectorIndexError("Provider identity is missing.")
        if not isinstance(model, str) or not model:
            raise VectorIndexError("Model identity is missing.")
        if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
            raise VectorIndexError("Invalid embedding dimensions.")

        seen: set[str] = set()
        points: list[models.PointStruct] = []

        for record in records:
            if not isinstance(record, dict):
                raise VectorIndexError("Each embedding record must be an object.")

            chunk_id = record.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise VectorIndexError("Every record must have a chunk_id.")

            if chunk_id in seen:
                raise VectorIndexError(f"Duplicate chunk_id: {chunk_id}")
            seen.add(chunk_id)

            if record.get("dimensions") != dimensions:
                raise VectorIndexError("Mixed embedding dimensions are not allowed.")

            if record.get("provider") != provider_info:
                raise VectorIndexError("Mixed embedding providers or models are not allowed.")

            vector = record.get("embedding")
            _validate_vector(vector, dimensions)

            source = record.get("source", {})
            if not isinstance(source, dict):
                raise VectorIndexError("Source provenance must be an object.")

            payload = {
                "chunk_id": chunk_id,
                "source": source,
                "source_content_sha256": record.get("source_content_sha256"),
                "input_sha256": record.get("input_sha256"),
                "tokenizer_fingerprint": record.get("tokenizer_fingerprint"),
                "provider": provider_info,
                "dimensions": dimensions,
                "content": record.get("text", record.get("content")),
                "metadata": record.get("metadata", {}),
            }

            points.append(
                models.PointStruct(
                    id=_point_id(
                        self.collection_name(provider, model, dimensions),
                        chunk_id,
                    ),
                    vector=[float(value) for value in vector],
                    payload=payload,
                )
            )

        collection = self.ensure_collection(provider, model, dimensions)

        for start in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=collection,
                points=points[start : start + batch_size],
                wait=True,
            )

        return {
            "status": "completed",
            "collection": collection,
            "provider": provider,
            "model": model,
            "dimensions": dimensions,
            "input_records": len(records),
            "indexed_points": len(points),
            "batch_size": batch_size,
            "idempotent": True,
        }

    def search(
        self,
        vector: list[float],
        provider: str,
        model: str,
        limit: int = 10,
        source_id: str | None = None,
        score_threshold: float | None = None,
    ) -> dict[str, Any]:
        dimensions = _validate_vector(vector)

        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise VectorIndexError("limit must be a positive integer.")

        collection = self.collection_name(provider, model, dimensions)

        if not self.client.collection_exists(collection):
            return {
                "status": "completed",
                "collection": collection,
                "count": 0,
                "results": [],
            }

        query_filter = None
        if source_id is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source.source_id",
                        match=models.MatchValue(value=source_id),
                    )
                ]
            )

        response = self.client.query_points(
            collection_name=collection,
            query=[float(value) for value in vector],
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                {
                    "point_id": str(point.id),
                    "chunk_id": payload.get("chunk_id"),
                    "score": float(point.score),
                    "content": payload.get("content"),
                    "source": payload.get("source"),
                    "source_content_sha256": payload.get("source_content_sha256"),
                    "input_sha256": payload.get("input_sha256"),
                    "tokenizer_fingerprint": payload.get("tokenizer_fingerprint"),
                    "provider": payload.get("provider"),
                    "dimensions": payload.get("dimensions"),
                    "metadata": payload.get("metadata"),
                }
            )

        return {
            "status": "completed",
            "collection": collection,
            "count": len(results),
            "results": results,
        }

    def collection_info(
        self,
        provider: str,
        model: str,
        dimensions: int,
    ) -> dict[str, Any]:
        name = self.collection_name(provider, model, dimensions)

        if not self.client.collection_exists(name):
            return {"exists": False, "collection": name}

        info = self.client.get_collection(name)
        return {
            "exists": True,
            "collection": name,
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": str(info.status),
            "dimensions": dimensions,
        }

    def delete_collection(
        self,
        provider: str,
        model: str,
        dimensions: int,
    ) -> bool:
        name = self.collection_name(provider, model, dimensions)

        if not self.client.collection_exists(name):
            return False

        self.client.delete_collection(name)
        return True

    def close(self) -> None:
        self.client.close()
