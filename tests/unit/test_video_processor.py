import json
from pathlib import Path

import pytest

from apps.api.app.multimodal import video_processor as vp


def test_rejects_missing_file(tmp_path):
    with pytest.raises(vp.VideoValidationError):
        vp.validate_video(tmp_path / "missing.mp4")


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("not a video")
    with pytest.raises(vp.VideoValidationError):
        vp.validate_video(path)


def test_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.mp4"
    path.write_bytes(b"")
    with pytest.raises(vp.VideoValidationError):
        vp.validate_video(path)


def test_rejects_invalid_frame_interval(tmp_path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"placeholder")
    with pytest.raises(ValueError):
        vp.analyze_video(path, tmp_path / "out", frame_interval_seconds=0)


def test_rejects_excessive_frame_limit(tmp_path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"placeholder")
    with pytest.raises(ValueError):
        vp.analyze_video(path, tmp_path / "out", max_frames=1001)


def test_validate_video_metadata(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(vp, "_require_tools", lambda: None)
    monkeypatch.setattr(vp, "_probe", lambda _: {
        "format": {"format_name": "mov,mp4", "duration": "12.5"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        ],
    })

    result = vp.validate_video(path)
    assert result["valid"] is True
    assert result["duration_seconds"] == 12.5
    assert result["video_stream_count"] == 1
    assert result["audio_stream_count"] == 1


def test_validate_rejects_no_video_stream(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(vp, "_require_tools", lambda: None)
    monkeypatch.setattr(vp, "_probe", lambda _: {
        "format": {"duration": "2"},
        "streams": [{"codec_type": "audio"}],
    })

    with pytest.raises(vp.VideoValidationError):
        vp.validate_video(path)


def test_checksum_mismatch_rejected(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(vp, "_require_tools", lambda: None)
    monkeypatch.setattr(vp, "_probe", lambda _: {
        "format": {"duration": "2"},
        "streams": [{"codec_type": "video"}],
    })

    with pytest.raises(vp.VideoValidationError):
        vp.analyze_video(
            path, tmp_path / "out",
            source_identity={"checksum_sha256": "incorrect"},
        )


def test_analyze_video_generates_traceable_frames(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(vp, "validate_video", lambda _: {
        "valid": True,
        "extension": ".mp4",
        "size_bytes": 5,
        "duration_seconds": 10.0,
        "format": "mp4",
        "video_stream_count": 1,
        "audio_stream_count": 1,
        "streams": [
            {"index": 0, "codec_type": "video", "start_time": "0"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        ],
        "format_metadata": {"start_time": "0"},
    })

    def fake_extract(video, frame_dir, interval, limit):
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame = frame_dir / "frame_000001.jpg"
        frame.write_bytes(b"test-frame")
        return [frame]

    monkeypatch.setattr(vp, "_extract_frames", fake_extract)

    result = vp.analyze_video(
        path, tmp_path / "output",
        frame_interval_seconds=5,
    )

    assert result["status"] == "completed"
    assert result["frame_extraction"]["frame_count"] == 1
    frame = result["frame_extraction"]["frames"][0]
    assert frame["timestamp_seconds"] == 0
    assert len(frame["checksum_sha256"]) == 64
    assert Path(result["report_path"]).exists()

    saved = json.loads(Path(result["report_path"]).read_text())
    assert saved["source"]["checksum_sha256"] == result["source"]["checksum_sha256"]
