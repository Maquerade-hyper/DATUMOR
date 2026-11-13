import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from apps.api.app.auth.user_model import User
from apps.api.app.database import Base
from apps.api.app.projects.project_model import ProjectActivity
from apps.api.app.projects.service import (
    archive_project,
    create_project,
    dashboard_summary,
    get_project,
    list_projects,
    restore_project,
    update_project,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def users(db):
    first = User(
        email="first@example.test",
        email_normalized="first@example.test",
        password_hash="not-used-in-project-tests",
        role="customer",
    )
    second = User(
        email="second@example.test",
        email_normalized="second@example.test",
        password_hash="not-used-in-project-tests",
        role="customer",
    )
    admin = User(
        email="admin@example.test",
        email_normalized="admin@example.test",
        password_hash="not-used-in-project-tests",
        role="superadmin",
    )
    db.add_all([first, second, admin])
    db.commit()
    return first, second, admin


def test_create_project_assigns_authenticated_owner(db, users):
    owner, _, _ = users
    project = create_project(db, owner, "My Project", "Description")

    assert project.owner_user_id == owner.user_id
    assert project.status == "active"
    assert project.archived_at is None

    event = db.scalar(select(ProjectActivity).where(
        ProjectActivity.project_id == project.project_id
    ))
    assert event is not None
    assert event.action == "project.created"


def test_customer_cannot_read_another_customers_project(db, users):
    owner, other, _ = users
    project = create_project(db, owner, "Private Project", None)

    with pytest.raises(HTTPException) as error:
        get_project(db, project.project_id, other)

    assert error.value.status_code == 404


def test_customer_project_listing_is_isolated(db, users):
    owner, other, _ = users
    create_project(db, owner, "Owner Project", None)
    create_project(db, other, "Other Project", None)

    projects, total = list_projects(db, owner, "all", 50, 0)

    assert total == 1
    assert len(projects) == 1
    assert projects[0].owner_user_id == owner.user_id


def test_admin_can_read_another_customers_project(db, users):
    owner, _, admin = users
    project = create_project(db, owner, "Customer Project", None)

    assert get_project(db, project.project_id, admin).project_id == project.project_id


def test_update_project_records_activity(db, users):
    owner, _, _ = users
    project = create_project(db, owner, "Before", None)

    updated = update_project(
        db,
        project.project_id,
        owner,
        {"name": "After", "description": "Updated"},
    )

    assert updated.name == "After"
    assert updated.description == "Updated"

    actions = db.scalars(
        select(ProjectActivity.action).where(
            ProjectActivity.project_id == project.project_id
        )
    ).all()
    assert "project.updated" in actions


def test_archive_and_restore_project(db, users):
    owner, _, _ = users
    project = create_project(db, owner, "Lifecycle", None)

    archived = archive_project(db, project.project_id, owner)
    assert archived.status == "archived"
    assert archived.archived_at is not None

    restored = restore_project(db, project.project_id, owner)
    assert restored.status == "active"
    assert restored.archived_at is None


def test_archived_project_cannot_be_updated(db, users):
    owner, _, _ = users
    project = create_project(db, owner, "Archived", None)
    archive_project(db, project.project_id, owner)

    with pytest.raises(HTTPException) as error:
        update_project(db, project.project_id, owner, {"name": "Changed"})

    assert error.value.status_code == 409


def test_dashboard_only_counts_visible_projects(db, users):
    owner, other, _ = users
    create_project(db, owner, "Active", None)
    archived = create_project(db, owner, "Archived", None)
    archive_project(db, archived.project_id, owner)
    create_project(db, other, "Other Customer", None)

    summary = dashboard_summary(db, owner)

    assert summary["total_projects"] == 2
    assert summary["active_projects"] == 1
    assert summary["archived_projects"] == 1
    assert len(summary["recent_projects"]) == 2


def test_admin_dashboard_includes_all_projects(db, users):
    owner, other, admin = users
    create_project(db, owner, "One", None)
    create_project(db, other, "Two", None)

    summary = dashboard_summary(db, admin)
    assert summary["total_projects"] == 2


def test_project_activity_isolation(db, users):
    owner, other, _ = users
    project = create_project(db, owner, "Private Activity", None)

    with pytest.raises(HTTPException) as error:
        from apps.api.app.projects.service import project_activity
        project_activity(db, project.project_id, other, 10)

    assert error.value.status_code == 404
