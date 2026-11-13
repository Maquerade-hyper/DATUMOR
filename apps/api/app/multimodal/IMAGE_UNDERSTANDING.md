# M6.1 ? Image Understanding

## Public functions

- `validate_image(image_path, max_bytes=50MiB, max_pixels=100M)`
- `analyze_image(image_path, source_identity=None, ocr_engine=None)`

## Supported image formats

JPEG, PNG, WEBP, BMP, TIFF, and GIF.

## Capabilities

- Image signature and corruption validation
- File size and decompression limits
- Dimensions, aspect ratio, frame count, mode, transparency
- Selected EXIF metadata; GPS information is deliberately excluded
- SHA-256 content fingerprint
- Deterministic brightness, contrast, channel statistics, color histograms,
  and gradient-based edge-density estimate
- Optional OCR adapter interface with text, confidence, and bounding boxes
- Pixel and normalized coordinate references
- Source identity and checksum provenance

## OCR

OCR is optional. Supply an object exposing `extract(path)` or a callable
that returns a list of dictionaries containing `text`, optional `confidence`,
and optional `bounding_box`.

`PaddleOCRAdapter` provides an adapter for the PaddleOCR legacy `ocr()` API.
PaddleOCR must be installed and configured separately.

If OCR fails, deterministic image analysis is retained and the report records
the failure as a warning.

## Explicit limitations

This milestone implementation does not perform object detection, image
captioning, face recognition, or visual question answering. Statistical
features must not be represented as semantic understanding.

## Safety and provenance

- Source files are read-only.
- SHA-256 is computed from the original file bytes.
- Supplied source checksums are verified.
- EXIF GPS is not retained.
- OCR evidence includes image-coordinate bounding boxes.
