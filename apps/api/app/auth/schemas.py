from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    is_email_verified: bool


class TokenResponse(BaseModel):
    token_type: str = "Bearer"
    access_token: str
    refresh_token: str
    expires_in: int


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(customer|admin|superadmin)$")
