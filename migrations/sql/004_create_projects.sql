BEGIN;

CREATE TABLE IF NOT EXISTS projects (
    project_id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,

    CONSTRAINT ck_projects_status
        CHECK (status IN ('active', 'archived')),
    CONSTRAINT ck_projects_name_length
        CHECK (length(trim(name)) BETWEEN 2 AND 100)
);

CREATE INDEX IF NOT EXISTS ix_projects_owner_created
    ON projects (owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_projects_owner_status
    ON projects (owner_user_id, status);

CREATE TABLE IF NOT EXISTS project_activity (
    activity_id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    action VARCHAR(40) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_project_activity_project_created
    ON project_activity (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_project_activity_actor_created
    ON project_activity (actor_user_id, created_at DESC);

COMMIT;
