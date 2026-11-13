# DATUMOR Video Processing

## Purpose
Validate video sources, inspect media streams, extract representative frames,
and preserve frame timestamps and SHA-256 provenance.

## Supported formats
MP4, MKV, MOV, AVI, WEBM, M4V, MPEG and MPG.

## Requirements
- FFmpeg
- FFprobe
- Python standard library

Both FFmpeg executables must be available on PATH.

## Public API

`validate_video(video_path, max_bytes, max_duration_seconds)`

`analyze_video(video_path, output_directory, source_identity=None,
frame_interval_seconds=5.0, max_frames=100, extract_audio=False)`

## Output
- Video metadata and stream inventory
- Frame files with extraction timestamps and SHA-256 checksums
- Audio stream metadata
- Optional first audio-track extraction to WAV
- Source provenance and structured JSON report

## Boundaries
This step does not perform object recognition, scene understanding,
video captioning, speech transcription, or speaker diarization.
Extracted audio is not automatically transcribed. M6.2 remains the
independent audio-processing capability.

Frame timestamps are sampling timestamps derived from the video start time
and configured extraction interval. They are not a claim of per-frame
original presentation timestamps.
