BEGIN;

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id VARCHAR(36) PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    owner_user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    celery_task_id VARCHAR(128),
    name VARCHAR(200) NOT NULL,
    pipeline VARCHAR(40) NOT NULL DEFAULT 'standard',
    source_ids JSONB NOT NULL,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    stage VARCHAR(80) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    result JSONB,
    error_message TEXT,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    attempt INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_processing_jobs_project_created
    ON processing_jobs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_processing_jobs_owner_status
    ON processing_jobs(owner_user_id, status);

CREATE TABLE IF NOT EXISTS processing_job_events (
    event_id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES processing_jobs(job_id) ON DELETE CASCADE,
    level VARCHAR(16) NOT NULL DEFAULT 'info',
    stage VARCHAR(80) NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_processing_job_events_job_created
    ON processing_job_events(job_id, created_at);

COMMIT;
