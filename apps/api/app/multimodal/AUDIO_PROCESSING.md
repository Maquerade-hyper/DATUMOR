# M6.2 ? Audio Processing

## Public functions

- `validate_audio(audio_path, max_bytes=500MiB, max_duration_seconds=6h)`
- `analyze_audio(audio_path, source_identity=None, transcription_engine=None)`

## Supported extensions

WAV, MP3, FLAC, OGG, OPUS, M4A, AAC, WMA, and AIFF.

WAV metadata can be extracted with the Python standard library.
Other formats require FFprobe.

## Metadata

- Format and codec
- Channel count and layout
- Sample rate
- Duration
- Bit rate
- Sample format and bit depth when available
- File size and SHA-256

## Transcription

`FasterWhisperAdapter` provides an optional faster-whisper implementation.
Its default configuration uses CPU and int8 compute.

The adapter returns:
- Detected language and confidence
- Segment text and timestamps
- Optional word timestamps
- Model identity

Model downloads may be required on first use.

## Speakers

Speaker IDs are retained only when provided by a transcription or
diarization adapter. faster-whisper alone does not establish speaker identity.
No speaker identity is invented.

## Limitations

This step does not perform speaker diarization by itself, emotion recognition,
music understanding, sound-event classification, or source separation.

## Provenance and safety

- Original audio is read-only.
- SHA-256 is calculated from original file bytes.
- Supplied source checksums are verified.
- Transcription failures do not discard successfully extracted metadata.
