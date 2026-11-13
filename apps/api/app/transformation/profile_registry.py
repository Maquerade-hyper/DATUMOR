"""Versioned transformation profile registry for DATUMOR."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


PROFILE_SCHEMA_VERSION = "1.0.0"

ALLOWED_TASK_TYPES = {
    "general_llm",
    "coding",
    "research",
    "retrieval",
}

ALLOWED_OUTPUT_FORMATS = {
    "jsonl",
    "json",
    "parquet",
}

ALLOWED_NORMALIZATION_MODES = {
    "none",
    "conservative",
    "standard",
}

ALLOWED_CHUNKING_MODES = {
    "none",
    "fixed",
    "semantic",
}

PROFILE_FIELDS = {
    "profile_id",
    "name",
    "version",
    "task_type",
    "description",
    "output_format",
    "required_fields",
    "optional_fields",
    "quality_threshold",
    "include_source_metadata",
    "preserve_provenance",
    "deduplicate",
    "normalization",
    "chunking",
    "target_model",
    "schema_version",
    "custom",
}


_BUILTIN_PROFILES = {
    "general_llm": {
        "profile_id": "general_llm",
        "name": "General LLM",
        "version": "1.0.0",
        "task_type": "general_llm",
        "description": "General instruction and response training data.",
        "output_format": "jsonl",
        "required_fields": ["instruction", "response"],
        "optional_fields": ["input", "system"],
        "quality_threshold": 0.75,
        "include_source_metadata": True,
        "preserve_provenance": True,
        "deduplicate": True,
        "normalization": {"mode": "conservative"},
        "chunking": {"mode": "none", "max_tokens": None, "overlap_tokens": 0},
        "target_model": None,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "custom": False,
    },
    "coding": {
        "profile_id": "coding",
        "name": "Coding",
        "version": "1.0.0",
        "task_type": "coding",
        "description": "Code generation, debugging, explanation, and programming tasks.",
        "output_format": "jsonl",
        "required_fields": ["instruction", "response"],
        "optional_fields": ["input", "language", "code", "tests"],
        "quality_threshold": 0.85,
        "include_source_metadata": True,
        "preserve_provenance": True,
        "deduplicate": True,
        "normalization": {"mode": "conservative"},
        "chunking": {"mode": "none", "max_tokens": None, "overlap_tokens": 0},
        "target_model": None,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "custom": False,
    },
    "research": {
        "profile_id": "research",
        "name": "Research",
        "version": "1.0.0",
        "task_type": "research",
        "description": "Evidence-grounded research questions, answers, and explanations.",
        "output_format": "jsonl",
        "required_fields": ["question", "answer", "evidence"],
        "optional_fields": ["context", "citations", "limitations"],
        "quality_threshold": 0.90,
        "include_source_metadata": True,
        "preserve_provenance": True,
        "deduplicate": True,
        "normalization": {"mode": "conservative"},
        "chunking": {"mode": "semantic", "max_tokens": 2048, "overlap_tokens": 128},
        "target_model": None,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "custom": False,
    },
    "retrieval": {
        "profile_id": "retrieval",
        "name": "Retrieval",
        "version": "1.0.0",
        "task_type": "retrieval",
        "description": "Query and relevant-context training pairs for retrieval systems.",
        "output_format": "jsonl",
        "required_fields": ["query", "positive"],
        "optional_fields": ["negative", "metadata"],
        "quality_threshold": 0.85,
        "include_source_metadata": True,
        "preserve_provenance": True,
        "deduplicate": True,
        "normalization": {"mode": "conservative"},
        "chunking": {"mode": "semantic", "max_tokens": 1024, "overlap_tokens": 100},
        "target_model": None,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "custom": False,
    },
}


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate a profile definition without modifying it."""

    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(profile, dict):
        return {
            "valid": False,
            "errors": ["Profile must be a dictionary."],
            "warnings": [],
        }

    unknown = sorted(set(profile) - PROFILE_FIELDS)
    if unknown:
        _error(errors, f"Unknown profile fields: {', '.join(unknown)}")

    required = {
        "profile_id", "name", "version", "task_type", "description",
        "output_format", "required_fields", "optional_fields",
        "quality_threshold", "include_source_metadata",
        "preserve_provenance", "deduplicate", "normalization",
        "chunking", "target_model", "schema_version", "custom",
    }
    missing = sorted(required - set(profile))
    if missing:
        _error(errors, f"Missing required fields: {', '.join(missing)}")

    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]{1,63}", profile_id
    ):
        _error(errors, "profile_id must be a lowercase identifier using letters, numbers, and underscores.")

    for field in ("name", "description", "version", "schema_version"):
        value = profile.get(field)
        if not isinstance(value, str) or not value.strip():
            _error(errors, f"{field} must be a non-empty string.")

    if profile.get("task_type") not in ALLOWED_TASK_TYPES:
        _error(errors, "Unsupported task_type.")

    if profile.get("output_format") not in ALLOWED_OUTPUT_FORMATS:
        _error(errors, "Unsupported output_format.")

    for field in ("required_fields", "optional_fields"):
        value = profile.get(field)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            _error(errors, f"{field} must be a non-empty list of non-empty strings.")

    required_fields = profile.get("required_fields")
    optional_fields = profile.get("optional_fields")
    if isinstance(required_fields, list) and isinstance(optional_fields, list):
        if len(required_fields) != len(set(required_fields)):
            _error(errors, "required_fields contains duplicate entries.")
        if len(optional_fields) != len(set(optional_fields)):
            _error(errors, "optional_fields contains duplicate entries.")
        overlap = set(required_fields) & set(optional_fields)
        if overlap:
            _error(errors, f"Fields cannot be both required and optional: {', '.join(sorted(overlap))}")

    threshold = profile.get("quality_threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0 <= threshold <= 1
    ):
        _error(errors, "quality_threshold must be a number between 0 and 1.")

    for field in ("include_source_metadata", "preserve_provenance", "deduplicate", "custom"):
        if not isinstance(profile.get(field), bool):
            _error(errors, f"{field} must be a boolean.")

    normalization = profile.get("normalization")
    if not isinstance(normalization, dict):
        _error(errors, "normalization must be an object.")
    elif set(normalization) != {"mode"} or normalization.get("mode") not in ALLOWED_NORMALIZATION_MODES:
        _error(errors, "normalization must contain a supported mode only.")

    chunking = profile.get("chunking")
    if not isinstance(chunking, dict):
        _error(errors, "chunking must be an object.")
    else:
        if set(chunking) != {"mode", "max_tokens", "overlap_tokens"}:
            _error(errors, "chunking must contain mode, max_tokens, and overlap_tokens only.")
        mode = chunking.get("mode")
        if mode not in ALLOWED_CHUNKING_MODES:
            _error(errors, "Unsupported chunking mode.")
        max_tokens = chunking.get("max_tokens")
        overlap = chunking.get("overlap_tokens")
        if mode == "none":
            if max_tokens is not None or overlap != 0:
                _error(errors, "No-chunking mode requires max_tokens=null and overlap_tokens=0.")
        else:
            if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
                _error(errors, "Chunking max_tokens must be a positive integer.")
            if isinstance(overlap, bool) or not isinstance(overlap, int) or overlap < 0:
                _error(errors, "Chunking overlap_tokens must be a non-negative integer.")
            elif isinstance(max_tokens, int) and overlap >= max_tokens:
                _error(errors, "Chunking overlap_tokens must be smaller than max_tokens.")

    target_model = profile.get("target_model")
    if target_model is not None and (
        not isinstance(target_model, str) or not target_model.strip()
    ):
        _error(errors, "target_model must be null or a non-empty string.")

    if profile.get("preserve_provenance") is False:
        warnings.append("Disabling provenance preservation is not recommended for traceable datasets.")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def list_profiles() -> list[dict[str, Any]]:
    """Return independent copies of all built-in transformation profiles."""
    return [
        deepcopy(_BUILTIN_PROFILES[key])
        for key in sorted(_BUILTIN_PROFILES)
    ]


def get_profile(profile_id: str) -> dict[str, Any]:
    """Return a built-in profile by its identifier."""
    if not isinstance(profile_id, str) or profile_id not in _BUILTIN_PROFILES:
        raise KeyError(f"Unknown transformation profile: {profile_id}")
    return deepcopy(_BUILTIN_PROFILES[profile_id])


def create_custom_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a custom profile; does not persist it."""
    candidate = deepcopy(profile)
    candidate["custom"] = True

    result = validate_profile(candidate)
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))

    if candidate["profile_id"] in _BUILTIN_PROFILES:
        raise ValueError("Custom profile cannot overwrite a built-in profile.")

    return candidate
