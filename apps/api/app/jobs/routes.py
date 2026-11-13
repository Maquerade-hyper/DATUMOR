import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.database import get_db
from apps.api.app.auth.dependencies import get_current_user
from apps.api.app.projects.project_model import Project
from apps.api.app.jobs.job_model import ProcessingJob, ProcessingJobEvent
from apps.api.app.jobs.schemas import JobCreate, JobResponse, JobEventResponse
from apps.worker.celery_app import celery_app
from apps.api.app.usage.models import UsageEvent, UsagePolicy
from apps.api.app.usage.service import record_usage, check_rate_limit

router = APIRouter(prefix="/api/v1/jobs", tags=["processing"])
admin_router = APIRouter(prefix="/api/v1/admin/jobs", tags=["processing-admin"])


def _admin(user):
    return getattr(user, "role", "customer") in ("admin", "superadmin")


def _visible_job(db, job_id, user):
    query = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
    if not _admin(user):
        query = query.where(ProcessingJob.owner_user_id == str(user.user_id))
    job = db.scalar(query)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("", response_model=JobResponse, status_code=202)
def create_job(payload: JobCreate, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    project_query = select(Project).where(Project.project_id == payload.project_id)
    if not _admin(user):
        project_query = project_query.where(Project.owner_user_id == str(user.user_id))
    project = db.scalar(project_query)
    if not project or getattr(project, "status", "active") != "active":
        raise HTTPException(status_code=404, detail="Project not found.")

    check_rate_limit(db, project.owner_user_id, 'job_creation')
    record_usage(db, project.owner_user_id, "job", 1)
    job = ProcessingJob(
        job_id=str(uuid.uuid4()),
        project_id=str(project.project_id),
        owner_user_id=str(project.owner_user_id),
        name=payload.name,
        pipeline=payload.pipeline,
        source_ids=list(dict.fromkeys(
            str(uuid.UUID(source_id)) for source_id in payload.source_ids
        )),
        options=payload.options,
        status="queued",
        stage="queued",
        progress=0,
    )
    db.add(job)
    db.add(ProcessingJobEvent(
        event_id=str(uuid.uuid4()), job_id=job.job_id, level="info",
        stage="queued", message="Job accepted and queued.", details={}
    ))
    db.commit()
    db.refresh(job)

    try:
        task = celery_app.send_task("datumor.process_job", args=[job.job_id])
        job.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.stage = "queue_error"
        job.error_message = f"Queue unavailable: {type(exc).__name__}"
        db.commit()
        raise HTTPException(status_code=503, detail="Processing queue is unavailable.")

    return job


@router.get("", response_model=list[JobResponse])
def list_jobs(project_id: str | None = None, limit: int = 50,
              db: Session = Depends(get_db), user=Depends(get_current_user)):
    limit = max(1, min(limit, 100))
    query = select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit)
    if not _admin(user):
        query = query.where(ProcessingJob.owner_user_id == str(user.user_id))
    if project_id:
        query = query.where(ProcessingJob.project_id == project_id)
    return list(db.scalars(query).all())


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    return _visible_job(db, job_id, user)


@router.get("/{job_id}/events", response_model=list[JobEventResponse])
def job_events(job_id: str, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    _visible_job(db, job_id, user)
    query = select(ProcessingJobEvent).where(
        ProcessingJobEvent.job_id == job_id
    ).order_by(ProcessingJobEvent.created_at.asc())
    return list(db.scalars(query).all())


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    job = _visible_job(db, job_id, user)
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail="This job is already finished.")
    job.cancel_requested = True
    if job.status == "queued":
        job.status = "cancelled"
        job.stage = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    db.add(ProcessingJobEvent(
        event_id=str(uuid.uuid4()), job_id=job_id, level="warning",
        stage="cancellation_requested", message="Cancellation requested.", details={}
    ))
    db.commit()
    return job


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=202)
def retry_job(job_id: str, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    old = _visible_job(db, job_id, user)
    if old.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried.")
    check_rate_limit(db, old.owner_user_id, 'job_retry')
    record_usage(db, old.owner_user_id, "retry", 1)
    new_job = ProcessingJob(
        job_id=str(uuid.uuid4()), project_id=old.project_id,
        owner_user_id=old.owner_user_id, name=f"{old.name} (retry)",
        pipeline=old.pipeline, source_ids=old.source_ids,
        options=old.options, status="queued", stage="queued", progress=0,
    )
    db.add(new_job)
    db.add(ProcessingJobEvent(
        event_id=str(uuid.uuid4()), job_id=new_job.job_id, level="info",
        stage="queued", message=f"Retry created from job {old.job_id}.", details={}
    ))
    db.commit()
    try:
        task = celery_app.send_task("datumor.process_job", args=[new_job.job_id])
        new_job.celery_task_id = task.id
        db.commit()
    except Exception:
        new_job.status = "failed"
        new_job.stage = "queue_error"
        new_job.error_message = "Queue unavailable."
        db.commit()
        raise HTTPException(status_code=503, detail="Processing queue is unavailable.")
    return new_job


@admin_router.get("")
def admin_list_jobs(limit: int = 100, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    if not _admin(user):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return list(db.scalars(
        select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all())
