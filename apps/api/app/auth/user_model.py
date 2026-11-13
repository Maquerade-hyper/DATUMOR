from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.database import Base


class User(Base):
    """Customer and platform administrator identity."""

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('customer', 'admin', 'superadmin')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "length(email) BETWEEN 3 AND 320",
            name="ck_users_email_length",
        ),
        CheckConstraint(
            "length(email_normalized) BETWEEN 3 AND 320",
            name="ck_users_normalized_email_length",
        ),
        CheckConstraint(
            "email_normalized = lower(trim(email_normalized))",
            name="ck_users_normalized_email_format",
        ),
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_role_active", "role", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    email_normalized: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="customer",
        server_default=text("'customer'"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )

    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
