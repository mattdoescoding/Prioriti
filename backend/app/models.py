from datetime import datetime, timezone
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def database_time(value: datetime) -> datetime:
    value = value.astimezone(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


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
    description: str = Field(default="", max_length=5000)
    group_id: str | None = None
    repeat_days: list[Annotated[int, Field(strict=True, ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    sessions_per_day: int = Field(default=1, strict=True, ge=1, le=12)

    @field_validator("repeat_days")
    @classmethod
    def unique_days(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

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
    source_id: str | None = None


class TaskStatus(RecordInput):
    status: Literal["todo", "completed"]


class CalendarEventInput(RecordInput):
    title: str = Field(min_length=1, max_length=200)
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        self.start = self.start.astimezone(timezone.utc)
        self.end = self.end.astimezone(timezone.utc)
        if self.end <= self.start:
            raise ValueError("Event end must be after start.")
        return self


class CalendarEvent(CalendarEventInput):
    id: str
    owner_id: str
    class_id: str | None = None
    source_id: str | None = None


class GroupInput(RecordInput):
    title: str = Field(min_length=1, max_length=80)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    daily_limit: int = Field(default=3, strict=True, ge=1, le=20)
    preferred_start: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    preferred_end: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def validate_hours(self) -> Self:
        if self.preferred_end <= self.preferred_start:
            raise ValueError("Preferred end must follow preferred start.")
        return self


class GroupRead(GroupInput):
    id: str
    owner_id: str
