# DATUMOR

Universal Multimodal Data Intelligence & Preparation Engine.

## Purpose
Transform raw information into structured, traceable,
quality-verified datasets for AI applications.

## Architecture
Modular monolith with independent background workers.

## Technology
- Python 3.12+
- FastAPI
- React + TypeScript + Vite
- PostgreSQL
- Redis + Celery
- SeaweedFS
- Hugging Face
- Docker

## Project Structure
- apps: API and customer interface
- contracts: Shared schemas and interfaces
- engine: Data intelligence engines
- runtime: Orchestration and workers
- services: Business services
- security: Authentication and file safety
- platform: Infrastructure adapters
- tests: Automated and acceptance tests
- docs: Product and engineering documentation

## Development
Follow the locked M0-M10 development roadmap.
Every milestone requires real-world acceptance testing.

## Status
M0-M9.5 - Development implementation completed with documented limitations
M10 - Open-source release preparation in progress


## Installation and Deployment

### Requirements

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- Docker Engine and Docker Compose v2 (for container deployment)

### Docker Compose

1. Copy `.env.example` to `.env`.
2. Configure strong local values for database, Redis, application and S3 credentials.
3. Start:

   ```bash
   docker compose up --build -d
   ```

4. Check API health at `http://127.0.0.1:8001/health`.
5. View logs using `docker compose logs -f api worker datumor-migrate`.

The migration service applies SQL migrations in filename order and records
successful migrations in `datumor_schema_migrations`.

### Manual installation

1. Install Python 3.12+, PostgreSQL and Redis.
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

3. Copy `.env.example` to `.env`.
4. Configure `DATUMOR_DB_USER`, `DATUMOR_DB_PASSWORD`, `DATUMOR_DB_NAME`,
   `DATUMOR_DB_HOST`, `DATUMOR_DB_PORT` and `DATUMOR_REDIS_URL`.
5. Run database migrations: `python scripts/migrate.py`.
6. Start the API with `scripts/start-api.ps1` on Windows or
   `bash scripts/start-api.sh` on Linux/macOS.
7. In another terminal, start the worker with `scripts/start-worker.ps1`
   or `bash scripts/start-worker.sh`.

   The Windows API startup script also runs migrations. Successful migrations
   are recorded and are not reapplied.

### Database migrations

The migration runner applies `migrations/sql/*.sql` in lexical order and
records successful migrations. Back up an existing database before migration.

### Local data

Staging files are stored under `data/staging` by default. Never commit `.env`,
customer uploads, generated reports or local database data.

## Verification Status

- Docker Compose deployment and end-to-end processing: verified.
- Non-root worker execution: verified.
- Fresh manual Windows installation: not yet verified.
- Fresh manual Linux installation: not yet verified.
- Production certification: not claimed.
## Documentation

- [API Reference](docs/API_REFERENCE.md)
- [Environment Variables](docs/ENVIRONMENT.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)

## License

DATUMOR is distributed under the Apache License, Version 2.0.

- SPDX identifier: `Apache-2.0`
- Full license text: [LICENSE](LICENSE)
- Official license: https://www.apache.org/licenses/LICENSE-2.0

Third-party components and dependencies may be subject to their own licenses and notices. See their respective distributions.
