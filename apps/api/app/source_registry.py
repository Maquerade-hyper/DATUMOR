"""Concurrency-safe canonical source claims for exact-content fingerprints."""
import hashlib
import json
import re
import uuid
from pathlib import Path

from sqlalchemy import Column, ForeignKey, String, Table, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.app.database import Base
from apps.api.app.source_model import Source

# A separate claim table lets historical duplicate source records remain intact.
# Only one canonical claim can exist per (source_type, SHA-256).
fingerprint_claims = Table(
    "fingerprint_claims", Base.metadata,
    Column("source_type", String(30), primary_key=True),
    Column("checksum_sha256", String(64), primary_key=True),
    Column("source_id", ForeignKey("sources.source_id", ondelete="RESTRICT"), nullable=False),
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_manifest_sha256(root: Path) -> str:
    root = Path(root)
    entries = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        entries.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": file_sha256(path),
            "size": path.stat().st_size,
        })
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_fingerprint(source_type: str, checksum: str):
    if not source_type or len(source_type) > 30:
        raise ValueError("Invalid source type")
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Invalid SHA-256 fingerprint")


def initialize_fingerprint_claims(db: Session):
    """Idempotently backfill canonical claims without deleting historical sources."""
    # Called at startup after the Source table exists. DDL is idempotent.
    fingerprint_claims.create(bind=db.get_bind(), checkfirst=True)
    # Existing duplicates: oldest source is canonical, then smallest UUID.
    # ON CONFLICT protects repeated startup and parallel service startup.
    db.execute(text("""
        INSERT INTO fingerprint_claims (source_type, checksum_sha256, source_id)
        SELECT DISTINCT ON (source_type, checksum_sha256)
            source_type, checksum_sha256, source_id
        FROM sources
        WHERE checksum_sha256 ~ '^[0-9a-f]{64}$'
        ORDER BY source_type, checksum_sha256, created_at ASC, source_id ASC
        ON CONFLICT (source_type, checksum_sha256) DO NOTHING
    """))
    db.commit()


def register_source_with_duplicate_info(
    db: Session, *, source_id: str, source_type: str, source_name: str,
    checksum_sha256: str, uri: str, media_type: str | None,
    size_bytes: int, metadata: dict,
    project_id: uuid.UUID | str | None = None,
) -> tuple[Source, bool]:
    """Atomically claim a fingerprint; return (canonical source, duplicate)."""
    _validate_fingerprint(source_type, checksum_sha256)
    parsed_id = uuid.UUID(source_id)
    parsed_project_id = (
        uuid.UUID(str(project_id)) if project_id is not None else None
    )
    # PostgreSQL transaction-scoped advisory lock serializes contenders.
    # Lock key derived from type+hash; collisions only reduce concurrency.
    lock_digest = hashlib.sha256(f"{source_type}:{checksum_sha256}".encode()).digest()
    lock_key = int.from_bytes(lock_digest[:8], "big", signed=True)
    uploaded_object_key = None
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        claimed = db.execute(
            select(fingerprint_claims.c.source_id).where(
                fingerprint_claims.c.source_type == source_type,
                fingerprint_claims.c.checksum_sha256 == checksum_sha256,
            )
        ).scalar_one_or_none()
        if claimed is not None:
            canonical = db.get(Source, claimed)
            if canonical is None:
                raise RuntimeError("Fingerprint claim references a missing source")
            if parsed_project_id is not None:
                if canonical.project_id is None:
                    canonical.project_id = parsed_project_id
                elif canonical.project_id != parsed_project_id:
                    raise ValueError(
                        "This exact source already belongs to another project; "
                        "cross-project duplicate reuse is not supported yet."
                    )
            db.commit()
            return canonical, canonical.source_id != parsed_id

        existing = db.get(Source, parsed_id)
        if existing is not None:
            if existing.source_type != source_type or existing.checksum_sha256 != checksum_sha256:
                raise ValueError("Source ID is already registered with different content")
            source = existing
            if parsed_project_id is not None:
                if source.project_id is None:
                    source.project_id = parsed_project_id
                elif source.project_id != parsed_project_id:
                    raise ValueError(
                        "Source is already associated with a different project."
                    )
        else:
            source = Source(
                source_id=parsed_id, project_id=parsed_project_id,
                source_type=source_type, source_name=source_name,
                checksum_sha256=checksum_sha256, uri=uri, media_type=media_type,
                size_bytes=size_bytes, metadata_json=metadata, status="staged",
            )

        # Store content before committing its source record.
        # The duplicate claim check above guarantees duplicate requests
        # return without performing another object upload.
        source_metadata = dict(source.metadata_json or {})
        storage_info = source_metadata.get("object_storage")

        if not storage_info or not storage_info.get("verified"):
            from apps.api.app.ingestion.object_storage import store_source

            storage_info = store_source(
                source_id=str(source.source_id),
                source_type=source_type,
                uri=source.uri,
                expected_fingerprint=checksum_sha256,
            )
            uploaded_object_key = storage_info["object_key"]

            source_metadata["object_storage"] = storage_info
            source.metadata_json = source_metadata

        if existing is None:
            db.add(source)
            db.flush()
        db.execute(pg_insert(fingerprint_claims).values(
            source_type=source_type, checksum_sha256=checksum_sha256,
            source_id=source.source_id,
        ).on_conflict_do_nothing(index_elements=["source_type", "checksum_sha256"]))
        db.commit()
        db.refresh(source)
        return source, False
    except Exception:
        db.rollback()

        # A commit error can be ambiguous: PostgreSQL may have committed
        # even if the client did not receive confirmation. Only delete the
        # object when a fresh ORM lookup confirms the source is absent.
        if uploaded_object_key:
            source_absent = False

            try:
                persisted_source = db.get(Source, parsed_id)
                source_absent = persisted_source is None
            except Exception:
                # Database state is uncertain. Preserve the object rather
                # than risk deleting content referenced by a committed row.
                source_absent = False

            if source_absent:
                try:
                    from apps.api.app.ingestion.object_storage import (
                        delete_source_object,
                    )
                    delete_source_object(uploaded_object_key)
                except Exception:
                    # Cleanup failure leaves an orphan object, which is
                    # safer than deleting a potentially referenced object.
                    import logging
                    logging.getLogger(__name__).exception(
                        "Failed to clean up orphaned storage object: %s",
                        uploaded_object_key,
                    )

        raise


def register_source(db: Session, **kwargs) -> Source:
    """Compatibility wrapper for existing callers."""
    return register_source_with_duplicate_info(db, **kwargs)[0]


def serialize_source(source: Source) -> dict:
    return {
        "source_id": str(source.source_id),
        "project_id": str(source.project_id) if source.project_id else None,
        "source_type": source.source_type,
        "source_name": source.source_name,
        "media_type": source.media_type,
        "checksum_sha256": source.checksum_sha256,
        "uri": source.uri,
        "size_bytes": source.size_bytes,
        "status": source.status,
        "metadata": source.metadata_json,
        "created_at": source.created_at.isoformat(),
    }
