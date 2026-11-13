import pytest
from qdrant_client import QdrantClient

from apps.api.app.optimization.vector_index import (
    QdrantVectorIndex,
    VectorIndexError,
)


@pytest.fixture
def index():
    client = QdrantClient(":memory:")
    instance = QdrantVectorIndex(client=client)
    yield instance
    instance.close()


def make_records():
    provider = {
        "provider": "ollama",
        "model": "nomic-embed-text",
        "dimensions": 3,
    }
    return [
        {
            "chunk_id": "chunk-001",
            "source": {"source_id": "source-001"},
            "source_content_sha256": "a" * 64,
            "input_sha256": "b" * 64,
            "tokenizer_fingerprint": "test-tokenizer",
            "provider": provider,
            "dimensions": 3,
            "embedding": [0.1, 0.2, 0.3],
            "text": "First test chunk",
            "metadata": {"kind": "test"},
        },
        {
            "chunk_id": "chunk-002",
            "source": {"source_id": "source-001"},
            "source_content_sha256": "a" * 64,
            "input_sha256": "c" * 64,
            "tokenizer_fingerprint": "test-tokenizer",
            "provider": provider,
            "dimensions": 3,
            "embedding": [0.2, 0.3, 0.4],
            "text": "Second test chunk",
            "metadata": {"kind": "test"},
        },
    ]


def test_index_and_search_preserves_provenance(index):
    records = make_records()
    result = index.index_embeddings(records)

    assert result["indexed_points"] == 2
    assert result["status"] == "completed"

    search = index.search(
        [0.1, 0.2, 0.3],
        provider="ollama",
        model="nomic-embed-text",
        source_id="source-001",
    )

    assert search["count"] == 2
    assert search["results"][0]["chunk_id"] in {"chunk-001", "chunk-002"}
    assert search["results"][0]["source"]["source_id"] == "source-001"
    assert search["results"][0]["source_content_sha256"] == "a" * 64
    assert search["results"][0]["provider"]["model"] == "nomic-embed-text"


def test_reindex_is_idempotent(index):
    records = make_records()

    index.index_embeddings(records)
    result = index.index_embeddings(records)

    info = index.collection_info("ollama", "nomic-embed-text", 3)

    assert result["indexed_points"] == 2
    assert info["points_count"] == 2


def test_rejects_duplicate_chunk_ids(index):
    records = make_records()
    records.append(records[0].copy())

    with pytest.raises(VectorIndexError, match="Duplicate chunk_id"):
        index.index_embeddings(records)


def test_rejects_mixed_dimensions(index):
    records = make_records()
    records[1]["dimensions"] = 4

    with pytest.raises(VectorIndexError, match="Mixed embedding dimensions"):
        index.index_embeddings(records)


def test_rejects_mixed_models(index):
    records = make_records()
    records[1]["provider"] = {
        "provider": "ollama",
        "model": "different-model",
        "dimensions": 3,
    }

    with pytest.raises(VectorIndexError, match="Mixed embedding providers"):
        index.index_embeddings(records)


def test_rejects_non_finite_vector(index):
    records = make_records()
    records[0]["embedding"] = [0.1, float("nan"), 0.3]

    with pytest.raises(VectorIndexError, match="non-finite"):
        index.index_embeddings(records)


def test_collection_isolated_by_model_and_dimensions(index):
    first = index.collection_name("ollama", "nomic-embed-text", 768)
    second = index.collection_name("ollama", "another-model", 768)
    third = index.collection_name("ollama", "nomic-embed-text", 384)

    assert len({first, second, third}) == 3


def test_empty_search_for_missing_collection(index):
    result = index.search(
        [0.1, 0.2, 0.3],
        provider="ollama",
        model="missing-model",
    )

    assert result["count"] == 0
    assert result["results"] == []


def test_collection_delete(index):
    index.index_embeddings(make_records())

    assert index.delete_collection("ollama", "nomic-embed-text", 3) is True
    assert index.delete_collection("ollama", "nomic-embed-text", 3) is False
