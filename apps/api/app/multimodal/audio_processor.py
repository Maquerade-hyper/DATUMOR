"""Audio validation, metadata extraction, transcription and provenance."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil
import subprocess
import wave


REPORT_TYPE = "datumor.audio_analysis"
REPORT_VERSION = "1.0.0"

SUPPORTED_FORMATS = {
    "wav", "mp3", "flac", "ogg", "opus", "m4a", "aac", "wma", "aiff"
}

DEFAULT_MAX_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_DURATION_SECONDS = 6 * 60 * 60


class AudioValidationError(ValueError):
    """Raised when an audio file is invalid or exceeds configured limits."""


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_ffprobe(path: Path) -> dict:
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError(
            "FFprobe is required for this audio format. "
            "Install FFmpeg and make ffprobe available on PATH."
        )

    command = [
        executable,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    if completed.returncode != 0:
        raise AudioValidationError(
            f"FFprobe rejected audio file: {completed.stderr.strip()}"
        )

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AudioValidationError("FFprobe returned invalid JSON") from exc


def _wav_metadata(path: Path) -> dict:
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_rate = audio.getframerate()
            frames = audio.getnframes()
            sample_width = audio.getsampwidth()
            compression = audio.getcomptype()
            duration = frames / sample_rate if sample_rate else 0

            return {
                "format": "wav",
                "codec": "pcm",
                "channels": channels,
                "sample_rate_hz": sample_rate,
                "duration_seconds": duration,
                "frame_count": frames,
                "sample_width_bytes": sample_width,
                "bit_rate_bps": sample_rate * channels * sample_width * 8,
                "compression": compression,
            }
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioValidationError(f"Invalid WAV file: {exc}") from exc


def _extract_probe_metadata(probe: dict) -> dict:
    streams = probe.get("streams", [])
    audio_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    if not audio_streams:
        raise AudioValidationError("File contains no audio stream")

    stream = audio_streams[0]
    format_info = probe.get("format", {})

    duration = stream.get("duration") or format_info.get("duration")
    try:
        duration = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration = None

    sample_rate = stream.get("sample_rate")
    channels = stream.get("channels")
    bit_rate = stream.get("bit_rate") or format_info.get("bit_rate")

    return {
        "format": (
            format_info.get("format_name", "unknown").split(",")[0].lower()
        ),
        "codec": stream.get("codec_name"),
        "channels": int(channels) if channels is not None else None,
        "sample_rate_hz": (
            int(sample_rate) if sample_rate is not None else None
        ),
        "duration_seconds": duration,
        "bit_rate_bps": int(bit_rate) if bit_rate is not None else None,
        "channel_layout": stream.get("channel_layout"),
        "sample_format": stream.get("sample_fmt"),
        "bits_per_sample": stream.get("bits_per_sample"),
    }


def validate_audio(
    audio_path: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
) -> dict:
    path = Path(audio_path)

    if not path.is_file():
        raise AudioValidationError(f"Audio file does not exist: {path}")

    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise AudioValidationError("Audio file is empty")

    if size_bytes > max_bytes:
        raise AudioValidationError(
            f"Audio exceeds maximum size of {max_bytes} bytes"
        )

    extension = path.suffix.lower().lstrip(".")
    if extension not in SUPPORTED_FORMATS:
        raise AudioValidationError(f"Unsupported audio extension: {extension}")

    if extension == "wav":
        metadata = _wav_metadata(path)
        # If FFprobe exists, also inspect the container and codec.
        if shutil.which("ffprobe"):
            try:
                probe_metadata = _extract_probe_metadata(_run_ffprobe(path))
                metadata.update({
                    "format": probe_metadata["format"],
                    "codec": probe_metadata["codec"],
                    "channel_layout": probe_metadata["channel_layout"],
                })
            except AudioValidationError:
                raise
            except Exception:
                pass
    else:
        metadata = _extract_probe_metadata(_run_ffprobe(path))

    duration = metadata.get("duration_seconds")
    if duration is None or duration <= 0:
        raise AudioValidationError("Audio duration is missing or invalid")

    if duration > max_duration_seconds:
        raise AudioValidationError(
            f"Audio exceeds maximum duration of {max_duration_seconds} seconds"
        )

    return {
        "valid": True,
        "extension": extension,
        "size_bytes": size_bytes,
        **metadata,
    }


class FasterWhisperAdapter:
    """Optional faster-whisper transcription adapter."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Install it to enable transcription."
            ) from exc

        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: str | Path) -> dict:
        segments, info = self.model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            word_timestamps=True,
        )

        normalized = []

        for index, segment in enumerate(segments):
            words = []
            for word in (getattr(segment, "words", None) or []):
                words.append({
                    "text": word.word,
                    "start_seconds": float(word.start),
                    "end_seconds": float(word.end),
                    "probability": (
                        float(word.probability)
                        if word.probability is not None else None
                    ),
                })

            normalized.append({
                "segment_id": f"segment-{index + 1:06d}",
                "start_seconds": float(segment.start),
                "end_seconds": float(segment.end),
                "text": str(segment.text).strip(),
                "confidence": (
                    float(segment.avg_logprob)
                    if segment.avg_logprob is not None else None
                ),
                "no_speech_probability": (
                    float(segment.no_speech_prob)
                    if segment.no_speech_prob is not None else None
                ),
                "speaker_id": None,
                "words": words,
                "evidence_method": "faster_whisper",
            })

        return {
            "language": getattr(info, "language", None),
            "language_probability": getattr(
                info, "language_probability", None
            ),
            "duration_seconds": getattr(info, "duration", None),
            "segments": normalized,
            "engine": "faster-whisper",
            "model_size": self.model_size,
        }


def _normalize_transcription(raw: dict, duration: float) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Transcription adapter must return a dictionary")

    segments = raw.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError("Transcription segments must be a list")

    normalized = []
    full_text = []

    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise ValueError("Each transcription segment must be an object")

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        start = float(item["start_seconds"])
        end = float(item["end_seconds"])

        if start < 0 or end < start or end > duration + 0.5:
            raise ValueError("Transcription segment has invalid timestamps")

        speaker_id = item.get("speaker_id")
        if speaker_id is not None:
            speaker_id = str(speaker_id)

        normalized.append({
            "segment_id": str(
                item.get("segment_id") or f"segment-{index + 1:06d}"
            ),
            "start_seconds": start,
            "end_seconds": end,
            "text": text,
            "confidence": item.get("confidence"),
            "speaker_id": speaker_id,
            "words": item.get("words", []),
            "evidence_method": item.get(
                "evidence_method", "transcription_adapter"
            ),
        })
        full_text.append(text)

    return {
        "language": raw.get("language"),
        "language_probability": raw.get("language_probability"),
        "engine": raw.get("engine", "custom_adapter"),
        "model_size": raw.get("model_size"),
        "segments": normalized,
        "text": " ".join(full_text),
        "segment_count": len(normalized),
    }


def analyze_audio(
    audio_path: str | Path,
    source_identity: dict | None = None,
    transcription_engine=None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
) -> dict:
    """Validate audio, extract metadata, optionally transcribe, and preserve provenance."""

    path = Path(audio_path)
    metadata = validate_audio(
        path,
        max_bytes=max_bytes,
        max_duration_seconds=max_duration_seconds,
    )
    checksum = _sha256(path)

    source = {
        "source_id": None,
        "source_name": path.name,
        "checksum_sha256": checksum,
        "size_bytes": metadata["size_bytes"],
        "media_type": f"audio/{metadata['extension']}",
    }

    if source_identity is not None:
        if not isinstance(source_identity, dict):
            raise TypeError("source_identity must be a dictionary")

        supplied_checksum = source_identity.get("checksum_sha256")
        if supplied_checksum and supplied_checksum != checksum:
            raise ValueError("Source identity checksum does not match audio")

        source["source_id"] = source_identity.get("source_id")
        source["source_name"] = (
            source_identity.get("source_name") or source["source_name"]
        )

    transcription_status = "not_configured"
    transcription = {
        "language": None,
        "language_probability": None,
        "engine": None,
        "model_size": None,
        "segments": [],
        "text": "",
        "segment_count": 0,
    }
    warnings_list = []

    if transcription_engine is not None:
        try:
            if hasattr(transcription_engine, "transcribe"):
                raw = transcription_engine.transcribe(path)
            elif callable(transcription_engine):
                raw = transcription_engine(path)
            else:
                raise TypeError(
                    "transcription_engine must be callable or expose transcribe()"
                )

            transcription = _normalize_transcription(
                raw, metadata["duration_seconds"]
            )
            transcription_status = "completed"
        except Exception as exc:
            transcription_status = "failed"
            warnings_list.append(
                f"Transcription failed: {type(exc).__name__}: {exc}"
            )

    speaker_ids = sorted({
        segment["speaker_id"]
        for segment in transcription["segments"]
        if segment["speaker_id"] is not None
    })

    return {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "status": "completed_with_warnings" if warnings_list else "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "audio": metadata,
        "transcription": {
            "status": transcription_status,
            **transcription,
        },
        "speakers": {
            "status": (
                "identified"
                if speaker_ids else "not_available"
            ),
            "speaker_ids": speaker_ids,
            "speaker_count": len(speaker_ids),
            "diarization_performed": bool(speaker_ids),
        },
        "capabilities": {
            "audio_validation": True,
            "metadata_extraction": True,
            "speech_to_text": transcription_status == "completed",
            "segment_timestamps": bool(transcription["segments"]),
            "word_timestamps": any(
                segment["words"] for segment in transcription["segments"]
            ),
            "speaker_diarization": bool(speaker_ids),
        },
        "provenance": {
            "source_id": source["source_id"],
            "source_checksum_sha256": checksum,
            "transcription_engine": transcription["engine"],
            "transcription_segment_count": transcription["segment_count"],
        },
        "warnings": warnings_list,
    }
