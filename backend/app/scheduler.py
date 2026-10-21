from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field

from app.models import CommitmentRead, RecordInput, TaskRead

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
STEP = timedelta(minutes=15)


class ScheduleRequest(RecordInput):
    week_start: date = Field(le=date.max - timedelta(days=7))


class ScheduledTask(BaseModel):
    task_id: str
    title: str
    start: AwareDatetime
    end: AwareDatetime
    scheduled_minutes: int
    duration_source: Literal["user_estimate"] = "user_estimate"


class UnscheduledTask(BaseModel):
    task_id: str
    title: str
    code: Literal[
        "window_elapsed", "deadline_passed", "duration_exceeds_day", "no_slot"
    ]
    reason: str


class ScheduleResult(BaseModel):
    week_start: date
    timezone: str = "America/New_York"
    effective_start: AwareDatetime
    scheduled: list[ScheduledTask]
    unscheduled: list[UnscheduledTask]
    commitments: list[CommitmentRead]


def generate_schedule(
    tasks: list[TaskRead],
    commitments: list[CommitmentRead],
    week_start: date,
    *,
    now: datetime,
) -> ScheduleResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone.")

    window_start = datetime.combine(
        week_start, time.min, tzinfo=NY
    ).astimezone(UTC)
    window_end = datetime.combine(
        week_start + timedelta(days=7), time.min, tzinfo=NY
    ).astimezone(UTC)
    effective_start = max(window_start, now.astimezone(UTC))

    visible_commitments = sorted(
        [
            item for item in commitments
            if item.start < window_end and item.end > window_start
        ],
        key=lambda item: (item.start, item.id),
    )
    busy = [(item.start, item.end) for item in visible_commitments]
    windows = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        windows.append((
            datetime.combine(day, time(9), tzinfo=NY).astimezone(UTC),
            datetime.combine(day, time(21), tzinfo=NY).astimezone(UTC),
        ))

    result = ScheduleResult(
        week_start=week_start,
        effective_start=effective_start,
        scheduled=[],
        unscheduled=[],
        commitments=visible_commitments,
    )
    ordered_tasks = sorted(
        (item for item in tasks if item.status == "todo"),
        key=lambda item: (item.deadline, -item.priority, item.id),
    )

    for task in ordered_tasks:
        minutes = ((task.estimated_minutes + 14) // 15) * 15
        if effective_start >= window_end:
            code = "window_elapsed"
            reason = "This seven-day window has already ended."
        elif task.deadline <= effective_start:
            code = "deadline_passed"
            reason = "The deadline is at or before the planning start."
        elif minutes > 720:
            code = "duration_exceeds_day"
            reason = (
                "The rounded duration exceeds the 12-hour daily window. "
                "This version schedules each task in one continuous block."
            )
        else:
            duration = timedelta(minutes=minutes)
            placed = False
            for day_start, day_end in windows:
                candidate = day_start
                latest_end = min(day_end, task.deadline)
                while candidate + duration <= latest_end:
                    end = candidate + duration
                    overlaps = any(
                        candidate < busy_end and end > busy_start
                        for busy_start, busy_end in busy
                    )
                    if candidate >= effective_start and not overlaps:
                        result.scheduled.append(ScheduledTask(
                            task_id=task.id,
                            title=task.title,
                            start=candidate,
                            end=end,
                            scheduled_minutes=minutes,
                        ))
                        busy.append((candidate, end))
                        placed = True
                        break
                    candidate += STEP
                if placed:
                    break

            if placed:
                continue
            code = "no_slot"
            reason = (
                f"No continuous {minutes}-minute block remains before the deadline in this weekly window, within 9:00AM to 9:00PM New York time, after commitments and earlier placements."
            )

        result.unscheduled.append(UnscheduledTask(
            task_id=task.id, title=task.title, code=code, reason=reason,
        ))

    result.scheduled.sort(key=lambda item: (item.start, item.task_id))
    return result