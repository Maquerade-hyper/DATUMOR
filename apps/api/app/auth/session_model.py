from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    __table_args__ = (
        Index(
            "ix_auth_sessions_user_active",
            "user_id",
            "expires_at",
        ),
        Index("ix_auth_sessions_family", "family_id"),
        Index("ix_auth_sessions_expiry", "expires_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
