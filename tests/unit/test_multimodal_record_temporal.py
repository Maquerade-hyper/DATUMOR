import copy


from apps.api.app.multimodal.multimodal_record import (
    generate_multimodal_record,
    validate_multimodal_record,
)


def make_report(kind, checksum):
    return {
        "report_type": f"datumor.{kind}_analysis",
        "version": "1.0.0",
        "status": "completed",
        "created_at": "2026-11-11T12:00:00+00:00",
        "source": {
            "source_id": None,
            "source_name": f"test.{kind}",
            "checksum_sha256": checksum,
            "size_bytes": 100,
            "media_type": kind,
        },
        "capabilities": {},
        "warnings": [],
    }


def make_temporal():
    events = [
        {
            "event_id": "frame-000001",
            "event_type": "video_frame",
            "modality": "video",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
        },
        {
            "event_id": "speech-000001",
            "event_type": "speech_segment",
            "modality": "audio",
            "start_seconds": 0.2,
            "end_seconds": 1.0,
        },
    ]

    return {
        "report_type": "datumor.temporal_analysis",
        "version": "1.0.0",
        "status": "completed",
        "timeline": {
            "duration_seconds": 12.0,
            "event_count": 2,
            "relationship_count": 1,
            "events": events,
            "relationships": [{
                "relationship_id": "rel-000001",
                "source_event_id": "speech-000001",
                "target_event_id": "frame-000001",
                "predicate": "temporally_aligned",
                "relationship_origin": "inferred",
            }],
        },
    }


def build_record():
    audio = make_report("audio", "a" * 64)
    audio["source"]["source_name"] = "audio_track.wav"
    audio["audio"] = {"duration_seconds": 12.0}

    video = make_report("video", "b" * 64)
    video["source"]["source_name"] = "video.mp4"
    video["video"] = {"duration_seconds": 12.0}
    video["audio"] = {
        "present": True,
        "extracted_path": r"E:\\DATUMOR\\data\\audio_track.wav",
    }

    return generate_multimodal_record(
        audio_analysis=audio,
        video_analysis=video,
        temporal_analysis=make_temporal(),
    )


def test_valid_temporal_record():
    record = build_record()
    result = validate_multimodal_record(record)

    assert result["valid"]
    assert record["validation"]["status"] == "valid"


def test_invalid_negative_timestamp():
    record = build_record()
    record["temporal"]["timeline"]["events"][0]["start_seconds"] = -1

    assert not validate_multimodal_record(record)["valid"]


def test_invalid_timestamp_exceeds_modality_duration():
    record = build_record()
    record["temporal"]["timeline"]["events"][0]["end_seconds"] = 13

    assert not validate_multimodal_record(record)["valid"]


def test_nan_timestamp_rejected():
    record = build_record()
    record["temporal"]["timeline"]["events"][0]["start_seconds"] = float("nan")

    assert not validate_multimodal_record(record)["valid"]


def test_unresolved_relationship_rejected():
    record = build_record()
    record["temporal"]["timeline"]["relationships"][0][
        "target_event_id"
    ] = "missing-event"

    assert not validate_multimodal_record(record)["valid"]


def test_conflicting_source_identity_rejected():
    record = build_record()
    record["modalities"]["audio"]["source"]["source_id"] = "shared-source"
    record["modalities"]["video"]["source"]["source_id"] = "shared-source"

    assert not validate_multimodal_record(record)["valid"]


def test_provenance_tampering_rejected():
    record = build_record()
    record["provenance"]["sources"][0]["checksum_sha256"] = "f" * 64

    assert not validate_multimodal_record(record)["valid"]


def test_duplicate_temporal_event_ids_rejected():
    record = build_record()
    duplicate = copy.deepcopy(record["temporal"]["timeline"]["events"][0])
    record["temporal"]["timeline"]["events"].append(duplicate)
    record["temporal"]["timeline"]["event_count"] += 1

    assert not validate_multimodal_record(record)["valid"]


def test_record_without_temporal_report_valid():
    record = generate_multimodal_record(
        images=[make_report("image", "c" * 64)]
    )

    assert validate_multimodal_record(record)["valid"]


def test_timestamp_boolean_rejected():
    record = build_record()
    record["temporal"]["timeline"]["events"][0]["start_seconds"] = True

    assert not validate_multimodal_record(record)["valid"]


def test_extracted_audio_parent_provenance_is_recorded():
    record = build_record()
    links = record["provenance"]["derived_sources"]

    assert len(links) == 1
    link = links[0]
    assert link["relationship"] == "extracted_from"
    assert link["derived_source"]["checksum_sha256"] == "a" * 64
    assert link["parent_source"]["checksum_sha256"] == "b" * 64
    assert link["extraction_path"].endswith("audio_track.wav")
    assert validate_multimodal_record(record)["valid"]


def test_derived_source_provenance_tampering_is_rejected():
    record = build_record()
    record["provenance"]["derived_sources"][0]["parent_source"][
        "checksum_sha256"
    ] = "f" * 64

    result = validate_multimodal_record(record)
    assert not result["valid"]
    assert any("Derived-source provenance" in error for error in result["errors"])


def test_timeline_duration_mismatch_is_rejected():
    record = build_record()
    record["temporal"]["timeline"]["duration_seconds"] = 10.0

    result = validate_multimodal_record(record)
    assert not result["valid"]
    assert any("Unified timeline duration" in error for error in result["errors"])


def test_invalid_modality_duration_is_rejected():
    record = build_record()
    record["modalities"]["audio"]["audio"]["duration_seconds"] = float("nan")

    result = validate_multimodal_record(record)
    assert not result["valid"]
    assert any("Invalid audio media duration" in error for error in result["errors"])


def test_audio_without_video_has_no_derived_parent():
    audio = make_report("audio", "a" * 64)
    audio["audio"] = {"duration_seconds": 12.0}

    record = generate_multimodal_record(audio_analysis=audio)
    assert record["provenance"]["derived_sources"] == []
    assert validate_multimodal_record(record)["valid"]
