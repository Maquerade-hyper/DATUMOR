import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METADATA_SCHEMA_VERSION = "1.0"


def _detect_encoding(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        try:
            data.decode("utf-16")
            return "utf-16"
        except UnicodeDecodeError:
            return "binary-or-unknown"


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def extract_metadata(
    path: str | Path,
    *,
    detected_format: str | None = None,
    content: Any = None,
    existing_metadata: dict | None = None,
    source_metadata: dict | None = None,
) -> dict:
    """Extract normalized file metadata without discarding parser metadata."""
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Metadata source does not exist: {path}")

    stat = path.stat()
    digest = hashlib.sha256()
    raw = bytearray()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
            raw.extend(chunk)

    data = bytes(raw)
    encoding = _detect_encoding(data)
    media_type, _ = mimetypes.guess_type(path.name)

    source = {
        "filename": path.name,
        "path": _relative_path(path),
        "extension": path.suffix.lower(),
        "format": detected_format or path.suffix.lower().lstrip("."),
        "media_type": media_type or "application/octet-stream",
        "size_bytes": stat.st_size,
        "checksum_sha256": digest.hexdigest(),
        "encoding": encoding,
        "created_at": datetime.fromtimestamp(
            stat.st_ctime, tz=timezone.utc
        ).isoformat(),
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
    }

    if isinstance(content, str):
        source["character_count"] = len(content)
        source["line_count"] = len(content.splitlines())
    elif isinstance(content, bytes):
        source["character_count"] = None
        source["line_count"] = None
    else:
        source["character_count"] = None
        source["line_count"] = None

    result = dict(existing_metadata or {})
    result["source"] = source

    if source_metadata:
        # Preserve supplied registry identity and provenance as a separate object.
        result["source_identity"] = dict(source_metadata)

    return result
