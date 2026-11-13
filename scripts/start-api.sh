#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "DATUMOR Python environment not found: $PYTHON" >&2
    echo "Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON" -m uvicorn apps.api.app.main:app \
    --host "${DATUMOR_API_HOST:-0.0.0.0}" \
    --port "${DATUMOR_API_PORT:-8000}"