import csv
import io
import json
from pathlib import Path

SIGNATURES = (
    (b"%PDF-", "pdf", "application/pdf", "document"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png", "image"),
    (b"\xff\xd8\xff", "jpeg", "image/jpeg", "image"),
    (b"GIF87a", "gif", "image/gif", "image"),
    (b"GIF89a", "gif", "image/gif", "image"),
    (b"RIFF", "riff", None, "media"),
    (b"fLaC", "flac", "audio/flac", "audio"),
    (b"OggS", "ogg", "application/ogg", "audio"),
    (b"PK\x03\x04", "zip", "application/zip", "archive"),
    (b"\x1f\x8b", "gzip", "application/gzip", "archive"),
)

EXTENSIONS = {
    ".pdf": ("pdf", "application/pdf", "document"),
    ".txt": ("text", "text/plain", "text"),
    ".md": ("markdown", "text/markdown", "text"),
    ".markdown": ("markdown", "text/markdown", "text"),
    ".json": ("json", "application/json", "structured"),
    ".jsonl": ("jsonl", "application/x-ndjson", "structured"),
    ".csv": ("csv", "text/csv", "structured"),
    ".py": ("python", "text/x-python", "code"),
    ".js": ("javascript", "text/javascript", "code"),
    ".ts": ("typescript", "text/typescript", "code"),
    ".tsx": ("tsx", "text/tsx", "code"),
    ".jsx": ("jsx", "text/jsx", "code"),
    ".html": ("html", "text/html", "code"),
    ".css": ("css", "text/css", "code"),
    ".sql": ("sql", "application/sql", "code"),
    ".yaml": ("yaml", "application/yaml", "structured"),
    ".yml": ("yaml", "application/yaml", "structured"),
    ".xml": ("xml", "application/xml", "structured"),
    ".toml": ("toml", "application/toml", "structured"),
    ".png": ("png", "image/png", "image"),
    ".jpg": ("jpeg", "image/jpeg", "image"),
    ".jpeg": ("jpeg", "image/jpeg", "image"),
    ".gif": ("gif", "image/gif", "image"),
    ".webp": ("webp", "image/webp", "image"),
    ".wav": ("wav", "audio/wav", "audio"),
    ".mp3": ("mp3", "audio/mpeg", "audio"),
    ".flac": ("flac", "audio/flac", "audio"),
    ".ogg": ("ogg", "application/ogg", "audio"),
    ".mp4": ("mp4", "video/mp4", "video"),
    ".mov": ("mov", "video/quicktime", "video"),
    ".mkv": ("mkv", "video/x-matroska", "video"),
    ".webm": ("webm", "video/webm", "video"),
    ".parquet": ("parquet", "application/vnd.apache.parquet", "structured"),
}


def _result(fmt, media_type, category, method, confidence, extension,
            warnings=None):
    return {
        "format": fmt,
        "media_type": media_type,
        "category": category,
        "detection_method": method,
        "confidence": confidence,
        "extension": extension or None,
        "extension_matches": (
            None if not extension or fmt == "unknown"
            else EXTENSIONS.get(extension, (None,))[0] == fmt
        ),
        "warnings": warnings or [],
    }


def _detect_text(text, extension):
    stripped = text.strip()
    if not stripped:
        return None

    try:
        json.loads(stripped)
        return ("json", "application/json", "structured", "content", 0.99)
    except (ValueError, TypeError):
        pass

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) >= 2:
        try:
            for line in lines:
                json.loads(line)
            return ("jsonl", "application/x-ndjson", "structured",
                    "content", 0.98)
        except (ValueError, TypeError):
            pass

    if extension in {".md", ".markdown"}:
        return ("markdown", "text/markdown", "text", "extension+content", 0.95)

    if extension in EXTENSIONS:
        fmt, media, category = EXTENSIONS[extension]
        if category in {"code", "structured"}:
            return (fmt, media, category, "extension+content", 0.90)

    if len(lines) >= 2:
        try:
            sample = "\n".join(lines[:20])
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            rows = list(csv.reader(io.StringIO(sample), dialect))
            if len(rows) >= 2 and len(rows[0]) > 1:
                return ("csv", "text/csv", "structured", "content", 0.90)
        except csv.Error:
            pass

    if extension in {".txt", ".text"}:
        return ("text", "text/plain", "text", "extension+content", 0.95)

    return ("text", "text/plain", "text", "content", 0.80)


def detect_format(path, original_filename=None, declared_media_type=None):
    path = Path(path)
    extension = Path(original_filename or path.name).suffix.lower()

    with path.open("rb") as file:
        data = file.read(65536)

    warnings = []

    if not data:
        return _result(
            "empty", "application/x-empty", "unknown",
            "content", 1.0, extension,
        )

    for signature, fmt, media, category in SIGNATURES:
        if data.startswith(signature):
            if fmt == "riff":
                if data[8:12] == b"WAVE":
                    fmt, media, category = "wav", "audio/wav", "audio"
                elif data[8:12] == b"WEBP":
                    fmt, media, category = "webp", "image/webp", "image"
                else:
                    fmt, media, category = "riff", "application/octet-stream", "media"
            return _result(
                fmt, media, category, "signature", 0.99, extension,
                ["File extension does not match detected content."]
                if extension in EXTENSIONS
                and EXTENSIONS[extension][0] != fmt else [],
            )

    if len(data) >= 12 and data[4:8] == b"ftyp":
        fmt = "mp4"
        media = "video/mp4"
        if extension == ".mov":
            fmt, media = "mov", "video/quicktime"
        return _result(fmt, media, "video", "signature", 0.99, extension)

    if data.startswith(b"\x1aE\xdf\xa3"):
        return _result("mkv", "video/x-matroska", "video",
                       "signature", 0.99, extension)

    if data.startswith(b"PAR1"):
        return _result("parquet", "application/vnd.apache.parquet",
                       "structured", "signature", 0.99, extension)

    if data.startswith(b"ID3") or (
        len(data) > 1 and data[0] == 0xff and data[1] & 0xe0 == 0xe0
    ):
        return _result("mp3", "audio/mpeg", "audio",
                       "signature", 0.95, extension)

    if b"\x00" not in data:
        try:
            text = data.decode("utf-8-sig")
            detected = _detect_text(text, extension)
            if detected:
                fmt, media, category, method, confidence = detected
                if extension in EXTENSIONS and EXTENSIONS[extension][0] != fmt:
                    warnings.append(
                        f"Extension suggests {EXTENSIONS[extension][0]}, "
                        f"but content suggests {fmt}."
                    )
                return _result(
                    fmt, media, category, method, confidence,
                    extension, warnings,
                )
        except UnicodeDecodeError:
            pass

    if extension in EXTENSIONS:
        fmt, media, category = EXTENSIONS[extension]
        warnings.append("Content could not confirm the declared extension.")
        return _result(fmt, media, category, "extension_only",
                       0.40, extension, warnings)

    return _result(
        "unknown", "application/octet-stream", "unknown",
        "content", 0.20, extension,
        ["Format could not be identified."],
    )
