import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from apps.api.app.jobs.job_model import ProcessingJob, ProcessingJobEvent


def now():
    return datetime.now(timezone.utc)


def add_event(db: Session, job_id: str, stage: str, message: str,
              level: str = "info", details: dict | None = None):
    db.add(ProcessingJobEvent(
        event_id=str(uuid.uuid4()), job_id=job_id, stage=stage,
        message=message, level=level, details=details or {}
    ))


def get_job(db: Session, job_id: str):
    return db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))


def update_job(db: Session, job: ProcessingJob, *, status=None, stage=None,
               progress=None, error=None, result=None):
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = max(0, min(100, progress))
    if error is not None:
        job.error_message = error[:4000]
    if result is not None:
        job.result = result
    job.updated_at = now()
    db.commit()
