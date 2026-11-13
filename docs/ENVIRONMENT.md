# Environment Variables

Copy `.env.example` to `.env`. Replace all example credentials with private,
strong values. Never commit `.env`.

## Application

| Variable | Purpose |
|---|---|
| `APP_ENV` | Application environment. |
| `APP_NAME` | Application/service name. |
| `APP_SECRET_KEY` | Application security secret. Generate a unique strong value. |
| `APP_VERSION` | Application version identifier. |

## Database

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Database connection URL. Check application configuration precedence before using it alongside individual database settings. |
| `DATUMOR_DB_HOST` | DATUMOR database hostname. |
| `DATUMOR_DB_NAME` | DATUMOR database name. |
| `DATUMOR_DB_PASSWORD` | DATUMOR database password. |
| `DATUMOR_DB_PORT` | Database TCP port. |
| `DATUMOR_DB_USER` | DATUMOR database username. |
| `POSTGRES_DB` | PostgreSQL database name used by Docker Compose. |
| `POSTGRES_PASSWORD` | PostgreSQL password used by Docker Compose. |
| `POSTGRES_USER` | PostgreSQL user used by Docker Compose. |

## Redis

| Variable | Purpose |
|---|---|
| `DATUMOR_REDIS_URL` | Redis connection URL used by DATUMOR. |
| `REDIS_PASSWORD` | Redis authentication password used by Docker Compose. |
| `REDIS_URL` | Additional Redis connection URL setting. |

## Object Storage

| Variable | Purpose |
|---|---|
| `DATUMOR_S3_ACCESS_KEY` | S3-compatible storage access key. |
| `DATUMOR_S3_SECRET_KEY` | S3-compatible storage secret key. |
| `MINIO_BUCKET` | Legacy/compatibility object-storage bucket setting. |
| `MINIO_ENDPOINT` | Legacy/compatibility object-storage endpoint setting. |
| `MINIO_ROOT_PASSWORD` | Legacy MinIO root password setting. |
| `MINIO_ROOT_USER` | Legacy MinIO root username setting. |
| `MINIO_SECURE` | Legacy MinIO TLS setting. |

The current Docker Compose deployment uses SeaweedFS with the
`DATUMOR_S3_ACCESS_KEY` and `DATUMOR_S3_SECRET_KEY` variables. The `MINIO_*`
variables are retained in the example configuration for compatibility and
are not referenced by the current Compose file.

## Processing

| Variable | Purpose |
|---|---|
| `DATUMOR_STAGING_DIR` | Local staging directory used for processing files. |

## Security Rules

- Never commit `.env` or real credentials.
- Keep `.env.example` free of real secrets.
- Use different credentials for development, staging, and production.
- Rotate credentials immediately if exposed.
- Restrict database, Redis, and object-storage network access.
- Use container service names for internal Docker connections.
