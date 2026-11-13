from pathlib import Path
import wave

import pytest

from apps.api.app.multimodal.audio_processor import (
    AudioValidationError,
    analyze_audio,
    validate_audio,
)


def create_wav(path: Path, duration=1, sample_rate=16000):
    frames = b"\x00\x00" * sample_rate * duration
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(frames)
    return path


def fake_transcription(_path):
    return {
        "language": "en",
        "language_probability": 0.99,
        "engine": "test-engine",
        "segments": [{
            "segment_id": "segment-1",
            "start_seconds": 0.1,
            "end_seconds": 0.8,
            "text": "DATUMOR audio test",
            "confidence": -0.1,
            "speaker_id": "speaker-1",
            "words": [{
                "text": "DATUMOR",
                "start_seconds": 0.1,
                "end_seconds": 0.4,
                "probability": 0.95,
            }],
        }],
    }


def test_valid_wav_metadata(tmp_path):
    path = create_wav(tmp_path / "sample.wav")
    result = validate_audio(path)

    assert result["valid"] is True
    assert result["format"] == "wav"
    assert result["channels"] == 1
    assert result["sample_rate_hz"] == 16000
    assert result["duration_seconds"] == 1


def test_audio_analysis_without_transcription(tmp_path):
    path = create_wav(tmp_path / "sample.wav")
    result = analyze_audio(path)

    assert result["report_type"] == "datumor.audio_analysis"
    assert result["status"] == "completed"
    assert result["source"]["checksum_sha256"]
    assert result["transcription"]["status"] == "not_configured"
    assert result["speakers"]["status"] == "not_available"


def test_transcription_segments_and_speakers(tmp_path):
    path = create_wav(tmp_path / "sample.wav")
    result = analyze_audio(path, transcription_engine=fake_transcription)

    assert result["transcription"]["status"] == "completed"
    assert result["transcription"]["text"] == "DATUMOR audio test"
    assert result["transcription"]["segment_count"] == 1
    assert result["transcription"]["segments"][0]["start_seconds"] == 0.1
    assert result["transcription"]["segments"][0]["speaker_id"] == "speaker-1"
    assert result["speakers"]["speaker_ids"] == ["speaker-1"]
    assert result["capabilities"]["word_timestamps"] is True


def test_source_identity_is_preserved(tmp_path):
    path = create_wav(tmp_path / "sample.wav")
    initial = analyze_audio(path)

    result = analyze_audio(
        path,
        source_identity={
            "source_id": "audio-source-1",
            "source_name": "registered.wav",
            "checksum_sha256": initial["source"]["checksum_sha256"],
        },
    )

    assert result["source"]["source_id"] == "audio-source-1"
    assert result["source"]["source_name"] == "registered.wav"


def test_checksum_mismatch_is_rejected(tmp_path):
    path = create_wav(tmp_path / "sample.wav")

    with pytest.raises(ValueError, match="checksum"):
        analyze_audio(
            path,
            source_identity={"checksum_sha256": "wrong"},
        )


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(AudioValidationError, match="does not exist"):
        validate_audio(tmp_path / "missing.wav")


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")

    with pytest.raises(AudioValidationError, match="empty"):
        validate_audio(path)


def test_corrupt_wav_is_rejected(tmp_path):
    path = tmp_path / "corrupt.wav"
    path.write_bytes(b"not-a-wav")

    with pytest.raises(AudioValidationError, match="Invalid WAV"):
        validate_audio(path)


def test_size_limit_is_enforced(tmp_path):
    path = create_wav(tmp_path / "sample.wav")

    with pytest.raises(AudioValidationError, match="maximum size"):
        validate_audio(path, max_bytes=10)


def test_duration_limit_is_enforced(tmp_path):
    path = create_wav(tmp_path / "sample.wav", duration=2)

    with pytest.raises(AudioValidationError, match="maximum duration"):
        validate_audio(path, max_duration_seconds=1)


def test_unsupported_extension_is_rejected(tmp_path):
    path = tmp_path / "sample.xyz"
    path.write_bytes(b"audio")

    with pytest.raises(AudioValidationError, match="Unsupported"):
        validate_audio(path)


def test_transcription_failure_preserves_metadata(tmp_path):
    path = create_wav(tmp_path / "sample.wav")

    def failing_engine(_path):
        raise RuntimeError("model unavailable")

    result = analyze_audio(path, transcription_engine=failing_engine)

    assert result["status"] == "completed_with_warnings"
    assert result["audio"]["format"] == "wav"
    assert result["transcription"]["status"] == "failed"
    assert result["warnings"]


def test_invalid_transcription_timestamps_are_rejected(tmp_path):
    path = create_wav(tmp_path / "sample.wav")

    def invalid_engine(_path):
        return {
            "segments": [{
                "start_seconds": 0.9,
                "end_seconds": 2.0,
                "text": "Invalid timestamp",
            }]
        }

    result = analyze_audio(path, transcription_engine=invalid_engine)

    assert result["transcription"]["status"] == "failed"
    assert "timestamps" in result["warnings"][0]


def test_speaker_identity_is_not_invented(tmp_path):
    path = create_wav(tmp_path / "sample.wav")

    def no_speaker_engine(_path):
        return {
            "language": "en",
            "segments": [{
                "start_seconds": 0,
                "end_seconds": 0.5,
                "text": "Hello",
            }],
        }

    result = analyze_audio(path, transcription_engine=no_speaker_engine)

    assert result["speakers"]["status"] == "not_available"
    assert result["speakers"]["speaker_count"] == 0


def test_word_timestamps_are_preserved(tmp_path):
    path = create_wav(tmp_path / "sample.wav")
    result = analyze_audio(path, transcription_engine=fake_transcription)

    word = result["transcription"]["segments"][0]["words"][0]
    assert word["text"] == "DATUMOR"
    assert word["start_seconds"] == 0.1
    assert word["end_seconds"] == 0.4
