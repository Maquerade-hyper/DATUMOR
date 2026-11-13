# DATUMOR Source Registry

Contract: 1.0.0

The `sources` PostgreSQL table stores persistent identities for ingested inputs.

Supported source types:
- file
- github

Each source record includes:
- UUID source identity
- Optional project identity (project management is scheduled for M1.9)
- Source type and name
- Media type
- SHA-256 content or canonical repository-manifest checksum
- Staging URI
- Byte size
- JSON metadata
- Lifecycle status
- UTC creation timestamp

API:
- POST /api/v1/ingestion/files
- POST /api/v1/ingestion/github
- GET /api/v1/sources
- GET /api/v1/sources/{source_id}

Staged source data is not yet promoted to permanent object storage.
That integration is scheduled for M1.5.
