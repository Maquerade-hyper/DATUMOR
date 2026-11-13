# Contributing to DATUMOR

Thank you for your interest in contributing.

## Before making changes

1. Read the project README and architecture documentation.
2. Open an issue describing substantial changes before starting implementation.
3. Keep changes focused and compatible with the existing architecture.
4. Do not include private datasets, credentials, customer records, generated reports, or local environment files.

## Development setup

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and configure local services.
5. Apply database migrations using the documented migration command.
6. Start the API and worker using the scripts in `scripts/`.

See the README and `docs/ENVIRONMENT.md` for setup details.

## Tests

Run the test suite before submitting changes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For Linux:

```sh
.venv/bin/python -m pytest -q
```

Add or update tests when changing behavior. Do not report a test as passing unless it was actually run.

## Pull requests

Include:

- A clear problem statement and proposed solution.
- A summary of changed behavior and affected components.
- Tests executed and their actual results.
- Migration or configuration changes, if applicable.
- Known limitations and follow-up work.

Keep secrets and personal data out of commits, logs, screenshots, and test fixtures.