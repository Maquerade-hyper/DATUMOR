from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.app.auth.dependencies import ensure_resource_owner
from apps.api.app.auth.user_model import User
from apps.api.app.projects.project_model import Project, ProjectActivity


def _visible_projects(db: Session, user: User):
    statement = select(Project)
    if user.role not in {"admin", "superadmin"}:
        statement = statement.where(Project.owner_user_id == user.user_id)
    return statement


def _get_project_or_404(
    db: Session,
    project_id: uuid.UUID,
    user: User,
) -> Project:
    project = db.scalar(
        _visible_projects(db, user).where(Project.project_id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    ensure_resource_owner(project.owner_user_id, user)
    return project


def _record_activity(
    db: Session,
    project: Project,
    actor: User,
    action: str,
    details: dict | None = None,
) -> None:
    db.add(
        ProjectActivity(
            project_id=project.project_id,
            actor_user_id=actor.user_id,
            action=action,
            details=details or {},
        )
    )


def create_project(
    db: Session,
    owner: User,
    name: str,
    description: str | None,
) -> Project:
    project = Project(
        owner_user_id=owner.user_id,
        name=name.strip(),
        description=description,
        status="active",
    )
    db.add(project)
    db.flush()
    _record_activity(db, project, owner, "project.created")
    db.commit()
    db.refresh(project)
    return project


def list_projects(
    db: Session,
    user: User,
    status: str,
    limit: int,
    offset: int,
) -> tuple[list[Project], int]:
    statement = _visible_projects(db, user)
    if status != "all":
        statement = statement.where(Project.status == status)

    count_statement = select(func.count()).select_from(statement.subquery())
    total = db.scalar(count_statement) or 0

    projects = db.scalars(
        statement.order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return list(projects), total


def get_project(
    db: Session,
    project_id: uuid.UUID,
    user: User,
) -> Project:
    return _get_project_or_404(db, project_id, user)


def update_project(
    db: Session,
    project_id: uuid.UUID,
    user: User,
    changes: dict,
) -> Project:
    project = _get_project_or_404(db, project_id, user)

    if project.status == "archived":
        raise HTTPException(
            status_code=409,
            detail="Archived projects cannot be updated. Restore the project first.",
        )

    changes = {key: value for key, value in changes.items() if key in {"name", "description"}}
    if not changes:
        raise HTTPException(status_code=422, detail="No project changes supplied.")

    for key, value in changes.items():
        setattr(project, key, value)

    _record_activity(db, project, user, "project.updated", {"fields": sorted(changes)})
    db.commit()
    db.refresh(project)
    return project


def archive_project(
    db: Session,
    project_id: uuid.UUID,
    user: User,
) -> Project:
    project = _get_project_or_404(db, project_id, user)

    if project.status == "archived":
        raise HTTPException(status_code=409, detail="Project is already archived.")

    project.status = "archived"
    project.archived_at = datetime.now(timezone.utc)
    _record_activity(db, project, user, "project.archived")
    db.commit()
    db.refresh(project)
    return project


def restore_project(
    db: Session,
    project_id: uuid.UUID,
    user: User,
) -> Project:
    project = _get_project_or_404(db, project_id, user)

    if project.status != "archived":
        raise HTTPException(status_code=409, detail="Project is not archived.")

    project.status = "active"
    project.archived_at = None
    _record_activity(db, project, user, "project.restored")
    db.commit()
    db.refresh(project)
    return project


def dashboard_summary(db: Session, user: User) -> dict:
    visible = _visible_projects(db, user)

    total = db.scalar(
        select(func.count()).select_from(visible.subquery())
    ) or 0

    active = db.scalar(
        select(func.count()).select_from(
            visible.where(Project.status == "active").subquery()
        )
    ) or 0

    archived = db.scalar(
        select(func.count()).select_from(
            visible.where(Project.status == "archived").subquery()
        )
    ) or 0

    recent_projects = db.scalars(
        visible.order_by(Project.updated_at.desc()).limit(5)
    ).all()

    activity_statement = (
        select(ProjectActivity)
        .join(Project, Project.project_id == ProjectActivity.project_id)
    )

    if user.role not in {"admin", "superadmin"}:
        activity_statement = activity_statement.where(
            Project.owner_user_id == user.user_id
        )

    recent_activity = db.scalars(
        activity_statement.order_by(ProjectActivity.created_at.desc()).limit(10)
    ).all()

    return {
        "total_projects": total,
        "active_projects": active,
        "archived_projects": archived,
        "recent_projects": list(recent_projects),
        "recent_activity": list(recent_activity),
    }


def project_activity(
    db: Session,
    project_id: uuid.UUID,
    user: User,
    limit: int,
) -> list[ProjectActivity]:
    project = _get_project_or_404(db, project_id, user)
    return list(
        db.scalars(
            select(ProjectActivity)
            .where(ProjectActivity.project_id == project.project_id)
            .order_by(ProjectActivity.created_at.desc())
            .limit(limit)
        ).all()
    )


def admin_list_projects(
    db: Session,
    owner_user_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Project], int]:
    statement = select(Project)
    if owner_user_id is not None:
        statement = statement.where(Project.owner_user_id == owner_user_id)

    total = db.scalar(
        select(func.count()).select_from(statement.subquery())
    ) or 0

    records = db.scalars(
        statement.order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return list(records), total
