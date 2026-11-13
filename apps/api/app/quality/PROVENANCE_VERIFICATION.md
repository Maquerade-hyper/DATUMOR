# Provenance Verification

`verify_provenance(dukr_documents)` checks source identity, source checksums,
entity evidence, relationship evidence, semantic evidence, and context evidence.

Statuses:
- `verified`: the available provenance evidence passed verification.
- `failed`: a supplied checksum, source reference, or evidence range contradicts
  the original source.
- `incomplete`: required provenance is missing and cannot be verified.

The verifier is deterministic, read-only, and does not modify DUKR documents.
Missing offsets or evidence are never treated as successful verification.

This implementation verifies evidence against the original content retained in
DUKR. It does not independently retrieve objects from SeaweedFS or prove that an
external storage object still exists. That requires a separate storage-backed
verification integration.
