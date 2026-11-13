import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from apps.api.app.database import Base, get_db
from apps.api.app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "DATUMOR_AUTH_SECRET_KEY",
        "test-only-secret-key-for-datumor-authentication",
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Do not enter TestClient as a context manager here:
    # these tests use their isolated SQLite dependency override,
    # not the production application startup database.
    test_client = TestClient(app)
    yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def test_registration_login_me_and_logout(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "api@example.com",
            "password": "a-strong-test-password",
            "full_name": "API Customer",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == "customer"
    assert "password_hash" not in registration.json()

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "API@example.com",
            "password": "a-strong-test-password",
        },
    )
    assert login.status_code == 200
    tokens = login.json()

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "api@example.com"

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout.status_code == 204

    after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert after_logout.status_code == 401


def test_protected_endpoint_rejects_missing_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_refresh_endpoint_rotates_token(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "a-strong-test-password",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "a-strong-test-password",
        },
    ).json()

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != login["refresh_token"]

    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert replay.status_code == 401


def test_customer_cannot_access_admin_users(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "password": "a-strong-test-password",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "customer@example.com",
            "password": "a-strong-test-password",
        },
    ).json()

    response = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert response.status_code == 403
