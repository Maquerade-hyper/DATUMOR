from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from apps.api.app.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    units: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        index=True, nullable=False
    )
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class UsagePolicy(Base):
    __tablename__ = "usage_policies"

    policy_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    deployment_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="community")
    monthly_job_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    monthly_ingestion_bytes_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=5368709120
    )
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String(36))
