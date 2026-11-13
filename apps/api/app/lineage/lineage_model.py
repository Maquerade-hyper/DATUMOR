from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.database import Base


class LineageEventModel(Base):
    """Append-only persisted lineage event."""

    __tablename__ = "lineage_events"

    __table_args__ = (
        Index("ix_lineage_dataset_timestamp", "dataset_id", "timestamp"),
        Index(
            "ix_lineage_dataset_version",
            "dataset_id",
            "dataset_version",
        ),
        Index("ix_lineage_event_type", "event_type"),
        CheckConstraint(
            "dataset_version >= 1",
            name="ck_lineage_dataset_version_positive",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    contract_version: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        String(36), nullable=False
    )
    dataset_version: Mapped[int] = mapped_column(
        nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    actor: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    timestamp: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    input_references: Mapped[list] = mapped_column(
        JSON, nullable=False
    )
    output_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False
    )
