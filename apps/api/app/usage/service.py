import os
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from fastapi import HTTPException

from apps.api.app.usage.models import UsageEvent, UsagePolicy


POLICY_ID = "default"


def get_policy(db):
    policy = db.get(UsagePolicy, POLICY_ID)
    if policy is None:
        mode = os.getenv("DATUMOR_DEPLOYMENT_MODE", "community").lower()
        self_hosted = mode == "self_hosted"
        policy = UsagePolicy(
            policy_id=POLICY_ID,
            deployment_mode="self_hosted" if self_hosted else "community",
            monthly_job_limit=0 if self_hosted else int(
                os.getenv("DATUMOR_MONTHLY_JOB_LIMIT", "100")
            ),
            monthly_ingestion_bytes_limit=0 if self_hosted else int(
                os.getenv("DATUMOR_MONTHLY_INGESTION_BYTES_LIMIT", "5368709120")
            ),
            requests_per_minute=int(os.getenv("DATUMOR_REQUESTS_PER_MINUTE", "60")),
        )
        db.add(policy)
        db.flush()
    return policy


def _period_start():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def record_usage(db, user_id, event_type, units=1, details=None):
    """Record successful usage and enforce monthly limits in the same transaction."""
    user_id = str(user_id)
    units = int(units)
    if units < 0:
        raise ValueError("Usage units cannot be negative.")

    # Serialize quota checks for one customer in PostgreSQL.
    db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(user_id)))
    )

    policy = get_policy(db)
    start = _period_start()

    if event_type in ("job", "retry") and policy.monthly_job_limit > 0:
        current = db.scalar(
            select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                UsageEvent.user_id == user_id,
                UsageEvent.event_type.in_(("job", "retry")),
                UsageEvent.created_at >= start,
            )
        ) or 0
        if int(current) + units > policy.monthly_job_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "monthly_job_quota_exceeded",
                    "message": "Monthly processing-job quota exceeded.",
                    "limit": policy.monthly_job_limit,
                    "used": int(current),
                },
            )

    if event_type == "ingestion_bytes" and policy.monthly_ingestion_bytes_limit > 0:
        current = db.scalar(
            select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                UsageEvent.user_id == user_id,
                UsageEvent.event_type == "ingestion_bytes",
                UsageEvent.created_at >= start,
            )
        ) or 0
        if int(current) + units > policy.monthly_ingestion_bytes_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "monthly_ingestion_quota_exceeded",
                    "message": "Monthly ingestion quota exceeded.",
                    "limit": policy.monthly_ingestion_bytes_limit,
                    "used": int(current),
                },
            )

    db.add(UsageEvent(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        event_type=event_type,
        units=units,
        details=details or {},
    ))
    db.flush()


def check_rate_limit(db, user_id, action):
    policy = get_policy(db)
    since = datetime.now(timezone.utc) - timedelta(minutes=1)

    # Rate limits are per customer and action, not shared across customers.
    db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(str(user_id))))
    )
    count = db.scalar(
        select(func.count()).select_from(UsageEvent).where(
            UsageEvent.user_id == str(user_id),
            UsageEvent.event_type == f"request:{action}",
            UsageEvent.created_at >= since,
        )
    ) or 0

    if policy.requests_per_minute > 0 and count >= policy.requests_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Request rate limit exceeded. Please retry shortly.",
        )

    db.add(UsageEvent(
        event_id=str(uuid.uuid4()),
        user_id=str(user_id),
        event_type=f"request:{action}",
        units=1,
        details={},
    ))
    db.flush()


def get_usage_summary(db, user_id):
    user_id = str(user_id)
    start = _period_start()
    policy = get_policy(db)

    rows = db.execute(
        select(UsageEvent.event_type, func.sum(UsageEvent.units))
        .where(
            UsageEvent.user_id == user_id,
            UsageEvent.created_at >= start,
        )
        .group_by(UsageEvent.event_type)
    ).all()

    totals = {kind: int(value or 0) for kind, value in rows}
    jobs = totals.get("job", 0) + totals.get("retry", 0)
    ingestion = totals.get("ingestion_bytes", 0)

    return {
        "period_start": start.isoformat(),
        "deployment_mode": policy.deployment_mode,
        "usage": {
            "processing_jobs": jobs,
            "ingestion_bytes": ingestion,
            "file_ingestions": totals.get("file_ingestion", 0),
            "github_ingestions": totals.get("github_ingestion", 0),
        },
        "limits": {
            "monthly_jobs": policy.monthly_job_limit,
            "monthly_ingestion_bytes": policy.monthly_ingestion_bytes_limit,
            "requests_per_minute": policy.requests_per_minute,
            "zero_means_unlimited": True,
        },
        "remaining": {
            "monthly_jobs": (
                None if policy.monthly_job_limit == 0
                else max(0, policy.monthly_job_limit - jobs)
            ),
            "monthly_ingestion_bytes": (
                None if policy.monthly_ingestion_bytes_limit == 0
                else max(0, policy.monthly_ingestion_bytes_limit - ingestion)
            ),
        },
    }
