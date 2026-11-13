from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    os.getenv("DATUMOR_RUN_POSTGRES_E2E") != "1",
    reason="Set DATUMOR_RUN_POSTGRES_E2E=1 to run PostgreSQL API E2E tests",
)


def _find_id(data):
    """Find a project UUID in common API response shapes."""
    if isinstance(data, dict):
        for key in ("project_id", "id"):
            value = data.get(key)
            if value:
                return str(value)
        for value in data.values():
            found = _find_id(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_id(item)
            if found:
                return found
    return None


def _token(response):
    assert response.status_code == 200, (
        f"Login failed: {response.status_code} {response.text}"
    )
    data = response.json()
    token = data.get("access_token")
    if not token and isinstance(data.get("tokens"), dict):
        token = data["tokens"].get("access_token")
    assert token, f"No access_token in login response: {data}"
    return {"Authorization": f"Bearer {token}"}


def _register(client, email, password):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "DATUMOR E2E Test",
        },
    )
    assert response.status_code in (200, 201), (
        f"Registration failed: {response.status_code} {response.text}"
    )


def test_m92_postgres_authenticated_api_isolation():
    from apps.api.app.main import app
    from apps.api.app.database import SessionLocal
    from apps.api.app.auth.user_model import User
    from apps.api.app.projects.project_model import Project, ProjectActivity
    from sqlalchemy import delete, select, update

    suffix = uuid.uuid4().hex
    password = f"Test-{suffix}-Aa9!"
    email_a = f"datumor-e2e-a-{suffix}@example.com"
    email_b = f"datumor-e2e-b-{suffix}@example.com"
    email_admin = f"datumor-e2e-admin-{suffix}@example.com"

    user_ids = []
    project_ids = []

    try:
        with TestClient(app) as client:
            # Create three independent test accounts.
            _register(client, email_a, password)
            _register(client, email_b, password)
            _register(client, email_admin, password)

            headers_a = _token(client.post(
                "/api/v1/auth/login",
                json={"email": email_a, "password": password},
            ))
            headers_b = _token(client.post(
                "/api/v1/auth/login",
                json={"email": email_b, "password": password},
            ))

            # Promote only the disposable test account to admin.
            with SessionLocal() as db:
                admin_user = db.scalar(
                    select(User).where(User.email_normalized == email_admin)
                )
                user_a = db.scalar(
                    select(User).where(User.email_normalized == email_a)
                )
                user_b = db.scalar(
                    select(User).where(User.email_normalized == email_b)
                )
                assert admin_user and user_a and user_b

                user_ids.extend([
                    admin_user.user_id,
                    user_a.user_id,
                    user_b.user_id,
                ])

                db.execute(
                    update(User)
                    .where(User.user_id == admin_user.user_id)
                    .values(role="admin")
                )
                db.commit()

            headers_admin = _token(client.post(
                "/api/v1/auth/login",
                json={"email": email_admin, "password": password},
            ))

            # Customer A creates a project.
            created = client.post(
                "/api/v1/projects",
                headers=headers_a,
                json={
                    "name": f"E2E ownership project {suffix}",
                    "description": "Temporary PostgreSQL API isolation test",
                },
            )
            assert created.status_code in (200, 201), (
                f"Project creation failed: {created.status_code} {created.text}"
            )

            project_id = _find_id(created.json())
            assert project_id, f"Could not find project ID: {created.json()}"
            project_ids.append(project_id)

            # Customer A can retrieve their project.
            own_get = client.get(
                f"/api/v1/projects/{project_id}", headers=headers_a
            )
            assert own_get.status_code == 200, own_get.text

            # Customer B must not see or access Customer A's project.
            foreign_get = client.get(
                f"/api/v1/projects/{project_id}", headers=headers_b
            )
            assert foreign_get.status_code == 404, foreign_get.text

            foreign_update = client.patch(
                f"/api/v1/projects/{project_id}",
                headers=headers_b,
                json={"name": "Unauthorized modification"},
            )
            assert foreign_update.status_code == 404, foreign_update.text

            foreign_archive = client.post(
                f"/api/v1/projects/{project_id}/archive",
                headers=headers_b,
            )
            assert foreign_archive.status_code == 404, foreign_archive.text

            foreign_activity = client.get(
                f"/api/v1/projects/{project_id}/activity",
                headers=headers_b,
            )
            assert foreign_activity.status_code == 404, foreign_activity.text

            # Customer B's project listing must not expose Customer A's project.
            list_b = client.get("/api/v1/projects", headers=headers_b)
            assert list_b.status_code == 200, list_b.text
            assert project_id not in json.dumps(list_b.json())

            # Dashboard data must also remain tenant-isolated.
            dashboard_b = client.get(
                "/api/v1/dashboard", headers=headers_b
            )
            assert dashboard_b.status_code == 200, dashboard_b.text
            assert project_id not in json.dumps(dashboard_b.json())

            # Customer A can update their own project.
            updated = client.patch(
                f"/api/v1/projects/{project_id}",
                headers=headers_a,
                json={"name": f"Updated E2E project {suffix}"},
            )
            assert updated.status_code == 200, updated.text

            # Archive and verify archived status.
            archived = client.post(
                f"/api/v1/projects/{project_id}/archive",
                headers=headers_a,
            )
            assert archived.status_code == 200, archived.text

            archived_get = client.get(
                f"/api/v1/projects/{project_id}", headers=headers_a
            )
            assert archived_get.status_code == 200, archived_get.text
            assert archived_get.json().get("status") == "archived"

            # Restore and verify active status.
            restored = client.post(
                f"/api/v1/projects/{project_id}/restore",
                headers=headers_a,
            )
            assert restored.status_code == 200, restored.text

            restored_get = client.get(
                f"/api/v1/projects/{project_id}", headers=headers_a
            )
            assert restored_get.status_code == 200, restored_get.text
            assert restored_get.json().get("status") == "active"

            # Activity history is available to the owner, not another customer.
            own_activity = client.get(
                f"/api/v1/projects/{project_id}/activity",
                headers=headers_a,
            )
            assert own_activity.status_code == 200, own_activity.text
            assert len(own_activity.json()) > 0

            # Customers cannot access the admin project listing.
            customer_admin_access = client.get(
                "/api/v1/admin/projects", headers=headers_a
            )
            assert customer_admin_access.status_code == 403, (
                customer_admin_access.text
            )

            # Admin can inspect projects across customer accounts.
            admin_projects = client.get(
                "/api/v1/admin/projects", headers=headers_admin
            )
            assert admin_projects.status_code == 200, admin_projects.text
            assert project_id in json.dumps(admin_projects.json())

            # Unauthenticated access is rejected.
            unauthenticated = client.get("/api/v1/projects")
            assert unauthenticated.status_code in (401, 403)

    finally:
        # Remove only the disposable test records.
        with SessionLocal() as db:
            if user_ids:
                db.execute(
                    delete(ProjectActivity).where(
                        ProjectActivity.actor_user_id.in_(user_ids)
                    )
                )
                db.execute(
                    delete(Project).where(
                        Project.owner_user_id.in_(user_ids)
                    )
                )
                db.execute(
                    delete(User).where(User.user_id.in_(user_ids))
                )
                db.commit()
