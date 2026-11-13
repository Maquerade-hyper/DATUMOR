from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Any


class JobCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=200)
    source_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, values: list[str]) -> list[str]:
        import uuid
        try:
            return [str(uuid.UUID(value)) for value in values]
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Every source ID must be a valid UUID.") from exc

    pipeline: str = Field(default="standard", pattern="^(standard|extract_only)$")
    options: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: str
    project_id: str
    name: str
    pipeline: str
    source_ids: list
    status: str
    stage: str
    progress: int
    result: dict | None
    error_message: str | None
    attempt: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: str
    level: str
    stage: str
    message: str
    details: dict
    created_at: datetime
