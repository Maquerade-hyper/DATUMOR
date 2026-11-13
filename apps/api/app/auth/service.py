from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.app.auth.session_model import AuthSession
from apps.api.app.auth.user_model import User

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env", override=False)

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

ACCESS_TOKEN_SECONDS = int(os.getenv("DATUMOR_ACCESS_TOKEN_SECONDS", "900"))
REFRESH_TOKEN_DAYS = int(os.getenv("DATUMOR_REFRESH_TOKEN_DAYS", "30"))
JWT_ISSUER = os.getenv("DATUMOR_JWT_ISSUER", "datumor")
JWT_AUDIENCE = os.getenv("DATUMOR_JWT_AUDIENCE", "datumor-api")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _secret() -> str:
    value = os.getenv("DATUMOR_AUTH_SECRET_KEY", "")
    if len(value) < 32:
        raise RuntimeError(
            "DATUMOR_AUTH_SECRET_KEY must contain at least 32 characters."
        )
    return value


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User, session_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.user_id),
        "sid": str(session_id),
        "role": user.role,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=ACCESS_TOKEN_SECONDS),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "sid", "iat", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired access token.") from exc


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _new_session(
    db: Session,
    user: User,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[AuthSession, str]:
    raw_token = _new_refresh_token()
    session = AuthSession(
        session_id=uuid.uuid4(),
        user_id=user.user_id,
        family_id=family_id or uuid.uuid4(),
        refresh_token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=REFRESH_TOKEN_DAYS),
        user_agent=user_agent[:500] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
    )
    db.add(session)
    return session, raw_token


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    normalized = normalize_email(email)
    existing = db.scalar(
        select(User).where(User.email_normalized == normalized)
    )
    if existing:
        raise AuthError("An account with this email already exists.", 409)

    user = User(
        email=email.strip(),
        email_normalized=normalized,
        password_hash=hash_password(password),
        full_name=full_name.strip() if full_name else None,
        role="customer",
        is_active=True,
        is_email_verified=False,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise AuthError(
            "An account with this email already exists.", 409
        ) from exc
    return user


def login_user(
    db: Session,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    normalized = normalize_email(email)
    user = db.scalar(
        select(User).where(User.email_normalized == normalized)
    )
    if user is None or not verify_password(user.password_hash, password):
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        raise AuthError("This account is inactive.", 403)

    session, refresh_token = _new_session(
        db, user, user_agent=user_agent, ip_address=ip_address
    )
    db.commit()

    return {
        "access_token": create_access_token(user, session.session_id),
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_SECONDS,
    }


def refresh_tokens(db: Session, raw_token: str) -> dict:
    token_hash = hash_refresh_token(raw_token)
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash)
        .with_for_update()
    )
    if session is None:
        raise AuthError("Invalid refresh token.")

    now = datetime.now(timezone.utc)

    if session.revoked_at is not None:
        # Reuse of an already-rotated token revokes the entire token family.
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.family_id == session.family_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.commit()
        raise AuthError("Refresh token reuse detected. Please log in again.")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise AuthError("Refresh token has expired.")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()
        raise AuthError("Account is unavailable.", 403)

    new_session, new_raw_token = _new_session(
        db,
        user,
        family_id=session.family_id,
        user_agent=session.user_agent,
        ip_address=session.ip_address,
    )
    session.revoked_at = now
    session.replaced_by_hash = new_session.refresh_token_hash
    db.commit()

    return {
        "access_token": create_access_token(user, new_session.session_id),
        "refresh_token": new_raw_token,
        "expires_in": ACCESS_TOKEN_SECONDS,
    }


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == hash_refresh_token(raw_token)
        )
    )
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()


def revoke_user_sessions(db: Session, user_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.commit()
    return result.rowcount or 0


def change_user_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise AuthError("Current password is incorrect.")

    user.password_hash = hash_password(new_password)
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()


def get_active_session(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID
) -> AuthSession | None:
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(AuthSession).where(
            AuthSession.session_id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )


def update_user_role(db: Session, user_id: uuid.UUID, role: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AuthError("User not found.", 404)
    user.role = role
    db.commit()
    db.refresh(user)
    return user
