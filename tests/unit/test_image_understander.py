from pathlib import Path

import pytest
from PIL import Image

from apps.api.app.multimodal.image_understander import (
    ImageValidationError,
    analyze_image,
    validate_image,
)


def create_image(path: Path, color=(120, 80, 40), size=(64, 48)):
    image = Image.new("RGB", size, color)
    image.save(path, format="PNG")
    return path


def test_valid_image_metadata(tmp_path):
    path = create_image(tmp_path / "sample.png")
    result = validate_image(path)

    assert result["valid"] is True
    assert result["format"] == "png"
    assert result["width"] == 64
    assert result["height"] == 48
    assert result["pixel_count"] == 3072


def test_analysis_returns_structured_report(tmp_path):
    path = create_image(tmp_path / "sample.png")
    result = analyze_image(path)

    assert result["report_type"] == "datumor.image_analysis"
    assert result["status"] == "completed"
    assert result["source"]["checksum_sha256"]
    assert result["image"]["aspect_ratio"] == round(64 / 48, 6)
    assert result["visual_analysis"]["brightness_mean"] > 0
    assert result["capabilities"]["object_detection"] is False


def test_source_identity_and_checksum_are_preserved(tmp_path):
    path = create_image(tmp_path / "sample.png")
    initial = analyze_image(path)

    result = analyze_image(
        path,
        source_identity={
            "source_id": "source-123",
            "source_name": "registered-image.png",
            "checksum_sha256": initial["source"]["checksum_sha256"],
        },
    )

    assert result["source"]["source_id"] == "source-123"
    assert result["source"]["source_name"] == "registered-image.png"


def test_mismatched_source_checksum_is_rejected(tmp_path):
    path = create_image(tmp_path / "sample.png")

    with pytest.raises(ValueError, match="checksum"):
        analyze_image(
            path,
            source_identity={"checksum_sha256": "wrong"},
        )


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ImageValidationError, match="does not exist"):
        validate_image(tmp_path / "missing.png")


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.png"
    path.write_bytes(b"")

    with pytest.raises(ImageValidationError, match="empty"):
        validate_image(path)


def test_corrupt_image_is_rejected(tmp_path):
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"not-an-image")

    with pytest.raises(ImageValidationError, match="Invalid or corrupt"):
        validate_image(path)


def test_size_limit_is_enforced(tmp_path):
    path = create_image(tmp_path / "sample.png")

    with pytest.raises(ImageValidationError, match="maximum size"):
        validate_image(path, max_bytes=10)


def test_pixel_limit_is_enforced(tmp_path):
    path = create_image(tmp_path / "sample.png", size=(64, 48))

    with pytest.raises(ImageValidationError, match="pixel count"):
        validate_image(path, max_pixels=100)


def test_ocr_observations_include_coordinates(tmp_path):
    path = create_image(tmp_path / "sample.png")

    def fake_ocr(_path):
        return [{
            "text": "DATUMOR",
            "confidence": 0.98,
            "bounding_box": [
                [10, 10], [40, 10], [40, 20], [10, 20]
            ],
        }]

    result = analyze_image(path, ocr_engine=fake_ocr)
    observation = result["ocr"]["observations"][0]

    assert result["ocr"]["status"] == "completed"
    assert observation["text"] == "DATUMOR"
    assert observation["confidence"] == 0.98
    assert observation["bounding_box"]["bounds_normalized"]["x_min"] > 0


def test_ocr_failure_is_reported_without_losing_image_analysis(tmp_path):
    path = create_image(tmp_path / "sample.png")

    def failing_ocr(_path):
        raise RuntimeError("OCR unavailable")

    result = analyze_image(path, ocr_engine=failing_ocr)

    assert result["status"] == "completed_with_warnings"
    assert result["image"]["format"] == "png"
    assert result["ocr"]["status"] == "failed"
    assert result["warnings"]


def test_ocr_not_configured_is_explicit(tmp_path):
    path = create_image(tmp_path / "sample.png")
    result = analyze_image(path)

    assert result["ocr"]["status"] == "not_configured"
    assert result["capabilities"]["ocr"] is False


def test_ocr_invalid_confidence_is_rejected_by_normalizer(tmp_path):
    path = create_image(tmp_path / "sample.png")

    def invalid_ocr(_path):
        return [{
            "text": "invalid",
            "confidence": 1.5,
            "bounding_box": [
                [1, 1], [4, 1], [4, 4], [1, 4]
            ],
        }]

    result = analyze_image(path, ocr_engine=invalid_ocr)

    assert result["ocr"]["status"] == "failed"
    assert "confidence" in result["warnings"][0]


def test_visual_statistics_are_deterministic(tmp_path):
    path = create_image(tmp_path / "sample.png")
    first = analyze_image(path)
    second = analyze_image(path)

    assert first["visual_analysis"] == second["visual_analysis"]


def test_exif_gps_is_not_retained(tmp_path):
    path = create_image(tmp_path / "sample.png")
    result = analyze_image(path)

    assert "gps_info" not in result["image"]["exif"]
