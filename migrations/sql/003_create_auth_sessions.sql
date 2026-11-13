BEGIN;

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    family_id UUID NOT NULL,
    refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_agent VARCHAR(500),
    ip_address VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_active
    ON auth_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_auth_sessions_family
    ON auth_sessions (family_id);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_expiry
    ON auth_sessions (expires_at);

COMMIT;
