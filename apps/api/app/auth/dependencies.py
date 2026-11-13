import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from apps.api.app.auth.service import (
    AuthError,
    decode_access_token,
    get_active_session,
)
from apps.api.app.auth.user_model import User
from apps.api.app.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (AuthError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable.")

    active_session = get_active_session(db, session_id, user_id)
    if active_session is None:
        raise HTTPException(status_code=401, detail="Session revoked or expired.")

    return user


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user

    return dependency


def ensure_resource_owner(owner_user_id: uuid.UUID, user: User) -> None:
    """Enforce customer ownership; admins may access resources."""
    if user.role in {"admin", "superadmin"}:
        return
    if owner_user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Resource not found.")
