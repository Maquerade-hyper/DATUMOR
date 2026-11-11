# DATUMOR — Architecture Decision Records
Version: 1.0.0
Status: ACCEPTED

ADR-001: Modular Monolith + Workers
Decision: One modular backend with separate workers.
Reason: Simpler development and deployment.

ADR-002: FastAPI
Decision: FastAPI for REST APIs.
Reason: Python ecosystem and asynchronous support.

ADR-003: PostgreSQL
Decision: Primary relational database.
Reason: Reliable transactions and structured data.

ADR-004: Redis + Celery
Decision: Background job execution.
Reason: Mature asynchronous processing infrastructure.

ADR-005: MinIO
Decision: S3-compatible object storage.
Reason: Separate binary storage from relational data.

ADR-006: DUKR
Decision: Canonical internal knowledge representation.
Reason: Preserve source context across transformations.

ADR-007: DQIS
Decision: Independent quality intelligence.
Reason: Prevent unverified AI output acceptance.

ADR-008: Provider Adapters
Decision: Provider-independent AI integration.
Reason: Avoid foundation-model dependency.

ADR-009: Docker
Decision: Containerized deployment.
Reason: Reproducible environments.

ADR-010: Immutable Dataset Versions
Decision: Never overwrite published dataset versions.
Reason: Reproducibility and traceability.

ADR-011: Optional Embeddings
Decision: Embeddings only when required.
Reason: Avoid unnecessary processing costs.

ADR-012: Independent Validation
Decision: Validate transformed outputs independently.
Reason: Reliable commercial delivery.

All decisions are locked for the DATUMOR M0-M10 roadmap.
