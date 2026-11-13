# M8.4 — Export Engine

## Dataset serialization pipeline

The export pipeline serializes dataset objects into:

- JSON: complete dataset object.
- JSONL: one example object per line.
- Parquet: one example per row using PyArrow and Zstandard compression.

Public interface:

`export_dataset(dataset, output_dir, configuration)`

The result reports success, format, filename, output path, byte size,
and example count.

The serializer validates dataset structure, rejects invalid JSON values,
supports empty example lists, and does not mutate the caller's dataset.

Existing files are protected by default. Explicit overwrite configuration
allows replacement.

Atomic writes, checksums, metadata/provenance policies, and export reports
remain part of the ongoing M8.4 implementation.
# M8.4 — Export Engine

## Atomic export and integrity

The exporter stages serialized content in a temporary file located in
the destination directory.

Before publication:
- Flushes staged data.
- Calls fsync on the staged file.
- Calculates and verifies the staged SHA-256 checksum.

Publication:
- overwrite=false uses an atomic hard-link operation that refuses to
  replace an existing destination.
- overwrite=true uses os.replace to atomically replace the destination.

After publication:
- Reads the final file.
- Recalculates SHA-256.
- Rejects a checksum mismatch.

The export result includes:
- content_sha256
- integrity_verified
- atomic_write

Temporary files are cleaned up after failed staging or publication.

Filesystem note:
No-overwrite atomic publication requires hard-link support on the
destination filesystem. Unsupported filesystems fail safely rather
than silently falling back to a non-atomic write.

## Metadata and provenance preservation

Every export produces a companion manifest named
`<artifact filename>.manifest.json`.

The manifest contains:
- Dataset-level metadata from the dataset object, excluding `examples`.
- Per-example provenance, associated by `example_id` or by source example index
  when an example has no ID.
- Artifact filename, format, SHA-256 checksum, byte size, and example count.
- Explicit metadata and provenance inclusion flags.

The `include_metadata` and `include_provenance` configuration options are
enforced. When provenance is excluded, it is removed from exported examples
and omitted from the manifest. When metadata is excluded, dataset-level
fields are omitted from JSON exports and from the manifest.

JSONL remains one example per line. Parquet remains one example per row.
The manifest is published after the artifact and acts as the export
completion marker. Each file is individually staged, checksummed, and
atomically published; publication of the two-file pair is not a single
filesystem transaction.

## Final validation and export result

The export result acts as the machine-readable export report. It includes
artifact identity, format, size, example count, SHA-256, atomic publication
status, manifest identity, manifest checksum, and metadata/provenance policy.

End-to-end verification covers JSON, JSONL, and Parquet, including
artifact-to-manifest checksum matching, metadata and provenance retention,
empty datasets, overwrite behavior, and temporary-file cleanup.

The artifact and manifest are individually atomic publications. They are
not a single filesystem transaction. Consumers should treat the manifest
as the completion marker and verify its artifact checksum before use.
