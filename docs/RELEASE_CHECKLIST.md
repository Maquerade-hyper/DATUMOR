# DATUMOR Release Checklist

This checklist is a preparation record, not a declaration that every item has passed.

## Repository
- [x] Select Apache License 2.0 (Apache-2.0) for DATUMOR.
- [ ] Review all tracked and untracked files.
- [ ] Confirm `.env`, backups, local datasets, reports, and credentials are excluded.
- [ ] Review third-party licenses and notices.
- [ ] Confirm the repository contains no customer or personal data.

## Documentation
- [x] Environment-variable reference generated and reviewed.
- [x] API reference generated from OpenAPI; 43 endpoints verified.
- [x] Contribution guide added.
- [x] Security policy added.
- [x] README reviewed and corrected; installation limitations disclosed.
- [ ] Add architecture diagrams and sample workflow instructions where useful.

## Verification
- [x] Docker deployment and end-to-end processing verified.
- [x] Non-root worker processing verified.
- [x] Windows startup script syntax verified.
- [ ] Linux startup script syntax verified (Bash unavailable in verification environment).
- [ ] Fresh manual Windows installation verified.
- [ ] Fresh manual Linux installation verified.
- [ ] Final full test suite run from release candidate.
- [ ] Final secret and dependency audit completed.

## Release
- [ ] Approve license and release version.
- [ ] Review changelog and known limitations.
- [ ] Create release candidate tag.
- [ ] Obtain explicit approval before publishing or pushing.


## M10.3 Final Verification Record

Verification date: 2026-11-13

### Completed
- [x] Repository hygiene and secret-pattern audit.
- [x] Docker Compose deployment and migration verification.
- [x] API reference checked against 43 live endpoints.
- [x] Documentation links and environment reference reviewed.
- [x] Runtime and development dependencies separated.
- [x] Local regression suite: 697 passed, 1 skipped.
- [x] Docker runtime dependency versions verified.
- [x] Docker API and worker health verified.
- [x] Docker JSONL upload and SeaweedFS storage verified.
- [x] Celery extraction job completed and report retrieved.
- [x] Runtime and development third-party inventories generated.

### Pending release gates
- [ ] Final human/legal review of third-party license obligations.
- [ ] Decide whether to remove unused MinIO SDK and retest if removed.
- [ ] Fresh manual Windows installation verification.
- [ ] Fresh manual Linux installation verification.
- [ ] Linux startup scripts independently validated.
- [ ] Release version selected and approved.
- [ ] Final release candidate review.
- [ ] Explicit publication approval.

No commit, tag, push, or publication is authorized by this checklist.
