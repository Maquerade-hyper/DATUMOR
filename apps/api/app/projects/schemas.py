from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Project name must contain at least 2 characters.")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Project name must contain at least 2 characters.")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    owner_user_id: UUID
    name: str
    description: str | None
    status: str
    created_at: object
    updated_at: object
    archived_at: object | None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: UUID
    project_id: UUID
    actor_user_id: UUID | None
    action: str
    details: dict
    created_at: object


class DashboardResponse(BaseModel):
    total_projects: int
    active_projects: int
    archived_projects: int
    recent_projects: list[ProjectResponse]
    recent_activity: list[ActivityResponse]
