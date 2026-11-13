from pathlib import Path

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from apps.api.app.optimization.tokenization_engine import (
    TokenizationEngine,
    TokenizationError,
    validate_tokenization_result,
)


@pytest.fixture
def engine(tmp_path):
    tokenizer = Tokenizer(
        WordLevel(
            vocab={
                "[UNK]": 0,
                "hello": 1,
                "world": 2,
                "print": 3,
                "(": 4,
                ")": 5,
            },
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()

    path = tmp_path / "tokenizer.json"
    tokenizer.save(str(path))

    return TokenizationEngine.load(tokenizer_json=path)


def test_load_local_tokenizer(engine):
    assert engine.identity["source_type"] == "local"
    assert engine.identity["vocabulary_size"] == 6
    assert len(engine.identity["fingerprint_sha256"]) == 64


def test_count_text(engine):
    result = engine.count_text("hello world", add_special_tokens=False)
    assert result["token_count"] == 2
    assert result["content_type"] == "text"


def test_count_code(engine):
    result = engine.count_text(
        "print ( hello )",
        content_type="code",
        add_special_tokens=False,
    )
    assert result["token_count"] == 4
    assert result["content_type"] == "code"


def test_context_overflow(engine):
    result = engine.count_text(
        "hello world",
        add_special_tokens=False,
        max_context_tokens=1,
    )
    assert result["context_overflow"] is True
    assert result["context_usage_ratio"] == 2.0


def test_context_within_limit(engine):
    result = engine.count_text(
        "hello",
        add_special_tokens=False,
        max_context_tokens=10,
    )
    assert result["context_overflow"] is False
    assert result["context_usage_ratio"] == 0.1


def test_batch_statistics(engine):
    result = engine.count_batch(
        ["hello", "hello world"],
        add_special_tokens=False,
    )
    assert result["item_count"] == 2
    assert result["total_tokens"] == 3
    assert result["minimum_tokens"] == 1
    assert result["maximum_tokens"] == 2
    assert result["average_tokens"] == 1.5


def test_empty_batch(engine):
    result = engine.count_batch([])
    assert result["item_count"] == 0
    assert result["total_tokens"] == 0


def test_invalid_tokenizer_arguments():
    with pytest.raises(TokenizationError):
        TokenizationEngine.load()


def test_missing_local_tokenizer():
    with pytest.raises(TokenizationError):
        TokenizationEngine.load(
            tokenizer_json=Path("missing-tokenizer.json")
        )


def test_invalid_text(engine):
    with pytest.raises(TokenizationError):
        engine.count_text(123)


def test_invalid_content_type(engine):
    with pytest.raises(TokenizationError):
        engine.count_text("hello", content_type="image")


def test_invalid_context_limit(engine):
    with pytest.raises(TokenizationError):
        engine.count_text("hello", max_context_tokens=0)


def test_result_validation(engine):
    result = engine.count_text("hello")
    validate_tokenization_result(result)


def test_invalid_result_validation():
    with pytest.raises(TokenizationError):
        validate_tokenization_result({"token_count": -1})


def test_reproducible_fingerprint(engine, tmp_path):
    tokenizer_path = tmp_path / "same.json"
    Tokenizer(
        WordLevel(
            vocab={"[UNK]": 0, "hello": 1},
            unk_token="[UNK]",
        )
    ).save(str(tokenizer_path))

    first = TokenizationEngine.load(tokenizer_json=tokenizer_path)
    second = TokenizationEngine.load(tokenizer_json=tokenizer_path)

    assert (
        first.identity["fingerprint_sha256"]
        == second.identity["fingerprint_sha256"]
    )


def test_metadata(engine):
    metadata = engine.metadata()
    assert metadata["counting_mode"] == "exact_tokenizer_encoding"
    assert metadata["supports_batch_processing"] is True
