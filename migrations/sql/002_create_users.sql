BEGIN;

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(120),
    role VARCHAR(16) NOT NULL DEFAULT 'customer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_email_normalized UNIQUE (email_normalized),
    CONSTRAINT ck_users_role
        CHECK (role IN ('customer', 'admin', 'superadmin')),
    CONSTRAINT ck_users_email_length
        CHECK (length(email) BETWEEN 3 AND 320),
    CONSTRAINT ck_users_normalized_email_length
        CHECK (length(email_normalized) BETWEEN 3 AND 320),
    CONSTRAINT ck_users_normalized_email_format
        CHECK (email_normalized = lower(trim(email_normalized)))
);

CREATE INDEX IF NOT EXISTS ix_users_created_at
    ON users (created_at);

CREATE INDEX IF NOT EXISTS ix_users_role_active
    ON users (role, is_active);

COMMIT;
