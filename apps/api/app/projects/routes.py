import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.app.auth.dependencies import get_current_user, require_roles
from apps.api.app.auth.user_model import User
from apps.api.app.database import get_db
from apps.api.app.projects.schemas import (
    ActivityResponse,
    DashboardResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from apps.api.app.projects.service import (
    admin_list_projects,
    archive_project,
    create_project,
    dashboard_summary,
    get_project,
    list_projects,
    project_activity,
    restore_project,
    update_project,
)

router = APIRouter(prefix="/api/v1", tags=["Projects and Dashboard"])

admin_projects_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Project Administration"],
    dependencies=[Depends(require_roles("admin", "superadmin"))],
)


def _parse_project_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid project ID.") from exc


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_project(db, user, payload.name, payload.description)


@router.get("/projects")
def list_all(
    status: str = Query(default="active", pattern="^(active|archived|all)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records, total = list_projects(db, user, status, limit, offset)
    return {
        "success": True,
        "data": records,
        "count": len(records),
        "total": total,
        "limit": limit,
        "offset": offset,
        "status": status,
    }


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def retrieve(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_project(db, _parse_project_id(project_id), user)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update(
    project_id: str,
    payload: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_project(
        db,
        _parse_project_id(project_id),
        user,
        payload.model_dump(exclude_unset=True),
    )


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
def archive(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return archive_project(db, _parse_project_id(project_id), user)


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
def restore(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return restore_project(db, _parse_project_id(project_id), user)


@router.get("/projects/{project_id}/activity", response_model=list[ActivityResponse])
def activity(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return project_activity(db, _parse_project_id(project_id), user, limit)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_summary(db, user)


@admin_projects_router.get("/projects")
def list_all_customer_projects(
    owner_user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    parsed_owner_id = None
    if owner_user_id is not None:
        try:
            parsed_owner_id = uuid.UUID(owner_user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid owner user ID.") from exc

    records, total = admin_list_projects(db, parsed_owner_id, limit, offset)
    return {
        "success": True,
        "data": records,
        "count": len(records),
        "total": total,
        "limit": limit,
        "offset": offset,
    }
