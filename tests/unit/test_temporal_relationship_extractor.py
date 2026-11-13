import pytest

from apps.api.app.multimodal.temporal_relationship_extractor import (
    TemporalValidationError,
    extract_temporal_relationships,
    validate_temporal_report,
    export_temporal_report,
)


def make_video():
    return {
        "source": {"source_id": "video-source"},
        "video": {"duration_seconds": 10.0},
        "frame_extraction": {
            "frames": [
                {
                    "frame_id": "frame-1",
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "filename": "frame_000001.jpg",
                    "checksum_sha256": "a" * 64,
                    "extraction_method": "ffmpeg_fps",
                },
                {
                    "frame_id": "frame-2",
                    "frame_index": 1,
                    "timestamp_seconds": 5.0,
                    "filename": "frame_000002.jpg",
                    "checksum_sha256": "b" * 64,
                    "extraction_method": "ffmpeg_fps",
                },
            ]
        },
    }


def make_audio():
    return {
        "source": {"source_id": "audio-source"},
        "audio": {"duration_seconds": 10.0},
        "transcription": {
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_seconds": 1.0,
                    "end_seconds": 3.0,
                    "text": "Hello there.",
                    "speaker_id": None,
                    "words": [
                        {
                            "text": " Hello",
                            "start_seconds": 1.0,
                            "end_seconds": 1.5,
                            "probability": 0.99,
                        },
                        {
                            "text": " there.",
                            "start_seconds": 1.5,
                            "end_seconds": 2.0,
                            "probability": 0.98,
                        },
                    ],
                }
            ]
        },
    }


def test_extracts_video_and_audio_events():
    report = extract_temporal_relationships(make_video(), make_audio())
    summary = report["summary"]

    assert summary["video_frame_events"] == 2
    assert summary["speech_segment_events"] == 1
    assert summary["speech_word_events"] == 2
    assert report["timeline"]["event_count"] == 5


def test_events_are_chronologically_ordered():
    report = extract_temporal_relationships(make_video(), make_audio())
    events = report["timeline"]["events"]

    keys = [
        (e["start_seconds"], e["end_seconds"], e["modality"], e["event_id"])
        for e in events
    ]
    assert keys == sorted(keys)


def test_cross_modal_alignment_is_extracted():
    report = extract_temporal_relationships(
        make_video(),
        make_audio(),
        alignment_tolerance_seconds=2,
    )
    alignments = [
        r for r in report["timeline"]["relationships"]
        if r["predicate"] == "temporally_aligned"
    ]

    assert len(alignments) == 1
    assert alignments[0]["method"] == "nearest_frame_midpoint"
    assert alignments[0]["relationship_origin"] == "inferred"


def test_relationships_reference_existing_events():
    report = extract_temporal_relationships(make_video(), make_audio())
    assert validate_temporal_report(report)["valid"]


def test_preserves_observed_timestamp_origin():
    report = extract_temporal_relationships(make_video(), make_audio())

    assert all(
        event["timestamp_origin"] == "observed"
        for event in report["timeline"]["events"]
    )
    assert all(
        relation["relationship_origin"] == "inferred"
        for relation in report["timeline"]["relationships"]
    )


def test_rejects_negative_tolerance():
    with pytest.raises(ValueError):
        extract_temporal_relationships(
            make_video(), make_audio(),
            alignment_tolerance_seconds=-1,
        )


def test_rejects_event_outside_media_duration():
    audio = make_audio()
    audio["transcription"]["segments"][0]["end_seconds"] = 12

    with pytest.raises(TemporalValidationError):
        extract_temporal_relationships(make_video(), audio)


def test_rejects_invalid_segment_interval():
    audio = make_audio()
    audio["transcription"]["segments"][0]["start_seconds"] = 4
    audio["transcription"]["segments"][0]["end_seconds"] = 2

    with pytest.raises(TemporalValidationError):
        extract_temporal_relationships(make_video(), audio)


def test_rejects_unknown_relationship_reference():
    report = extract_temporal_relationships(make_video(), make_audio())
    report["timeline"]["relationships"][0]["target_event_id"] = "missing"

    with pytest.raises(TemporalValidationError):
        validate_temporal_report(report)


def test_export_creates_valid_report(tmp_path):
    report = extract_temporal_relationships(make_video(), make_audio())
    result = export_temporal_report(report, tmp_path)

    assert result["status"] == "completed"
    assert result["event_count"] == 5
    assert (tmp_path / "temporal_analysis.json").exists()


def test_video_only_input():
    report = extract_temporal_relationships(video_analysis=make_video())

    assert report["summary"]["video_frame_events"] == 2
    assert report["summary"]["speech_segment_events"] == 0
    assert report["capabilities"]["cross_modal_alignment"] is False


def test_audio_only_input():
    report = extract_temporal_relationships(audio_analysis=make_audio())

    assert report["summary"]["speech_segment_events"] == 1
    assert report["summary"]["speech_word_events"] == 2
    assert report["capabilities"]["cross_modal_alignment"] is False


def test_stable_event_ids():
    first = extract_temporal_relationships(make_video(), make_audio())
    second = extract_temporal_relationships(make_video(), make_audio())

    assert [
        e["event_id"] for e in first["timeline"]["events"]
    ] == [
        e["event_id"] for e in second["timeline"]["events"]
    ]


def test_near_simultaneous_relationship():
    video = make_video()
    audio = make_audio()
    audio["transcription"]["segments"][0]["start_seconds"] = 0.1
    audio["transcription"]["segments"][0]["end_seconds"] = 0.2

    report = extract_temporal_relationships(
        video, audio, near_simultaneous_tolerance_seconds=0.25
    )

    predicates = [
        r["predicate"] for r in report["timeline"]["relationships"]
    ]
    assert "overlaps" in predicates or "near_simultaneous" in predicates
