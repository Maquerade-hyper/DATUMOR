import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from apps.api.app.optimization.tokenization_engine import TokenizationEngine
from apps.api.app.optimization.intelligent_chunker import (
    ChunkingError,
    IntelligentChunker,
    validate_chunk_result,
)


@pytest.fixture
def chunker(tmp_path):
    tokenizer = Tokenizer(
        WordLevel(
            vocab={
                "[UNK]": 0,
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
                "nine": 9,
                "ten": 10,
                "alpha": 11,
                "beta": 12,
                "gamma": 13,
                "delta": 14,
                "epsilon": 15,
            },
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    path = tmp_path / "tokenizer.json"
    tokenizer.save(str(path))
    return IntelligentChunker(
        TokenizationEngine.load(tokenizer_json=path)
    )


def test_chunk_size_limit(chunker):
    result = chunker.chunk_text(
        "one two three four five six seven eight",
        chunk_size=3,
        overlap=0,
    )
    assert all(chunk["token_count"] <= 3 for chunk in result["chunks"])


def test_source_coverage(chunker):
    text = "one two three four five six"
    result = chunker.chunk_text(text, chunk_size=2, overlap=0)
    reconstructed = "".join(
        text[c["start_char"]:c["end_char"]]
        for c in result["chunks"]
    )
    assert reconstructed == text


def test_overlap(chunker):
    result = chunker.chunk_text(
        "one two three four five six",
        chunk_size=3,
        overlap=1,
    )
    assert len(result["chunks"]) > 1
    for previous, current in zip(
        result["chunks"], result["chunks"][1:]
    ):
        assert previous["end_char"] >= current["start_char"]


def test_stable_ids(chunker):
    first = chunker.chunk_text("one two three four", chunk_size=2, overlap=0)
    second = chunker.chunk_text("one two three four", chunk_size=2, overlap=0)
    assert [c["chunk_id"] for c in first["chunks"]] == [
        c["chunk_id"] for c in second["chunks"]
    ]


def test_provenance_preserved(chunker):
    source = {
        "source_id": "source-1",
        "filename": "sample.txt",
        "checksum_sha256": "abc123",
    }
    result = chunker.chunk_text(
        "one two three",
        source=source,
        chunk_size=2,
        overlap=0,
    )
    assert all(c["source"]["source_id"] == "source-1" for c in result["chunks"])
    assert result["source"]["checksum_sha256"] == "abc123"


def test_empty_text(chunker):
    result = chunker.chunk_text("", chunk_size=10, overlap=0)
    assert result["chunks"] == []
    assert result["summary"]["chunk_count"] == 0


def test_invalid_chunk_size(chunker):
    with pytest.raises(ChunkingError):
        chunker.chunk_text("one", chunk_size=0)


def test_invalid_overlap(chunker):
    with pytest.raises(ChunkingError):
        chunker.chunk_text("one", chunk_size=3, overlap=3)


def test_invalid_content_type(chunker):
    with pytest.raises(ChunkingError):
        chunker.chunk_text("one", content_type="image")


def test_code_line_boundaries(chunker):
    result = chunker.chunk_text(
        "one two\nthree four\nfive six\n",
        content_type="code",
        chunk_size=2,
        overlap=0,
    )
    assert all(c["token_count"] <= 2 for c in result["chunks"])


def test_validation(chunker):
    result = chunker.chunk_text("one two three", chunk_size=2, overlap=0)
    assert validate_chunk_result(result)["valid"]


def test_detect_duplicate_ids(chunker):
    result = chunker.chunk_text("one two", chunk_size=1, overlap=0)
    result["chunks"][1]["chunk_id"] = result["chunks"][0]["chunk_id"]
    validation = validate_chunk_result(result)
    assert not validation["valid"]


def test_detect_broken_link(chunker):
    result = chunker.chunk_text("one two three", chunk_size=1, overlap=0)
    result["chunks"][0]["next_chunk_id"] = "invalid"
    assert not validate_chunk_result(result)["valid"]


def test_long_single_line(chunker):
    result = chunker.chunk_text(
        "one two three four five six seven eight",
        content_type="code",
        chunk_size=2,
        overlap=0,
    )
    assert all(c["token_count"] <= 2 for c in result["chunks"])


def test_source_not_modified(chunker):
    source = {"source_id": "immutable"}
    original = source.copy()
    chunker.chunk_text("one two three", source=source, chunk_size=2, overlap=0)
    assert source == original
