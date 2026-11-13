"""Video validation, stream inspection, frame extraction and provenance."""

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpeg", ".mpg"
}


class VideoValidationError(ValueError):
    """Raised when a video file is invalid or unsupported."""


def _run(command, timeout=300):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoValidationError(f"Command execution failed: {exc}") from exc

    if result.returncode != 0:
        raise VideoValidationError(
            result.stderr.strip() or "External media command failed."
        )
    return result


def _require_tools():
    missing = [tool for tool in ("ffprobe", "ffmpeg") if not shutil.which(tool)]
    if missing:
        raise VideoValidationError(
            f"Required executable(s) not found on PATH: {', '.join(missing)}"
        )


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path):
    result = _run([
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=format_name,duration,size,bit_rate,start_time:"
        "stream=index,codec_type,codec_name,profile,width,height,"
        "pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,"
        "channel_layout,bit_rate,duration,start_time",
        "-of", "json",
        str(path),
    ])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoValidationError("FFprobe returned invalid JSON.") from exc


def validate_video(video_path, max_bytes=2 * 1024**3,
                   max_duration_seconds=24 * 60 * 60):
    path = Path(video_path)

    if not path.is_file():
        raise VideoValidationError("Video file does not exist.")
    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise VideoValidationError("Unsupported video extension.")

    size = path.stat().st_size
    if size <= 0:
        raise VideoValidationError("Video file is empty.")
    if size > max_bytes:
        raise VideoValidationError("Video exceeds the configured size limit.")

    _require_tools()
    probe = _probe(path)
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    if not video_streams:
        raise VideoValidationError("No video stream was detected.")

    raw_duration = (
        probe.get("format", {}).get("duration")
        or video_streams[0].get("duration")
    )
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise VideoValidationError("Video duration is missing or invalid.") from exc

    if duration <= 0 or duration > max_duration_seconds:
        raise VideoValidationError("Video duration is outside allowed limits.")

    return {
        "valid": True,
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": size,
        "duration_seconds": duration,
        "format": probe.get("format", {}).get("format_name"),
        "video_stream_count": len(video_streams),
        "audio_stream_count": sum(
            s.get("codec_type") == "audio" for s in streams
        ),
        "streams": streams,
        "format_metadata": probe.get("format", {}),
    }


def _extract_frames(video_path, frame_dir, interval, max_frames):
    frame_dir.mkdir(parents=True, exist_ok=True)
    pattern = frame_dir / "frame_%06d.jpg"

    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-map", "0:v:0",
        "-vf", f"fps=1/{interval}",
        "-frames:v", str(max_frames),
        "-q:v", "2",
        "-an",
        str(pattern),
    ])

    return sorted(frame_dir.glob("frame_*.jpg"))


def analyze_video(
    video_path,
    output_directory,
    source_identity=None,
    frame_interval_seconds=5.0,
    max_frames=100,
    extract_audio=False,
):
    """Analyze a video and produce traceable frame and stream metadata."""

    if frame_interval_seconds <= 0:
        raise ValueError("frame_interval_seconds must be positive.")
    if max_frames < 1 or max_frames > 1000:
        raise ValueError("max_frames must be between 1 and 1000.")

    path = Path(video_path)
    metadata = validate_video(path)
    checksum = _sha256(path)

    if source_identity and source_identity.get("checksum_sha256"):
        if source_identity["checksum_sha256"] != checksum:
            raise VideoValidationError("Source identity checksum mismatch.")

    output = Path(output_directory)
    frame_dir = output / "frames"
    output.mkdir(parents=True, exist_ok=True)

    warnings = []
    frame_records = []
    audio_output = None

    try:
        extracted = _extract_frames(
            path, frame_dir, frame_interval_seconds, max_frames
        )
        start_time = float(
            metadata["format_metadata"].get("start_time")
            or next(
                (s.get("start_time") for s in metadata["streams"]
                 if s.get("codec_type") == "video"
                 and s.get("start_time") is not None),
                0,
            )
        )

        for index, frame_path in enumerate(extracted):
            frame_records.append({
                "frame_id": f"frame-{index + 1:06d}",
                "frame_index": index,
                "timestamp_seconds": round(
                    start_time + index * frame_interval_seconds, 6
                ),
                "filename": frame_path.name,
                "path": str(frame_path.resolve()),
                "size_bytes": frame_path.stat().st_size,
                "checksum_sha256": _sha256(frame_path),
                "extraction_method": "ffmpeg_fps",
            })

        if not frame_records:
            warnings.append("No frames were extracted.")
    except VideoValidationError as exc:
        warnings.append(f"Frame extraction failed: {exc}")

    audio_streams = [
        stream for stream in metadata["streams"]
        if stream.get("codec_type") == "audio"
    ]

    if extract_audio:
        if audio_streams:
            audio_output = output / "audio_track.wav"
            try:
                _run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(path),
                    "-map", "0:a:0",
                    "-vn", "-acodec", "pcm_s16le",
                    str(audio_output),
                ])
            except VideoValidationError as exc:
                warnings.append(f"Audio extraction failed: {exc}")
                audio_output = None
        else:
            warnings.append("Audio extraction requested but no audio stream exists.")

    result = {
        "report_type": "datumor.video_analysis",
        "version": "1.0.0",
        "status": "completed_with_warnings" if warnings else "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "source_id": (source_identity or {}).get("source_id"),
            "source_name": path.name,
            "checksum_sha256": checksum,
            "size_bytes": path.stat().st_size,
            "media_type": "video",
        },
        "video": {
            key: metadata[key]
            for key in (
                "valid", "extension", "size_bytes", "duration_seconds",
                "format", "video_stream_count", "audio_stream_count",
            )
        },
        "streams": metadata["streams"],
        "frame_extraction": {
            "method": "ffmpeg_fps",
            "interval_seconds": frame_interval_seconds,
            "frame_count": len(frame_records),
            "frames": frame_records,
        },
        "audio": {
            "present": bool(audio_streams),
            "stream_count": len(audio_streams),
            "streams": audio_streams,
            "extracted_path": (
                str(audio_output.resolve())
                if audio_output and audio_output.exists() else None
            ),
            "transcription_performed": False,
        },
        "provenance": {
            "source_id": (source_identity or {}).get("source_id"),
            "source_checksum_sha256": checksum,
            "frame_checksums_included": True,
        },
        "capabilities": {
            "video_validation": True,
            "stream_inspection": True,
            "frame_extraction": len(frame_records) > 0,
            "frame_timestamps": len(frame_records) > 0,
            "audio_track_detection": True,
            "audio_track_extraction": bool(audio_output and audio_output.exists()),
            "object_recognition": False,
            "video_captioning": False,
            "transcription": False,
        },
        "warnings": warnings,
    }

    report_path = output / "video_analysis.json"
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    result["report_path"] = str(report_path.resolve())
    return result
