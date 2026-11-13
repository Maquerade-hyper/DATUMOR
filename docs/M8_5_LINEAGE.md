# M8.5 — Lineage

## Lineage Event Registry and Persistence

The registry persists append-only lineage events in the
`lineage_events` SQLAlchemy table.

The event model follows the existing `lineage-event` contract version
1.0.0 and stores:

- Event and dataset UUIDs.
- Dataset version and event type.
- Actor and timezone-aware UTC timestamp.
- Input references.
- Optional output SHA-256 checksum.
- JSON metadata.

Public registry functions:

- `validate_lineage_event(event)`
- `record_lineage_event(session, event)`
- `get_lineage_event(session, event_id)`
- `list_lineage_events(session, dataset_id, dataset_version=None,
  event_type=None, limit=100, offset=0)`

Identical event submissions are idempotent. Reusing an event ID with
different content raises `DuplicateLineageEventError`.

The registry does not expose update or delete operations. Events are
ordered by timestamp and event ID when queried.

The database model uses the existing application SQLAlchemy Base.
The table must be included in the application's Alembic migration
workflow before production deployment.

The current step establishes persistence and registry behavior.
Pipeline integration, dataset/version relationships, export linkage,
and lineage reports are subsequent M8.5 implementation steps.
# M8.5 — Pipeline Event Integration

## Pipeline event integration

`pipeline_integration.py` provides a shared integration boundary for
successful processing stages.

Supported stage-to-contract mappings:

| Pipeline stage | Lineage event |
|---|---|
| source_ingestion | source_added |
| extraction | extracted |
| understanding | understood |
| quality | quality_checked |
| transformation | transformed |
| optimization | optimized |
| validation | validated |

The public APIs are:

- `record_pipeline_stage_success(...)`
- `track_pipeline_stage(...)`

The context manager records an event only after the wrapped operation
returns successfully. Exceptions propagate and do not create success events.

Each event carries dataset ID, dataset version, actor, UTC timestamp,
input references, optional output checksum, and stage metadata.

Transaction ownership remains with the calling pipeline service.
The integration layer flushes through the existing registry but does
not commit the caller's transaction.

A stage must be called only after its dataset identity and version are
known. The helper is the integration boundary for the existing processing
services; it does not invent dataset identities for source-only operations.

## M8.5 Step 3 — Dataset and Version Lineage

Implemented `dataset_version_lineage.py` to record immutable dataset-version
provenance through the existing append-only lineage registry. Each version
event records the dataset identity, version number and ID, parent version ID,
source IDs, pipeline run ID, input references, actor, timestamp, and optional
output checksum.

The caller owns the database transaction. The module does not commit.
`build_dataset_version_lineage` reconstructs and validates ordered version
ancestry from recorded events, rejecting duplicate versions and broken
parent relationships.

This module provides the lineage recording and graph-building boundary. It
does not automatically discover source records or pipeline runs, nor does it
modify the M8.3 version snapshots.

## M8.5 Step 4 — Export Lineage and Integrity

Added `export_lineage_integration.py`, which wraps the existing M8.4
exporter without modifying its serialization or atomic publication logic.

The integration independently recomputes the artifact and manifest SHA-256
checksums, verifies the artifact size, parses the manifest, and checks that
the manifest describes the exact published artifact.

Only after all checks pass does it persist an `exported` lineage event through
the existing SQLAlchemy registry. The event records dataset/version identity,
pipeline run, source references, artifact path and checksum, manifest path
and checksum, format, size, example count, and integrity status.

The caller owns the database transaction. Exported files remain on disk if
lineage persistence fails; the exception exposes the export result for
recovery. No successful export event is written for a failed export or
failed integrity check.

## M8.5 Step 5 — Lineage Queries, Reports and End-to-End Verification

Implemented `lineage_queries.py` with:
- Paginated and filtered dataset event queries.
- Complete dataset event history.
- Dataset version ancestry reconstruction.
- Source-to-event traceability.
- Export artifact and manifest traceability.
- Machine-readable JSON lineage reports.
- Human-readable Markdown lineage reports.
- Atomic report file publication.

The end-to-end test exercises all seven pipeline stage event types,
creates an immutable dataset version, exports the dataset, and verifies
the complete lineage history, source traceability, export checksums,
and report summary.

The query layer reads from the existing append-only registry and does not
modify persisted lineage events.
