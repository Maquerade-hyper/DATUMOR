# Changelog

All notable changes to DATUMOR will be documented here.

## Unreleased

### Implemented
- Authentication and project management.
- Project-scoped file and GitHub ingestion.
- Background processing with Celery and Redis.
- SeaweedFS S3-compatible object storage.
- Processing reports, downloads, artifacts, and version manifests.
- Usage metering, configurable limits, and resource monitoring.
- Docker Compose deployment and database migrations.

### Verified
- Local regression suite: 697 passed, 1 skipped.
- Docker API and worker startup after dependency separation.
- Non-root worker execution.
- Docker JSONL upload, object storage verification, processing, and report retrieval.
- Production image excludes pytest, pytest-cov, Ruff, and PyMuPDF.

### Known limitations
- The Docker E2E test verifies extraction, not every later intelligence pipeline stage.
- Fresh manual Windows and Linux installations have not been certified.
- Production certification and legal redistribution approval are not claimed.
