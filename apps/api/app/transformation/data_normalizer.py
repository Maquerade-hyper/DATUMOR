"""Read-only, provenance-preserving dataset normalization."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
from typing import Any


REPORT_TYPE = "datumor.normalization_result"
REPORT_VERSION = "1.0.0"

_CODE_KEYS = {
    "code", "source_code", "snippet", "program", "script",
    "query", "sql", "command", "raw_code",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str, mode: str, *, code_sensitive: bool = False) -> tuple[str, list[str]]:
    if mode == "none":
        return value, []

    result = value
    operations = []

    normalized = unicodedata.normalize("NFC", result)
    if normalized != result:
        operations.append("unicode_nfc")
        result = normalized

    normalized = result.replace("\r\n", "\n").replace("\r", "\n")
    if normalized != result:
        operations.append("line_endings_lf")
        result = normalized

    lines = result.split("\n")
    trimmed = [line.rstrip(" \t") for line in lines]
    if trimmed != lines:
        operations.append("trim_trailing_line_whitespace")
        result = "\n".join(trimmed)

    if mode == "standard" and not code_sensitive:
        lines = result.split("\n")
        collapsed = [re.sub(r"[ \t]+", " ", line) for line in lines]
        if collapsed != lines:
            operations.append("collapse_horizontal_whitespace")
            result = "\n".join(collapsed)

        limited = re.sub(r"\n{3,}", "\n\n", result)
        if limited != result:
            operations.append("limit_consecutive_blank_lines")
            result = limited

    return result, operations


def _normalize_value(
    value: Any,
    mode: str,
    path: str,
    changes: list[dict],
    *,
    code_sensitive: bool = False,
) -> Any:
    if isinstance(value, str):
        normalized, operations = _normalize_text(
            value, mode, code_sensitive=code_sensitive
        )
        if normalized != value:
            changes.append({
                "path": path,
                "operations": operations,
                "before_sha256": _sha256(value),
                "after_sha256": _sha256(normalized),
                "changed": True,
            })
        return normalized

    if isinstance(value, list):
        return [
            _normalize_value(
                item,
                mode,
                f"{path}[{index}]",
                changes,
                code_sensitive=code_sensitive,
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            key_is_code = isinstance(key, str) and key.lower() in _CODE_KEYS
            normalized[key] = _normalize_value(
                item,
                mode,
                f"{path}.{key}",
                changes,
                code_sensitive=code_sensitive or key_is_code,
            )
        return normalized

    return deepcopy(value)


def normalize_dukr(dukr: dict, profile: dict) -> dict:
    """Create a normalized derived artifact without mutating the DUKR."""

    if not isinstance(dukr, dict):
        raise TypeError("dukr must be a dictionary")

    if not isinstance(profile, dict):
        raise TypeError("profile must be a dictionary")

    from apps.api.app.transformation.profile_registry import validate_profile

    validation = validate_profile(profile)
    if not validation["valid"]:
        raise ValueError(
            "Invalid transformation profile: " + "; ".join(validation["errors"])
        )

    mode = profile["normalization"]["mode"]
    source = dukr.get("source")
    if not isinstance(source, dict):
        raise ValueError("DUKR source object is required")

    original_content = source.get("original_content")
    if original_content is not None and not isinstance(original_content, str):
        raise ValueError("DUKR source.original_content must be a string or null")

    changes: list[dict] = []
    normalized_content = None
    if original_content is not None:
        normalized_content = _normalize_value(
            original_content,
            mode,
            "source.original_content",
            changes,
        )

    source_records = source.get("source_records", [])
    if source_records is None:
        source_records = []
    if not isinstance(source_records, list):
        raise ValueError("DUKR source.source_records must be a list")

    normalized_records = _normalize_value(
        source_records,
        mode,
        "source.source_records",
        changes,
    )

    source_identity = {
        "source_id": source.get("source_id"),
        "project_id": source.get("project_id"),
        "filename": source.get("filename"),
        "checksum_sha256": source.get("checksum_sha256"),
        "content_sha256": source.get("content_sha256"),
    }

    original_hash = (
        _sha256(original_content) if original_content is not None else None
    )
    normalized_hash = (
        _sha256(normalized_content) if normalized_content is not None else None
    )

    return {
        "report_type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["version"],
            "normalization_mode": mode,
        },
        "source": source_identity,
        "normalized_data": {
            "content": normalized_content,
            "records": normalized_records,
        },
        "integrity": {
            "original_content_sha256": original_hash,
            "normalized_content_sha256": normalized_hash,
            "original_content_length": (
                len(original_content) if original_content is not None else None
            ),
            "normalized_content_length": (
                len(normalized_content) if normalized_content is not None else None
            ),
            "source_checksum_preserved": source.get("checksum_sha256"),
            "source_content_hash_preserved": source.get("content_sha256"),
        },
        "change_summary": {
            "changed_values": len(changes),
            "changed": bool(changes),
            "operations": sorted({
                operation
                for change in changes
                for operation in change["operations"]
            }),
        },
        "changes": changes,
        "warnings": validation["warnings"],
        "automatic_source_changes": False,
    }
