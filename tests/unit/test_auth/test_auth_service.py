import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.app.auth.session_model import AuthSession
from apps.api.app.auth.service import (
    AuthError,
    change_user_password,
    decode_access_token,
    get_active_session,
    login_user,
    refresh_tokens,
    register_user,
    revoke_refresh_token,
    verify_password,
)
from apps.api.app.database import Base


@pytest.fixture(autouse=True)
def auth_test_secret(monkeypatch):
    monkeypatch.setenv(
        "DATUMOR_AUTH_SECRET_KEY",
        "test-only-secret-key-for-datumor-authentication",
    )


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool

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


def test_register_hashes_password_and_normalizes_email(db):
    user = register_user(db, "  Alice@Example.com ", "correct-horse-battery")
    assert user.email_normalized == "alice@example.com"
    assert user.password_hash != "correct-horse-battery"
    assert verify_password(user.password_hash, "correct-horse-battery")
    assert user.role == "customer"
    assert user.is_active is True


def test_duplicate_registration_is_rejected(db):
    register_user(db, "alice@example.com", "correct-horse-battery")
    with pytest.raises(AuthError) as error:
        register_user(db, "ALICE@example.com", "another-correct-password")
    assert error.value.status_code == 409


def test_login_returns_access_and_refresh_tokens(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    tokens = login_user(db, user.email, "correct-horse-battery")
    payload = decode_access_token(tokens["access_token"])
    assert payload["sub"] == str(user.user_id)
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0


def test_wrong_password_is_rejected(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    with pytest.raises(AuthError):
        login_user(db, user.email, "incorrect-password")


def test_inactive_account_cannot_login(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    user.is_active = False
    db.commit()
    with pytest.raises(AuthError) as error:
        login_user(db, user.email, "correct-horse-battery")
    assert error.value.status_code == 403


def test_refresh_rotates_token_and_revokes_old_session(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    first = login_user(db, user.email, "correct-horse-battery")
    first_payload = decode_access_token(first["access_token"])
    first_session_id = uuid.UUID(first_payload["sid"])

    second = refresh_tokens(db, first["refresh_token"])
    second_payload = decode_access_token(second["access_token"])
    second_session_id = uuid.UUID(second_payload["sid"])

    assert first["refresh_token"] != second["refresh_token"]
    assert get_active_session(db, first_session_id, user.user_id) is None
    assert get_active_session(db, second_session_id, user.user_id) is not None


def test_refresh_token_reuse_revokes_entire_family(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    first = login_user(db, user.email, "correct-horse-battery")
    second = refresh_tokens(db, first["refresh_token"])

    with pytest.raises(AuthError, match="reuse"):
        refresh_tokens(db, first["refresh_token"])

    second_payload = decode_access_token(second["access_token"])
    second_session_id = uuid.UUID(second_payload["sid"])
    assert get_active_session(db, second_session_id, user.user_id) is None


def test_logout_revokes_refresh_session(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    tokens = login_user(db, user.email, "correct-horse-battery")
    session_id = uuid.UUID(decode_access_token(tokens["access_token"])["sid"])

    revoke_refresh_token(db, tokens["refresh_token"])
    assert get_active_session(db, session_id, user.user_id) is None


def test_password_change_revokes_all_sessions(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    first = login_user(db, user.email, "correct-horse-battery")
    second = login_user(db, user.email, "correct-horse-battery")

    change_user_password(
        db, user, "correct-horse-battery", "new-correct-password"
    )

    assert verify_password(user.password_hash, "new-correct-password")
    assert not verify_password(user.password_hash, "correct-horse-battery")

    for token in (first["access_token"], second["access_token"]):
        payload = decode_access_token(token)
        assert get_active_session(
            db, uuid.UUID(payload["sid"]), user.user_id
        ) is None


def test_refresh_token_is_stored_only_as_hash(db):
    user = register_user(db, "alice@example.com", "correct-horse-battery")
    tokens = login_user(db, user.email, "correct-horse-battery")
    stored = db.scalar(select(AuthSession))
    assert stored.refresh_token_hash != tokens["refresh_token"]
    assert len(stored.refresh_token_hash) == 64
