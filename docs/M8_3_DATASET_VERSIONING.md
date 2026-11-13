# M8.3 — Dataset Versioning

DATUMOR stores immutable dataset snapshots under
`{storage_dir}/{dataset_id}/versions/vNNNNNN.json`.

Each version contains a UUID, monotonically increasing version number,
parent version reference, UTC creation timestamp, dataset snapshot,
metadata, and SHA-256 checksum of the canonical dataset JSON.

A new version must reference the latest version as its parent. Existing
version files are never overwritten. Loading, listing, and comparing
versions verifies their stored checksums.

Comparison uses stable `example_id` values in the dataset `examples` list.
