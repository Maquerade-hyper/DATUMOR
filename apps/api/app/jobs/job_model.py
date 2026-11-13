from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Text, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from apps.api.app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_project_created", "project_id", "created_at"),
        Index("ix_processing_jobs_owner_status", "owner_user_id", "status"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(128))
    execution_id: Mapped[str | None] = mapped_column(String(128))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    pipeline: Mapped[str] = mapped_column(String(40), nullable=False, default="standard")
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(80), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProcessingJobEvent(Base):
    __tablename__ = "processing_job_events"
    __table_args__ = (
        Index("ix_processing_job_events_job_created", "job_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_jobs.job_id", ondelete="CASCADE"),
        nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
