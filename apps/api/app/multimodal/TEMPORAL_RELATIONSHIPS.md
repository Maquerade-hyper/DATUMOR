# DATUMOR Temporal Relationship Extraction

## Purpose
Build a unified chronological event timeline from M6.2 audio-analysis
and M6.3 video-analysis artifacts.

## Public APIs

- `extract_temporal_relationships(video_analysis=None, audio_analysis=None, alignment_tolerance_seconds=1.0, near_simultaneous_tolerance_seconds=0.25)`
- `validate_temporal_report(report)`
- `export_temporal_report(report, output_directory)`

Inputs can be dictionaries or paths to JSON artifacts.

## Event types

- `video_frame`
- `speech_segment`
- `speech_word`

## Temporal predicates

- `before`
- `after`
- `overlaps`
- `contains`
- `during`
- `coincident`
- `near_simultaneous`
- `temporally_aligned`

## Timestamp policy

Source frame and speech timestamps are retained as observed values.
Temporal relationships and cross-modal alignment are inferred from
interval comparisons and nearest-frame midpoint calculations.

## Limitations

- Frame timestamps represent extracted sample times, not semantic events.
- Nearest-frame alignment does not prove that the frame depicts the spoken content.
- No object recognition, scene understanding, speaker identification,
  semantic event detection, or causal inference is performed.
- Alignment accuracy depends on source timestamp quality and extraction intervals.

## Output

The JSON report contains ordered events, temporal relationships,
source provenance, summary counts, capability declarations, and validation.
