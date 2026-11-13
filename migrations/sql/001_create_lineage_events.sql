CREATE TABLE IF NOT EXISTS lineage_events (
    event_id VARCHAR(36) PRIMARY KEY,
    contract_version VARCHAR(16) NOT NULL,
    dataset_id VARCHAR(36) NOT NULL,
    dataset_version INTEGER NOT NULL
        CHECK (dataset_version >= 1),
    event_type VARCHAR(32) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    input_references JSON NOT NULL,
    output_checksum_sha256 VARCHAR(64),
    metadata JSON NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_lineage_dataset_timestamp
    ON lineage_events (dataset_id, timestamp);

CREATE INDEX IF NOT EXISTS ix_lineage_dataset_version
    ON lineage_events (dataset_id, dataset_version);

CREATE INDEX IF NOT EXISTS ix_lineage_event_type
    ON lineage_events (event_type);
