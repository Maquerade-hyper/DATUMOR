import os
import shutil
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.database import get_db
from apps.api.app.auth.dependencies import get_current_user
from apps.api.app.usage.models import UsagePolicy
from apps.api.app.usage.service import get_policy, get_usage_summary

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])
admin_router = APIRouter(prefix="/api/v1/admin/usage", tags=["usage-admin"])


def _admin(user):
    return getattr(user, "role", "customer") in ("admin", "superadmin")


class PolicyUpdate(BaseModel):
    deployment_mode: str = Field(pattern="^(community|self_hosted)$")
    monthly_job_limit: int = Field(ge=0, le=10000000)
    monthly_ingestion_bytes_limit: int = Field(ge=0, le=10**15)
    requests_per_minute: int = Field(ge=0, le=1000000)


@router.get("/me")
def my_usage(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_usage_summary(db, user.user_id)


@router.get("/policy")
def public_policy(db: Session = Depends(get_db), user=Depends(get_current_user)):
    policy = get_policy(db)
    return {
        "deployment_mode": policy.deployment_mode,
        "monthly_job_limit": policy.monthly_job_limit,
        "monthly_ingestion_bytes_limit": policy.monthly_ingestion_bytes_limit,
        "requests_per_minute": policy.requests_per_minute,
        "zero_means_unlimited": True,
    }


@admin_router.get("/policy")
def read_policy(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not _admin(user):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    p = get_policy(db)
    return {
        "deployment_mode": p.deployment_mode,
        "monthly_job_limit": p.monthly_job_limit,
        "monthly_ingestion_bytes_limit": p.monthly_ingestion_bytes_limit,
        "requests_per_minute": p.requests_per_minute,
        "updated_at": p.updated_at.isoformat(),
    }


@admin_router.put("/policy")
def update_policy(
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _admin(user):
        raise HTTPException(status_code=403, detail="Administrator access required.")

    p = get_policy(db)
    p.deployment_mode = payload.deployment_mode
    p.monthly_job_limit = payload.monthly_job_limit
    p.monthly_ingestion_bytes_limit = payload.monthly_ingestion_bytes_limit
    p.requests_per_minute = payload.requests_per_minute
    p.updated_at = datetime.now(timezone.utc)
    p.updated_by = str(user.user_id)
    db.commit()
    return {"success": True, "policy": {
        "deployment_mode": p.deployment_mode,
        "monthly_job_limit": p.monthly_job_limit,
        "monthly_ingestion_bytes_limit": p.monthly_ingestion_bytes_limit,
        "requests_per_minute": p.requests_per_minute,
    }}


@admin_router.get("/resources")
def system_resources(user=Depends(get_current_user)):
    if not _admin(user):
        raise HTTPException(status_code=403, detail="Administrator access required.")

    disk = shutil.disk_usage(os.getcwd())
    result = {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
    }

    try:
        import psutil
        memory = psutil.virtual_memory()
        result["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        result["memory"] = {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_percent": memory.percent,
        }
    except ImportError:
        result["resource_monitoring_note"] = (
            "Install psutil to enable CPU and RAM metrics."
        )

    return result
