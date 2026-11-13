"""Reliable source lookup for the DATUMOR processing worker."""
import os
import uuid
from pathlib import Path
from sqlalchemy import MetaData, Table, inspect, select

class SourceResolutionError(RuntimeError):
    pass

def _coerce_uuid(value: str, column):
    column_type = column.type
    if getattr(column_type, "as_uuid", False):
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise SourceResolutionError("Invalid UUID supplied for source lookup.") from exc
    return str(value)

def resolve_source(engine, source_id: str, project_id: str):
    inspector = inspect(engine)
    if "sources" not in inspector.get_table_names():
        raise SourceResolutionError("DATUMOR sources table does not exist.")
    metadata = MetaData()
    table = Table("sources", metadata, autoload_with=engine)
    if not {"source_id", "project_id"}.issubset(table.c.keys()):
        raise SourceResolutionError("Source registry schema is incompatible.")
    source_value = _coerce_uuid(source_id, table.c.source_id)
    project_value = _coerce_uuid(project_id, table.c.project_id)
    with engine.connect() as conn:
        row = conn.execute(select(table).where(
            table.c.source_id == source_value,
            table.c.project_id == project_value,
        )).mappings().first()
    if not row:
        raise SourceResolutionError("Source not found in the requested project.")
    uri = row.get("uri")
    if uri:
        path = Path(str(uri)).expanduser()
        if path.is_file() or path.is_dir():
            return {
                "path": str(path.resolve()),
                "name": row.get("source_name") or path.name,
                "source_id": str(source_id),
                "media_type": row.get("media_type"),
                "size_bytes": row.get("size_bytes"),
                "checksum_sha256": row.get("checksum_sha256"),
                "metadata": row.get("metadata") or row.get("metadata_json") or {},
            }
    source_metadata = row.get("metadata") or row.get("metadata_json") or {}
    if not isinstance(source_metadata, dict):
        source_metadata = {}
    storage = source_metadata.get("object_storage") or {}
    object_key = storage.get("object_key")
    if object_key:
        return {
            "object_key": str(object_key),
            "name": row.get("source_name") or str(source_id),
            "source_id": str(source_id),
            "media_type": row.get("media_type"),
            "size_bytes": row.get("size_bytes"),
            "checksum_sha256": row.get("checksum_sha256"),
            "metadata": source_metadata,
        }
    raise SourceResolutionError("Source has no accessible staged file or object-storage key.")

def materialize_object(source: dict, destination: Path) -> Path:
    import boto3
    endpoint = os.getenv("DATUMOR_S3_ENDPOINT") or os.getenv("MINIO_ENDPOINT")
    access = os.getenv("DATUMOR_S3_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
    secret = os.getenv("DATUMOR_S3_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    bucket = os.getenv("DATUMOR_S3_BUCKET") or os.getenv("MINIO_BUCKET") or "datumor"
    if not endpoint or not access or not secret:
        raise SourceResolutionError("SeaweedFS credentials are not configured.")
    client = boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=access,
        aws_secret_access_key=secret, region_name="us-east-1",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, source["object_key"], str(destination))
    if not destination.is_file() or destination.stat().st_size == 0:
        raise SourceResolutionError("Object storage returned an empty or missing file.")
    return destination
