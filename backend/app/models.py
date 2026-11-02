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
    not_before: AwareDatetime | None = None
    priority: int = Field(default=2, strict=True, ge=1, le=3)
    category: str = Field(min_length=1, max_length=80)
    estimated_minutes: int = Field(strict=True, gt=0)
    status: Literal["todo", "completed"] = "todo"

    @field_validator("deadline", "not_before")
    @classmethod
    def normalize_task_time(
        cls, value: datetime | None,
    ) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def validate_task_window(self) -> Self:
        if self.not_before is not None and self.not_before >= self.deadline:
            raise ValueError(
                "Available-from time must be before the deadline."
            )
        return self


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