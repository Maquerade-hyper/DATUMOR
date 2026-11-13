from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.auth.dependencies import get_current_user, require_roles
from apps.api.app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RoleUpdateRequest,
    TokenResponse,
    UserResponse,
)
from apps.api.app.auth.service import (
    AuthError,
    change_user_password,
    login_user,
    refresh_tokens,
    register_user,
    revoke_refresh_token,
    update_user_role,
)
from apps.api.app.auth.user_model import User
from apps.api.app.database import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


def _raise_auth_error(exc: AuthError):
    raise HTTPException(
        status_code=exc.status_code,
        detail=exc.message,
    ) from exc


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        user = register_user(
            db,
            str(payload.email),
            payload.password,
            payload.full_name,
        )
        return user
    except AuthError as exc:
        _raise_auth_error(exc)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user_agent, ip_address = _client_metadata(request)
    try:
        return login_user(
            db,
            str(payload.email),
            payload.password,
            user_agent,
            ip_address,
        )
    except AuthError as exc:
        _raise_auth_error(exc)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    try:
        return refresh_tokens(db, payload.refresh_token)
    except AuthError as exc:
        _raise_auth_error(exc)


@router.post("/logout", status_code=204)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
):
    revoke_refresh_token(db, payload.refresh_token)
    return None


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        change_user_password(
            db, user, payload.current_password, payload.new_password
        )
    except AuthError as exc:
        _raise_auth_error(exc)
    return None


admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Administration"],
    dependencies=[Depends(require_roles("admin", "superadmin"))],
)


@admin_router.get("/users", response_model=list[UserResponse])
def list_users(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination.")
    return db.scalars(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    ).all()


@admin_router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
)
def change_role(
    user_id: str,
    payload: RoleUpdateRequest,
    actor: User = Depends(require_roles("superadmin")),
    db: Session = Depends(get_db),
):
    import uuid

    try:
        parsed_id = uuid.UUID(user_id)
        target = db.get(User, parsed_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")

        if target.user_id == actor.user_id and payload.role != "superadmin":
            raise HTTPException(
                status_code=409,
                detail="You cannot remove your own superadmin role.",
            )

        return update_user_role(db, parsed_id, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user ID.") from exc
