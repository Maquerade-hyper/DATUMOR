"""Deterministic duplicate detection for DATUMOR DUKR documents."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations

DETECTOR_VERSION = "0.1.0"
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.90
MAX_DOCUMENTS = 500
MAX_CONTENT_CHARACTERS = 2_000_000


def _normalize(content: str) -> str:
    """Normalize Unicode, casing, punctuation and whitespace."""
    content = unicodedata.normalize("NFKC", content).casefold()
    content = re.sub(r"[^\w\s]", " ", content, flags=re.UNICODE)
    return " ".join(content.split())


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _document_identity(dukr: dict, index: int) -> dict:
    source = dukr.get("source") or {}
    content = source.get("original_content")

    if not isinstance(content, str):
        raise ValueError(
            f"Document at index {index} has no string source.original_content."
        )

    if len(content) > MAX_CONTENT_CHARACTERS:
        raise ValueError(
            f"Document at index {index} exceeds the "
            f"{MAX_CONTENT_CHARACTERS}-character comparison limit."
        )

    source_id = source.get("source_id")
    project_id = source.get("project_id")

    return {
        "document_index": index,
        "representation_id": dukr.get("representation_id"),
        "source_id": source_id,
        "project_id": project_id,
        "filename": source.get("filename"),
        "path": source.get("path"),
        "checksum_sha256": source.get("checksum_sha256"),
        "content": content,
        "content_sha256": _content_hash(content),
        "normalized_content": _normalize(content),
    }


def _similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    return round(
        SequenceMatcher(None, left, right, autojunk=True).ratio(),
        6,
    )


def _same_source(left: dict, right: dict) -> bool:
    left_id = left.get("source_id")
    right_id = right.get("source_id")

    return (
        left_id is not None
        and right_id is not None
        and left_id == right_id
    )


def _cross_source(left: dict, right: dict) -> bool:
    return not _same_source(left, right)


def _pair_result(
    left: dict,
    right: dict,
    method: str,
    similarity: float,
) -> dict:
    return {
        "left": {
            "document_index": left["document_index"],
            "representation_id": left["representation_id"],
            "source_id": left["source_id"],
            "project_id": left["project_id"],
            "filename": left["filename"],
            "path": left["path"],
            "checksum_sha256": left["checksum_sha256"],
            "content_sha256": left["content_sha256"],
        },
        "right": {
            "document_index": right["document_index"],
            "representation_id": right["representation_id"],
            "source_id": right["source_id"],
            "project_id": right["project_id"],
            "filename": right["filename"],
            "path": right["path"],
            "checksum_sha256": right["checksum_sha256"],
            "content_sha256": right["content_sha256"],
        },
        "detection_method": method,
        "similarity": similarity,
        "cross_source": _cross_source(left, right),
        "same_project": (
            left["project_id"] is not None
            and left["project_id"] == right["project_id"]
        ),
        "originals_modified": False,
        "review_required": method == "near_duplicate",
    }


def detect_duplicates(
    dukr_documents: list[dict],
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> dict:
    """Detect exact, normalized and near duplicates across DUKR documents."""
    if not isinstance(dukr_documents, list):
        raise TypeError("dukr_documents must be a list.")

    if len(dukr_documents) > MAX_DOCUMENTS:
        raise ValueError(
            f"At most {MAX_DOCUMENTS} documents can be compared per call."
        )

    if not isinstance(near_duplicate_threshold, (int, float)):
        raise TypeError("near_duplicate_threshold must be numeric.")

    if not 0.0 < near_duplicate_threshold <= 1.0:
        raise ValueError(
            "near_duplicate_threshold must be greater than 0 and at most 1."
        )

    documents = []
    for index, dukr in enumerate(dukr_documents):
        if not isinstance(dukr, dict):
            raise TypeError(f"Document at index {index} must be a dictionary.")

        if dukr.get("dukr_schema") != "datumor.dukr":
            raise ValueError(
                f"Document at index {index} has an unsupported DUKR schema."
            )

        documents.append(_document_identity(dukr, index))

    matches = []
    parent = list(range(len(documents)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, right_index in combinations(range(len(documents)), 2):
        left = documents[left_index]
        right = documents[right_index]

        # A source compared with another DUKR representation of itself
        # is not a cross-source duplicate.
        if _same_source(left, right):
            continue

        if left["content_sha256"] == right["content_sha256"]:
            match = _pair_result(left, right, "exact", 1.0)

        elif (
            left["normalized_content"]
            and left["normalized_content"] == right["normalized_content"]
        ):
            match = _pair_result(left, right, "normalized", 1.0)

        else:
            similarity = _similarity(
                left["normalized_content"],
                right["normalized_content"],
            )

            if similarity < near_duplicate_threshold:
                continue

            match = _pair_result(
                left, right, "near_duplicate", similarity
            )

        matches.append(match)
        union(left_index, right_index)

    # Group connected duplicate candidates without modifying their sources.
    grouped_indices: dict[int, list[int]] = {}
    for match in matches:
        left_index = match["left"]["document_index"]
        right_index = match["right"]["document_index"]
        root = find(left_index)
        grouped_indices.setdefault(root, [])
        for index in (left_index, right_index):
            if index not in grouped_indices[root]:
                grouped_indices[root].append(index)

    group_by_index = {}
    groups = []

    for root, indices in grouped_indices.items():
        indices.sort()
        material = "|".join(
            documents[index]["content_sha256"] for index in indices
        )
        group_id = "duplicate_" + hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()[:20]

        group = {
            "duplicate_group_id": group_id,
            "document_indices": indices,
            "source_ids": list(dict.fromkeys(
                documents[index]["source_id"]
                for index in indices
                if documents[index]["source_id"] is not None
            )),
            "document_count": len(indices),
        }
        groups.append(group)

        for index in indices:
            group_by_index[index] = group_id

    for match in matches:
        match["duplicate_group_id"] = group_by_index[
            match["left"]["document_index"]
        ]

    method_counts = {
        method: sum(
            match["detection_method"] == method for match in matches
        )
        for method in ("exact", "normalized", "near_duplicate")
    }

    return {
        "report_schema": "datumor.duplicate_report",
        "detector_version": DETECTOR_VERSION,
        "threshold": near_duplicate_threshold,
        "summary": {
            "documents_analyzed": len(documents),
            "duplicate_pairs": len(matches),
            "duplicate_groups": len(groups),
            "exact_matches": method_counts["exact"],
            "normalized_matches": method_counts["normalized"],
            "near_duplicate_matches": method_counts["near_duplicate"],
            "cross_source_matches": sum(
                match["cross_source"] for match in matches
            ),
            "originals_modified": False,
        },
        "matches": matches,
        "groups": groups,
        "warnings": [
            "Near-duplicate matches are candidates and require review.",
            "Duplicate detection does not delete, merge or rewrite source data.",
            "Similarity is character-sequence similarity over normalized text.",
            "Documents sharing a non-null source_id are not compared with each other.",
        ],
    }
