BEGIN;

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS execution_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_processing_jobs_recovery_lease
    ON processing_jobs(status, lease_expires_at)
    WHERE status = 'running';

COMMIT;
