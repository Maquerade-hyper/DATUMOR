import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Integer, JSON, String, Text, Uuid, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.database import Base


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="staged"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_sources_type_created", "source_type", "created_at"),
    )
