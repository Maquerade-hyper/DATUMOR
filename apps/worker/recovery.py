from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from apps.api.app.database import SessionLocal
from apps.api.app.jobs.job_model import ProcessingJob


LEGACY_GRACE_MINUTES = 15


def utcnow():
    return datetime.now(timezone.utc)


def detect_stale_jobs(db, legacy_grace_minutes=LEGACY_GRACE_MINUTES):
    """
    Read-only detection.

    Expired leases are stale immediately.
    Legacy running jobs without lease metadata are stale only when
    their last update is older than the configured grace period.
    """
    now = utcnow()
    legacy_cutoff = now - timedelta(minutes=legacy_grace_minutes)

    statement = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == "running",
            or_(
                ProcessingJob.lease_expires_at <= now,
                and_(
                    ProcessingJob.lease_expires_at.is_(None),
                    ProcessingJob.heartbeat_at.is_(None),
                    ProcessingJob.updated_at <= legacy_cutoff,
                ),
            ),
        )
        .order_by(ProcessingJob.updated_at.asc())
    )

    jobs = db.scalars(statement).all()

    return [
        {
            "job_id": job.job_id,
            "project_id": str(job.project_id),
            "status": job.status,
            "attempt": job.attempt,
            "execution_id": job.execution_id,
            "heartbeat_at": job.heartbeat_at.isoformat()
                if job.heartbeat_at else None,
            "lease_expires_at": job.lease_expires_at.isoformat()
                if job.lease_expires_at else None,
            "updated_at": job.updated_at.isoformat()
                if job.updated_at else None,
            "reason": (
                "lease_expired"
                if job.lease_expires_at is not None
                else "legacy_missing_lease"
            ),
        }
        for job in jobs
    ]


def main():
    with SessionLocal() as db:
        stale = detect_stale_jobs(db)

    print("DATUMOR STALE JOB DETECTION")
    print("Mode: READ ONLY")
    print("Stale jobs found:", len(stale))

    for item in stale:
        print("-" * 60)
        for key, value in item.items():
            print(f"{key}: {value}")

    print("-" * 60)
    print("H6.3.1 DETECTION COMPLETE")


if __name__ == "__main__":
    main()
