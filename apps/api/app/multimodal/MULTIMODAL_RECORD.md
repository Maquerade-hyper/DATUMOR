# DATUMOR Multimodal Record Contract

Contract version: 1.0.0

Schema:
`contracts/schemas/multimodal-record.schema.json`

## Purpose

Defines the canonical structure used to combine image, audio, video,
and temporal-analysis results without modifying upstream reports.

## Top-level fields

- `record_id`: UUID identifying the generated record.
- `schema_version`: Canonical contract version.
- `created_at`: Record creation timestamp.
- `modalities`: Image, audio, and video analysis payloads.
- `temporal`: Temporal events and relationships, or null when unavailable.
- `provenance`: Source identities and upstream report references.
- `warnings`: Explicit processing limitations and unavailable capabilities.
- `validation`: Validation status and errors.

## Modality handling

`images` is always an array. `audio` and `video` may be null when
those modalities are absent.

The record must preserve the original upstream analysis payloads and
must not claim capabilities that were not executed.

## Provenance

Source checksums and identities must be preserved from upstream reports.
A missing source identifier must remain explicitly null; it must not
be fabricated.

## Temporal data

Temporal relationships must reference existing events. Timestamps
must be validated against their respective media durations.

## Compatibility

This is a new versioned multimodal contract. Existing DUKR records
remain unchanged. DUKR integration will be handled by the record
generation implementation.

## Validation

The JSON Schema defines structural validation. The implementation
must additionally perform semantic checks for checksums, source
identity consistency, timestamps, and temporal references.

## M6.5 End-to-End Verification

### Implementation status

All five M6.5 implementation steps are complete:

1. Canonical multimodal record architecture and JSON Schema.
2. Record generation and modality integration.
3. Temporal relationship and provenance integration.
4. Validation, serialization, export, and reload.
5. End-to-end verification, regression testing, and documentation.

### Verified integration evidence

Controlled end-to-end verification completed successfully.

- Image reports integrated: 3
- Audio processing: passed
- Video processing: passed
- Temporal events: 6
- Provenance sources: 5
- Record validation: passed
- JSON export: passed
- Reload equality: passed
- Record SHA-256:
  `af19a126804977fd204c966be06f184892c081f14a90a672441227948eeb1d45`

Verification artifacts:

- `data/reports/m6_5/end_to_end_multimodal_record.json`
- `data/reports/m6_5/end_to_end_verification.json`

### Regression and static analysis

- Full test suite: 423 passed, 3 warnings.
- Ruff: all checks passed.

### Known limitations

- The end-to-end video fixture produced zero speech events and zero cross-modal temporal alignments.
- Speech-to-frame synchronization is therefore not demonstrated by this verification.
- Image OCR execution using PaddleOCR has not been demonstrated.
- Image understanding currently provides validation, metadata, visual statistics, and an optional OCR adapter; it does not establish object recognition or image captioning.
- Audio speaker diarization is not implemented.
- Video object recognition, captioning, and transcription are not implemented by the video processor.
- Verification used controlled fixtures, not customer-supplied production data.

M6.5 verification demonstrates canonical multimodal record generation, provenance integration, validation, serialization, export, and reload. It does not establish the unverified capabilities listed above.
