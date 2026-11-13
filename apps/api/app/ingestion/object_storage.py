import hashlib
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config


def _client():
    endpoint = os.getenv("DATUMOR_S3_ENDPOINT", "http://127.0.0.1:8333")
    access_key = os.getenv("DATUMOR_S3_ACCESS_KEY")
    secret_key = os.getenv("DATUMOR_S3_SECRET_KEY")

    if not access_key or not secret_key:
        raise RuntimeError("DATUMOR S3 credentials are not configured.")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("DATUMOR_S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )


def _bucket():
    # Preserve the existing M0 storage configuration.
    bucket = os.getenv("DATUMOR_S3_BUCKET") or os.getenv("MINIO_BUCKET")
    if not bucket:
        raise RuntimeError(
            "Storage bucket is not configured. "
            "Set MINIO_BUCKET or DATUMOR_S3_BUCKET."
        )
    return bucket


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_directory(directory: Path):
    temporary = tempfile.NamedTemporaryFile(
        prefix="datumor-repository-",
        suffix=".tar.gz",
        delete=False,
    )
    temporary.close()
    archive_path = Path(temporary.name)

    try:
        with tarfile.open(archive_path, "w:gz") as archive:
            for item in sorted(directory.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    archive.add(
                        item,
                        arcname=item.relative_to(directory).as_posix(),
                        recursive=False,
                    )
        return archive_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


def store_source(
    source_id: str,
    source_type: str,
    uri: str,
    expected_fingerprint: str,
) -> dict[str, Any]:

    source_path = Path(uri).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source content not found: {source_path}")

    temporary_archive = None
    upload_path = source_path

    try:
        if source_path.is_dir():
            temporary_archive = _archive_directory(source_path)
            upload_path = temporary_archive

        if not upload_path.is_file():
            raise RuntimeError("Source must be a file or directory.")

        object_checksum = _sha256(upload_path)
        object_key = f"sources/{source_type}/{source_id}/content"

        client = _client()
        bucket = _bucket()
        try:
            client.upload_file(
                str(upload_path),
                bucket,
                object_key,
                ExtraArgs={
                    "Metadata": {
                        "source-id": source_id,
                        "source-type": source_type,
                        "sha256": object_checksum,
                        "source-fingerprint": expected_fingerprint,
                    }
                },
            )

            response = client.head_object(
                Bucket=bucket,
                Key=object_key,
            )

            if response.get("Metadata", {}).get("sha256") != object_checksum:
                raise RuntimeError("Object metadata verification failed.")

            downloaded = client.get_object(
                Bucket=bucket,
                Key=object_key,
            )

            digest = hashlib.sha256()

            for chunk in iter(
                lambda: downloaded["Body"].read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

            if digest.hexdigest() != object_checksum:
                raise RuntimeError("Stored object SHA-256 verification failed.")

        except Exception:
            import logging

            try:
                client.delete_object(Bucket=bucket, Key=object_key)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to clean up incomplete storage upload: %s",
                    object_key,
                )
            raise

        return {
            "backend": "seaweedfs-s3",
            "bucket": bucket,
            "object_key": object_key,
            "object_sha256": object_checksum,
            "source_fingerprint": expected_fingerprint,
            "object_size_bytes": upload_path.stat().st_size,
            "verified": True,
        }

    finally:
        if temporary_archive is not None:
            temporary_archive.unlink(missing_ok=True)


def retrieve_source(object_key: str, destination: Path):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    _client().download_file(
        _bucket(),
        object_key,
        str(destination),
    )

    return destination


def delete_source_object(object_key: str) -> None:
    """Delete an object created for a source whose DB registration failed."""
    if not object_key or object_key.startswith("/"):
        raise ValueError("Invalid object key")

    _client().delete_object(
        Bucket=_bucket(),
        Key=object_key,
    )
