import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from apps.api.app.database import SessionLocal
from apps.api.app.jobs.job_model import ProcessingJob
from apps.worker.job_runtime import add_event

LEASE_SECONDS = 600
LEGACY_RECOVERY_GRACE_SECONDS = 900
HEARTBEAT_INTERVAL_SECONDS = 30
logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def claim_execution(db, job_id: str, celery_task_id: str | None):
    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.job_id == job_id)
        .with_for_update()
    )

    if not job or job.status in ("completed", "failed", "cancelled"):
        return None

    now = utcnow()

    if job.status == "running":
        expiry = job.lease_expires_at

        if expiry is not None and expiry > now:
            return None

        if expiry is None:
            last_update = job.updated_at
            if last_update is None:
                return None

            legacy_cutoff = now - timedelta(
                seconds=LEGACY_RECOVERY_GRACE_SECONDS
            )
            if last_update > legacy_cutoff:
                return None

    if job.status not in ("queued", "running"):
        return None

    previous_execution = job.execution_id
    execution_id = str(__import__("uuid").uuid4())

    job.execution_id = execution_id
    job.celery_task_id = celery_task_id
    job.status = "running"
    job.started_at = job.started_at or now
    job.finished_at = None
    job.attempt = (job.attempt or 0) + 1
    job.stage = "source_resolution"
    job.progress = 5
    job.error_message = None
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)

    add_event(
        db, job_id, "execution_claimed",
        "Worker acquired execution ownership.",
        details={
            "execution_id": execution_id,
            "attempt": job.attempt,
            "recovered_previous_execution": bool(previous_execution),
        },
    )
    db.commit()
    return execution_id


def renew_execution(db, job_id: str, execution_id: str) -> bool:
    now = utcnow()

    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.execution_id == execution_id,
            ProcessingJob.status == "running",
            ProcessingJob.lease_expires_at > now,
        )
        .values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def execution_is_owned(job_id: str, execution_id: str) -> bool:
    now = utcnow()
    with SessionLocal() as check_db:
        return check_db.scalar(
            select(ProcessingJob.job_id).where(
                ProcessingJob.job_id == job_id,
                ProcessingJob.execution_id == execution_id,
                ProcessingJob.status == "running",
                ProcessingJob.lease_expires_at > now,
            )
        ) is not None


def acknowledge_cancellation(db, job_id: str, execution_id: str) -> bool:
    now = utcnow()

    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.execution_id == execution_id,
            ProcessingJob.status == "running",
            ProcessingJob.cancel_requested.is_(True),
            ProcessingJob.lease_expires_at > now,
        )
        .values(
            status="cancelled",
            stage="cancelled",
            finished_at=now,
            updated_at=now,
            execution_id=None,
            heartbeat_at=None,
            lease_expires_at=None,
        )
    )
    db.commit()

    if result.rowcount == 1:
        add_event(db, job_id, "cancelled", "Cancellation acknowledged.")
        db.commit()
        return True

    return False


class ExecutionHeartbeat:
    """Renew a job lease from a separate database session while work runs."""

    def __init__(self, job_id: str, execution_id: str):
        self.job_id = job_id
        self.execution_id = execution_id
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"datumor-heartbeat-{job_id[:8]}",
            daemon=True,
        )
        self.thread.start()

    def _run(self):
        while not self.stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                with SessionLocal() as heartbeat_db:
                    renewed = renew_execution(
                        heartbeat_db, self.job_id, self.execution_id
                    )
                if not renewed:
                    self.lost_event.set()
                    logger.warning(
                        "Execution lease lost for DATUMOR job %s",
                        self.job_id,
                    )
                    return
            except Exception:
                self.lost_event.set()
                logger.exception(
                    "Heartbeat failed for DATUMOR job %s", self.job_id
                )
                return

    def is_lost(self) -> bool:
        return self.lost_event.is_set()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)


def finalize_execution(db, job_id: str, execution_id: str, values: dict) -> bool:
    """Apply terminal state only while this execution owns an unexpired lease."""
    allowed = {
        "status", "stage", "progress", "result", "error_message",
        "finished_at",
    }
    if not set(values).issubset(allowed):
        raise ValueError("Unsupported terminal job fields.")

    now = utcnow()
    update_values = dict(values)
    update_values.update({
        "execution_id": None,
        "heartbeat_at": None,
        "lease_expires_at": None,
        "updated_at": now,
    })

    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.execution_id == execution_id,
            ProcessingJob.status == "running",
            ProcessingJob.lease_expires_at > now,
        )
        .values(**update_values)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1

def release_execution(db, job_id: str, execution_id: str) -> bool:
    """Release a lease only when the caller still owns the execution."""
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.execution_id == execution_id,
            ProcessingJob.status == "running",
        )
        .values(
            execution_id=None,
            heartbeat_at=None,
            lease_expires_at=None,
            updated_at=utcnow(),
        )
    )
    db.commit()
    return result.rowcount == 1
