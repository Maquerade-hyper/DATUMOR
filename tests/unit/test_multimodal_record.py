import copy
import json

import pytest

from apps.api.app.multimodal.multimodal_record import (
    MultimodalRecordError,
    generate_multimodal_record,
    export_multimodal_record,
    load_multimodal_record,
)


def report(report_type, name, checksum):
    return {
        "report_type": f"datumor.{report_type}_analysis",
        "version": "1.0.0",
        "status": "completed",
        "created_at": "2026-11-11T12:00:00+00:00",
        "source": {
            "source_id": None,
            "source_name": name,
            "checksum_sha256": checksum,
            "size_bytes": 100,
            "media_type": report_type,
        },
        "capabilities": {},
        "warnings": [],
    }


IMAGE = report("image", "image.png", "a" * 64)
AUDIO = report("audio", "audio.wav", "b" * 64)
VIDEO = report("video", "video.mp4", "c" * 64)


def test_generate_image_only_record():
    record = generate_multimodal_record(images=[IMAGE])
    assert len(record["modalities"]["images"]) == 1
    assert record["modalities"]["audio"] is None
    assert record["modalities"]["video"] is None


def test_generate_audio_only_record():
    record = generate_multimodal_record(audio_analysis=AUDIO)
    assert record["modalities"]["audio"]["source"]["source_name"] == "audio.wav"


def test_generate_video_only_record():
    record = generate_multimodal_record(video_analysis=VIDEO)
    assert record["modalities"]["video"]["source"]["source_name"] == "video.mp4"


def test_generate_combined_record():
    record = generate_multimodal_record(
        images=[IMAGE],
        audio_analysis=AUDIO,
        video_analysis=VIDEO,
    )
    assert len(record["provenance"]["sources"]) == 3


def test_missing_modalities_are_explicit():
    record = generate_multimodal_record(images=[IMAGE])
    assert record["modalities"]["audio"] is None
    assert record["modalities"]["video"] is None
    assert record["temporal"] is None


def test_upstream_reports_are_not_modified():
    original = copy.deepcopy(IMAGE)
    generate_multimodal_record(images=[IMAGE])
    assert IMAGE == original


def test_source_checksum_is_preserved():
    record = generate_multimodal_record(images=[IMAGE])
    assert record["provenance"]["sources"][0]["checksum_sha256"] == "a" * 64


def test_invalid_checksum_is_rejected():
    invalid = copy.deepcopy(IMAGE)
    invalid["source"]["checksum_sha256"] = "invalid"

    with pytest.raises(MultimodalRecordError):
        generate_multimodal_record(images=[invalid])


def test_incomplete_report_is_rejected():
    invalid = copy.deepcopy(IMAGE)
    invalid["status"] = "failed"

    with pytest.raises(MultimodalRecordError):
        generate_multimodal_record(images=[invalid])


def test_no_modalities_is_rejected():
    with pytest.raises(MultimodalRecordError):
        generate_multimodal_record()


def test_temporal_report_is_preserved():
    temporal = {"events": [], "relationships": []}
    record = generate_multimodal_record(
        images=[IMAGE],
        temporal_analysis=temporal,
    )
    assert record["temporal"] == temporal


def test_export_and_reload(tmp_path):
    record = generate_multimodal_record(
        images=[IMAGE],
        audio_analysis=AUDIO,
    )
    path = export_multimodal_record(record, tmp_path / "record.json")
    loaded = load_multimodal_record(path)

    assert loaded == record
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_unavailable_capabilities_become_warnings():
    image = copy.deepcopy(IMAGE)
    image["capabilities"] = {"ocr": False}

    record = generate_multimodal_record(images=[image])
    assert "image: capability unavailable: ocr" in record["warnings"]
