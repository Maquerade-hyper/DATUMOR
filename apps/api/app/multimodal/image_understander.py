"""Deterministic image analysis and optional OCR for DATUMOR M6.1."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


REPORT_TYPE = "datumor.image_analysis"
REPORT_VERSION = "1.0.0"

SUPPORTED_FORMATS = {
    "JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"
}

DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PIXELS = 100_000_000


class ImageValidationError(ValueError):
    """Raised when an image is invalid or exceeds configured limits."""


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_exif(image: Image.Image) -> dict:
    """Extract a limited, JSON-safe set of EXIF fields."""
    try:
        exif = image.getexif()
    except Exception:
        return {}

    selected = {
        271: "camera_make",
        272: "camera_model",
        306: "datetime",
        36867: "datetime_original",
        34853: "gps_info",
        274: "orientation",
        33434: "exposure_time",
        33437: "f_number",
        34855: "iso",
        37386: "focal_length",
    }

    result = {}
    for tag, name in selected.items():
        if tag not in exif:
            continue
        value = exif.get(tag)
        if tag == 34853:
            # GPS is deliberately not extracted or retained.
            continue
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, (str, int, float, bool)):
            result[name] = value
        else:
            result[name] = str(value)

    return result


def validate_image(
    image_path: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> dict:
    """Validate image signature, format, dimensions, and file limits."""
    path = Path(image_path)

    if not path.is_file():
        raise ImageValidationError(f"Image file does not exist: {path}")

    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise ImageValidationError("Image file is empty")

    if size_bytes > max_bytes:
        raise ImageValidationError(
            f"Image exceeds maximum size of {max_bytes} bytes"
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image_format = image.format
                width, height = image.size
                frame_count = getattr(image, "n_frames", 1)
                image.verify()
    except Image.DecompressionBombError as exc:
        raise ImageValidationError("Image exceeds decompression safety limit") from exc
    except Image.DecompressionBombWarning as exc:
        raise ImageValidationError("Image triggers decompression safety warning") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImageValidationError(f"Invalid or corrupt image: {exc}") from exc

    if image_format not in SUPPORTED_FORMATS:
        raise ImageValidationError(
            f"Unsupported image format: {image_format}"
        )

    if width <= 0 or height <= 0:
        raise ImageValidationError("Image dimensions must be positive")

    if width * height > max_pixels:
        raise ImageValidationError(
            f"Image exceeds maximum pixel count of {max_pixels}"
        )

    return {
        "valid": True,
        "format": image_format.lower(),
        "width": width,
        "height": height,
        "pixel_count": width * height,
        "frame_count": frame_count,
        "size_bytes": size_bytes,
    }


def _visual_statistics(image: Image.Image) -> dict:
    """Compute deterministic image statistics; does not identify objects."""
    rgb = image.convert("RGB")
    array = np.asarray(rgb, dtype=np.float32)

    channel_means = array.mean(axis=(0, 1))
    channel_stds = array.std(axis=(0, 1))

    gray = (
        0.299 * array[:, :, 0]
        + 0.587 * array[:, :, 1]
        + 0.114 * array[:, :, 2]
    )

    brightness = float(gray.mean())
    contrast = float(gray.std())

    # Simple gradient-based edge density estimate.
    gradient_x = np.abs(np.diff(gray, axis=1))
    gradient_y = np.abs(np.diff(gray, axis=0))

    edge_x = float(np.mean(gradient_x > 30)) if gradient_x.size else 0.0
    edge_y = float(np.mean(gradient_y > 30)) if gradient_y.size else 0.0

    histogram = {}
    for index, channel in enumerate(("red", "green", "blue")):
        counts, _ = np.histogram(array[:, :, index], bins=8, range=(0, 256))
        total = int(counts.sum())
        histogram[channel] = [
            round(int(value) / total, 6) if total else 0.0
            for value in counts
        ]

    return {
        "brightness_mean": round(brightness, 4),
        "contrast_stddev": round(contrast, 4),
        "channel_means": {
            name: round(float(value), 4)
            for name, value in zip(("red", "green", "blue"), channel_means)
        },
        "channel_stddevs": {
            name: round(float(value), 4)
            for name, value in zip(("red", "green", "blue"), channel_stds)
        },
        "color_histogram_8_bins": histogram,
        "edge_density_estimate": round((edge_x + edge_y) / 2, 6),
        "analysis_method": "pillow_numpy_deterministic_statistics",
        "object_recognition_performed": False,
        "image_captioning_performed": False,
    }


class PaddleOCRAdapter:
    """Optional adapter for the PaddleOCR legacy OCR interface."""

    def __init__(self, language: str = "en"):
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install and configure it "
                "before using this adapter."
            ) from exc

        self.engine = PaddleOCR(use_angle_cls=True, lang=language)

    def extract(self, image_path: str | Path) -> list[dict]:
        raw = self.engine.ocr(str(image_path), cls=True)
        observations = []

        if not raw:
            return observations

        for page in raw:
            if not page:
                continue

            for item in page:
                if not item or len(item) < 2:
                    continue

                polygon, recognition = item[0], item[1]
                if not recognition or len(recognition) < 2:
                    continue

                text, confidence = recognition[0], recognition[1]
                observations.append({
                    "text": str(text),
                    "confidence": float(confidence),
                    "bounding_box": polygon,
                })

        return observations


def _normalize_ocr_observations(
    observations: list[dict],
    width: int,
    height: int,
) -> list[dict]:
    normalized = []

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        confidence = item.get("confidence")
        if confidence is not None:
            confidence = float(confidence)
            if not 0 <= confidence <= 1:
                raise ValueError("OCR confidence must be between 0 and 1")

        polygon = item.get("bounding_box")
        normalized_box = None

        if polygon is not None:
            points = []
            for point in polygon:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    raise ValueError("Invalid OCR bounding-box point")
                x, y = float(point[0]), float(point[1])
                points.append([x, y])

            if len(points) < 4:
                raise ValueError("OCR bounding box requires at least four points")

            xs = [point[0] for point in points]
            ys = [point[1] for point in points]

            normalized_box = {
                "polygon_pixels": points,
                "bounds_pixels": {
                    "x_min": min(xs),
                    "y_min": min(ys),
                    "x_max": max(xs),
                    "y_max": max(ys),
                },
                "bounds_normalized": {
                    "x_min": round(min(xs) / width, 6),
                    "y_min": round(min(ys) / height, 6),
                    "x_max": round(max(xs) / width, 6),
                    "y_max": round(max(ys) / height, 6),
                },
            }

        normalized.append({
            "observation_id": f"ocr-{index + 1:06d}",
            "text": text,
            "confidence": confidence,
            "bounding_box": normalized_box,
            "observation_type": "ocr_text",
            "evidence_method": "ocr_engine",
        })

    return normalized


def analyze_image(
    image_path: str | Path,
    source_identity: dict | None = None,
    ocr_engine=None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> dict:
    """Analyze an image and return a provenance-aware structured record."""
    path = Path(image_path)
    validation = validate_image(path, max_bytes, max_pixels)
    checksum = _file_sha256(path)

    with Image.open(path) as original:
        exif = _safe_exif(original)
        oriented = ImageOps.exif_transpose(original)
        width, height = oriented.size
        visual = _visual_statistics(oriented)

        image_metadata = {
            **validation,
            "width": width,
            "height": height,
            "aspect_ratio": round(width / height, 6),
            "mode": original.mode,
            "has_transparency": (
                "A" in original.getbands()
                or "transparency" in original.info
            ),
            "exif": exif,
        }

    source = {
        "source_id": None,
        "source_name": path.name,
        "checksum_sha256": checksum,
        "size_bytes": validation["size_bytes"],
        "media_type": f"image/{validation['format']}",
    }

    if source_identity is not None:
        if not isinstance(source_identity, dict):
            raise TypeError("source_identity must be a dictionary")

        source["source_id"] = source_identity.get("source_id")
        source["source_name"] = (
            source_identity.get("source_name") or source["source_name"]
        )
        supplied_checksum = source_identity.get("checksum_sha256")
        if supplied_checksum and supplied_checksum != checksum:
            raise ValueError("Source identity checksum does not match image")
        source["checksum_sha256"] = checksum

    warnings_list = []
    ocr_observations = []
    ocr_status = "not_configured"

    if ocr_engine is not None:
        try:
            if hasattr(ocr_engine, "extract"):
                raw_observations = ocr_engine.extract(path)
            elif callable(ocr_engine):
                raw_observations = ocr_engine(path)
            else:
                raise TypeError("ocr_engine must be callable or expose extract()")

            if not isinstance(raw_observations, list):
                raise ValueError("OCR engine must return a list")

            ocr_observations = _normalize_ocr_observations(
                raw_observations, width, height
            )
            ocr_status = "completed"
        except Exception as exc:
            ocr_status = "failed"
            warnings_list.append(
                f"OCR extraction failed: {type(exc).__name__}: {exc}"
            )

    return {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "status": "completed_with_warnings" if warnings_list else "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "image": image_metadata,
        "visual_analysis": visual,
        "ocr": {
            "status": ocr_status,
            "engine": (
                type(ocr_engine).__name__ if ocr_engine is not None else None
            ),
            "observations": ocr_observations,
            "text": "\n".join(item["text"] for item in ocr_observations),
            "observation_count": len(ocr_observations),
        },
        "capabilities": {
            "metadata_extraction": True,
            "deterministic_visual_statistics": True,
            "ocr": ocr_status == "completed",
            "object_detection": False,
            "image_captioning": False,
            "face_recognition": False,
        },
        "provenance": {
            "source_id": source["source_id"],
            "source_checksum_sha256": checksum,
            "visual_analysis_method": visual["analysis_method"],
            "ocr_observation_count": len(ocr_observations),
        },
        "warnings": warnings_list,
    }
