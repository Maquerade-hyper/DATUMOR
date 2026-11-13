from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from apps.api.app.exporting.export_config import (
    validate_export_configuration,
)


class DatasetExportError(ValueError):
    """Raised when dataset serialization or export fails."""


class DatasetExportIntegrityError(DatasetExportError):
    """Raised when exported content fails integrity verification."""


def _strict_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        )
        return serialized.encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DatasetExportError(
            f"Dataset contains values that cannot be serialized as JSON: {exc}"
        ) from exc


def _validate_dataset(dataset: dict) -> None:
    if not isinstance(dataset, dict):
        raise DatasetExportError("Dataset must be a dictionary.")

    if "examples" in dataset and not isinstance(dataset["examples"], list):
        raise DatasetExportError("Dataset examples must be a list.")

    if "examples" in dataset:
        for index, example in enumerate(dataset["examples"]):
            if not isinstance(example, dict):
                raise DatasetExportError(
                    f"Dataset example at index {index} must be an object."
                )


def _dataset_for_export(dataset: dict, *, include_metadata: bool,
                        include_provenance: bool) -> dict:
    exported = dict(dataset)

    if not include_metadata:
        exported = {
            key: value for key, value in exported.items()
            if key == "examples"
        }

    examples = dataset.get("examples")
    if isinstance(examples, list):
        exported_examples = []
        for example in examples:
            item = dict(example)
            if not include_provenance:
                item.pop("provenance", None)
            exported_examples.append(item)
        exported["examples"] = exported_examples

    return exported


def _build_manifest(
    dataset: dict,
    *,
    filename: str,
    export_format: str,
    artifact_sha256: str,
    artifact_size_bytes: int,
    example_count: int,
    include_metadata: bool,
    include_provenance: bool,
) -> dict:
    metadata = {
        key: value for key, value in dataset.items()
        if key != "examples"
    } if include_metadata else {}

    provenance = []
    if include_provenance:
        for index, example in enumerate(dataset.get("examples", [])):
            if "provenance" not in example:
                continue
            entry = {"provenance": example["provenance"]}
            if "example_id" in example:
                entry["example_id"] = example["example_id"]
            else:
                entry["example_index"] = index
            provenance.append(entry)

    return {
        "manifest_type": "datumor.export_manifest",
        "manifest_version": "1.0.0",
        "artifact": {
            "filename": filename,
            "format": export_format,
            "sha256": artifact_sha256,
            "size_bytes": artifact_size_bytes,
            "example_count": example_count,
        },
        "inclusion": {
            "metadata": include_metadata,
            "provenance": include_provenance,
        },
        "dataset_metadata": metadata,
        "example_provenance": provenance,
    }


def _serialize_json(dataset: dict) -> tuple[bytes, int]:
    return (
        _strict_json_bytes(dataset, pretty=True),
        len(dataset.get("examples", [])),
    )


def _serialize_jsonl(dataset: dict) -> tuple[bytes, int]:
    examples = dataset.get("examples")
    if not isinstance(examples, list):
        raise DatasetExportError(
            "JSONL export requires a dataset examples list."
        )

    lines = [_strict_json_bytes(example) for example in examples]
    if not lines:
        return b"", 0
    return b"\n".join(lines) + b"\n", len(lines)


def _serialize_parquet(dataset: dict) -> tuple[bytes, int]:
    examples = dataset.get("examples")
    if not isinstance(examples, list):
        raise DatasetExportError(
            "Parquet export requires a dataset examples list."
        )

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise DatasetExportError(
            "Parquet export requires the installed PyArrow dependency."
        ) from exc

    try:
        table = pa.Table.from_pylist(examples)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return sink.getvalue().to_pybytes(), len(examples)
    except (pa.ArrowException, TypeError, ValueError) as exc:
        raise DatasetExportError(
            f"Unable to serialize dataset examples to Parquet: {exc}"
        ) from exc


def _calculate_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DatasetExportIntegrityError(
            f"Unable to read exported file for integrity verification: {exc}"
        ) from exc
    return digest.hexdigest()


def _atomic_write(output_path: Path, content: bytes, *, overwrite: bool) -> dict:
    """Stage, verify, and atomically publish an export file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_hash = _calculate_sha256(content)
    temp_path: Path | None = None

    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=str(output_path.parent),
        )
        temp_path = Path(temp_name)

        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if _file_sha256(temp_path) != expected_hash:
            raise DatasetExportIntegrityError(
                "Temporary export checksum does not match serialized content."
            )

        if overwrite:
            os.replace(temp_path, output_path)
            temp_path = None
        else:
            try:
                os.link(temp_path, output_path)
            except FileExistsError as exc:
                raise DatasetExportError(
                    f"Export file already exists: {output_path.name}"
                ) from exc
            except OSError as exc:
                raise DatasetExportError(
                    "Atomic no-overwrite publication failed. "
                    f"The destination filesystem must support hard links: {exc}"
                ) from exc
            temp_path.unlink()
            temp_path = None

        final_hash = _file_sha256(output_path)
        if final_hash != expected_hash:
            raise DatasetExportIntegrityError(
                "Published export checksum does not match expected content."
            )

        return {
            "content_sha256": final_hash,
            "integrity_verified": True,
            "atomic_write": True,
        }
    except DatasetExportError:
        raise
    except OSError as exc:
        raise DatasetExportError(
            f"Atomic export operation failed: {exc}"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def export_dataset(dataset: dict, output_dir: str | Path,
                   configuration: dict) -> dict:
    """Export a dataset and a checksummed metadata/provenance manifest."""
    _validate_dataset(dataset)
    config = validate_export_configuration(configuration)

    output_directory = Path(output_dir).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / config["filename"]
    manifest_path = output_directory / f"{output_path.name}.manifest.json"

    if output_path.parent != output_directory:
        raise DatasetExportError("Export path escaped the output directory.")

    if not config["overwrite"]:
        if output_path.exists():
            raise DatasetExportError(
                f"Export file already exists: {output_path.name}"
            )
        if manifest_path.exists():
            raise DatasetExportError(
                f"Export manifest already exists: {manifest_path.name}"
            )

    export_dataset_content = _dataset_for_export(
        dataset,
        include_metadata=config["include_metadata"],
        include_provenance=config["include_provenance"],
    )

    serializers = {
        "json": _serialize_json,
        "jsonl": _serialize_jsonl,
        "parquet": _serialize_parquet,
    }
    content, example_count = serializers[config["format"]](
        export_dataset_content
    )

    artifact_integrity = _atomic_write(
        output_path,
        content,
        overwrite=config["overwrite"],
    )

    manifest = _build_manifest(
        dataset,
        filename=output_path.name,
        export_format=config["format"],
        artifact_sha256=artifact_integrity["content_sha256"],
        artifact_size_bytes=len(content),
        example_count=example_count,
        include_metadata=config["include_metadata"],
        include_provenance=config["include_provenance"],
    )
    manifest_content = _strict_json_bytes(manifest, pretty=True)

    # Publish the manifest last. Its presence indicates that the artifact
    # and its metadata/provenance manifest have both been published.
    manifest_integrity = _atomic_write(
        manifest_path,
        manifest_content,
        overwrite=config["overwrite"],
    )

    return {
        "success": True,
        "format": config["format"],
        "filename": output_path.name,
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "example_count": example_count,
        **artifact_integrity,
        "manifest_filename": manifest_path.name,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_integrity["content_sha256"],
        "manifest_integrity_verified": manifest_integrity["integrity_verified"],
        "metadata_included": config["include_metadata"],
        "provenance_included": config["include_provenance"],
    }
