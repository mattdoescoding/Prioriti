from datetime import datetime, timezone
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskCreate(RecordInput):
    title: str = Field(min_length=1, max_length=200)
    deadline: AwareDatetime
    priority: int = Field(default=2, strict=True, ge=1, le=3)
    category: str = Field(min_length=1, max_length=80)
    estimated_minutes: int = Field(strict=True, gt=0)
    status: Literal["todo", "completed"] = "todo"

    @field_validator("deadline")
    @classmethod
    def normalize_deadline(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class TaskRead(TaskCreate):
    id: str
    owner_id: str


class CommitmentCreate(RecordInput):
    title: str = Field(min_length=1, max_length=200)
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        self.start = self.start.astimezone(timezone.utc)
        self.end = self.end.astimezone(timezone.utc)
        if self.end <= self.start:
            raise ValueError("Commitment end must be after start.")
        return self


class CommitmentRead(CommitmentCreate):
    id: str
    owner_id: str
    class_id: str | None = None