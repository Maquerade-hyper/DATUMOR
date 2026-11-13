
import pytest

from apps.api.app.optimization.embedding_adapters import (
    EmbeddingEngine,
    EmbeddingError,
    EmbeddingProvider,
    HuggingFaceEmbeddingAdapter,
    OllamaEmbeddingAdapter,
    validate_embedding_records,
    validate_vector,
)


class FakeProvider(EmbeddingProvider):
    @property
    def metadata(self):
        return {
            "provider": "test",
            "model": "fake-embedding",
            "dimensions": 3,
        }

    def embed(self, texts):
        return [[float(len(text)), 1.0, 2.0] for text in texts]


class FakeHFModel:
    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, **kwargs):
        return [[float(len(text)), 1.0, 2.0] for text in texts]


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError("HTTP failure")

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse(self.body)


@pytest.fixture
def chunks():
    return [
        {
            "chunk_id": "chunk-1",
            "text": "first chunk",
            "source": {"source_id": "source-1"},
            "source_content_sha256": "source-hash",
            "tokenizer_fingerprint": "tokenizer-hash",
        },
        {
            "chunk_id": "chunk-2",
            "text": "second chunk",
            "source": {"source_id": "source-1"},
            "source_content_sha256": "source-hash",
            "tokenizer_fingerprint": "tokenizer-hash",
        },
    ]


def test_validate_vector():
    assert validate_vector([0.1, 0.2, 0.3]) == 3


def test_reject_empty_vector():
    with pytest.raises(EmbeddingError):
        validate_vector([])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_reject_nonfinite_vector(value):
    with pytest.raises(EmbeddingError):
        validate_vector([value])


def test_reject_boolean_vector_value():
    with pytest.raises(EmbeddingError):
        validate_vector([True])


def test_reject_wrong_dimension():
    with pytest.raises(EmbeddingError):
        validate_vector([1.0, 2.0], expected_dimension=3)


def test_huggingface_adapter():
    adapter = HuggingFaceEmbeddingAdapter(
        "test-model",
        model=FakeHFModel(),
    )
    vectors = adapter.embed(["hello", "world"])
    assert len(vectors) == 2
    assert adapter.metadata["dimensions"] == 3


def test_huggingface_empty_batch():
    adapter = HuggingFaceEmbeddingAdapter(
        "test-model",
        model=FakeHFModel(),
    )
    assert adapter.embed([]) == []


def test_huggingface_invalid_model_id():
    with pytest.raises(EmbeddingError):
        HuggingFaceEmbeddingAdapter("", model=FakeHFModel())


def test_ollama_adapter():
    session = FakeSession({
        "model": "nomic-embed-text",
        "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    })
    adapter = OllamaEmbeddingAdapter(
        "nomic-embed-text",
        session=session,
    )
    vectors = adapter.embed(["first", "second"])
    assert len(vectors) == 2
    assert adapter.metadata["dimensions"] == 3
    assert session.calls[0][0].endswith("/api/embed")
    assert session.calls[0][1]["truncate"] is False


def test_ollama_dimension_request():
    session = FakeSession({"embeddings": [[0.1, 0.2, 0.3]]})
    adapter = OllamaEmbeddingAdapter(
        "test-model",
        dimensions=3,
        session=session,
    )
    adapter.embed(["hello"])
    assert session.calls[0][1]["dimensions"] == 3


def test_ollama_invalid_response_count():
    session = FakeSession({"embeddings": []})
    adapter = OllamaEmbeddingAdapter("test-model", session=session)
    with pytest.raises(EmbeddingError):
        adapter.embed(["hello"])


def test_ollama_invalid_base_url():
    with pytest.raises(EmbeddingError):
        OllamaEmbeddingAdapter("test-model", base_url="invalid")


def test_ollama_invalid_timeout():
    with pytest.raises(EmbeddingError):
        OllamaEmbeddingAdapter("test-model", timeout=0)


def test_embedding_engine_batching(chunks):
    result = EmbeddingEngine(FakeProvider()).embed_chunks(
        chunks,
        batch_size=1,
    )
    assert result["summary"]["input_chunks"] == 2
    assert result["summary"]["embedded_chunks"] == 2
    assert result["summary"]["dimensions"] == 3


def test_embedding_engine_provenance(chunks):
    result = EmbeddingEngine(FakeProvider()).embed_chunks(chunks)
    record = result["embeddings"][0]
    assert record["chunk_id"] == "chunk-1"
    assert record["source"]["source_id"] == "source-1"
    assert record["source_content_sha256"] == "source-hash"
    assert len(record["input_sha256"]) == 64


def test_embedding_engine_does_not_modify_chunks(chunks):
    import copy
    original = copy.deepcopy(chunks)
    EmbeddingEngine(FakeProvider()).embed_chunks(chunks)
    assert chunks == original


def test_empty_chunk_collection():
    result = EmbeddingEngine(FakeProvider()).embed_chunks([])
    assert result["summary"]["embedded_chunks"] == 0


def test_invalid_batch_size(chunks):
    with pytest.raises(EmbeddingError):
        EmbeddingEngine(FakeProvider()).embed_chunks(chunks, batch_size=0)


def test_invalid_chunk(chunks):
    chunks[0].pop("chunk_id")
    with pytest.raises(EmbeddingError):
        EmbeddingEngine(FakeProvider()).embed_chunks(chunks)


def test_duplicate_chunk_ids():
    records = [
        {
            "chunk_id": "same",
            "embedding": [1.0, 2.0],
            "input_sha256": "hash",
            "provider": {},
        },
        {
            "chunk_id": "same",
            "embedding": [2.0, 3.0],
            "input_sha256": "hash2",
            "provider": {},
        },
    ]
    assert not validate_embedding_records(records)["valid"]


def test_inconsistent_record_dimensions():
    records = [
        {
            "chunk_id": "a",
            "embedding": [1.0, 2.0],
            "input_sha256": "hash",
            "provider": {},
        },
        {
            "chunk_id": "b",
            "embedding": [1.0, 2.0, 3.0],
            "input_sha256": "hash2",
            "provider": {},
        },
    ]
    assert not validate_embedding_records(records)["valid"]


def test_provider_is_not_interchangeable():
    hf = HuggingFaceEmbeddingAdapter("hf-model", model=FakeHFModel())
    ollama = OllamaEmbeddingAdapter(
        "ollama-model",
        session=FakeSession({"embeddings": [[1.0, 2.0, 3.0]]}),
    )
    assert hf.metadata["provider"] != ollama.metadata["provider"]
    assert hf.metadata["model"] != ollama.metadata["model"]
