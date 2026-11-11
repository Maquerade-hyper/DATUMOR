# DATUMOR Module Interface Contract

Contract Version: 1.0.0
Status: Initial Foundation Contract

## Rules

1. Modules exchange structured data through documented interfaces.
2. Shared payloads must conform to the applicable JSON Schema.
3. Every payload includes its contract_version where defined.
4. IDs use UUID format.
5. Timestamps use ISO 8601 date-time format.
6. Unknown fields are rejected unless a schema explicitly allows them.
7. Dataset versions are positive integers and must not be overwritten.
8. Errors use the shared ApiError response structure.
9. Source checksums use SHA-256.
10. Changes that break existing consumers require a new contract version.

## Core data contracts

| Schema | Purpose |
|---|---|
| source.schema.json | Registered input source |
| dataset.schema.json | Dataset identity and version |
| processing-job.schema.json | Background processing state |
| processing-profile.schema.json | Task-specific output configuration |
| quality-report.schema.json | Quality evaluation results |
| lineage-event.schema.json | Dataset transformation history |
| api-error.schema.json | Standard API error response |

## Module ownership

- Ingestion creates Source records.
- Dataset services manage Dataset identity and versions.
- Runtime manages ProcessingJob state.
- Transformation consumes ProcessingProfile.
- Quality produces QualityReport.
- Lineage records LineageEvent.
- API boundaries return ApiError on failures.

## Compatibility policy

Minor additions must remain backward compatible.
Breaking changes require a new major contract version.
Schemas are the authoritative definition of payload structure.

These are foundational contracts. Future milestones may extend them through
versioned changes without silently changing existing payload meanings.
