import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


def get_redis_url(default_db: int = 1) -> str:
    raw_url = (
        os.getenv("DATUMOR_REDIS_URL")
        or os.getenv("REDIS_URL")
        or f"redis://localhost:6379/{default_db}"
    )
    password = os.getenv("DATUMOR_REDIS_PASSWORD") or os.getenv("REDIS_PASSWORD")

    parts = urlsplit(raw_url)
    if not password or parts.password is not None:
        return raw_url

    username = parts.username or ""
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    host = parts.hostname or "localhost"
    if parts.port:
        host = f"{host}:{parts.port}"

    return urlunsplit((
        parts.scheme,
        auth + host,
        parts.path or f"/{default_db}",
        parts.query,
        parts.fragment,
    ))
