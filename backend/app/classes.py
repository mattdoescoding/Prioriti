from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Self
from zoneinfo import ZoneInfo
from pydantic import Field, model_validator
from app.models import CommitmentRead, RecordInput

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
Weekday = Annotated[int, Field(strict=True, ge=0, le=6)]
ClockTime = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]

def local_time(day: date, clock: str) -> datetime:
    naive = datetime.combine(day, time.fromisoformat(clock))
    local = naive.replace(tzinfo=NY)
    utc = local.astimezone(UTC)

    if utc.astimezone(NY).replace(tzinfo=None) != naive:
        raise ValueError(
            f"{day} {clock} does not exist due to daylight saving time."
        )

    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError(
            f"{day} {clock} is ambiguous due to daylight saving time."
        )

    return utc

class ClassInput(RecordInput):
    title: str = Field(min_length=1, max_length=200)
    weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    start_time: ClockTime
    end_time: ClockTime
    start_date: date
    end_date: date
    skip_dates: list[date] = Field(default_factory=list, max_length=366)

    @model_validator(mode="after")
    def validate_pattern(self) -> Self:
        length = (self.end_date - self.start_date).days

        if not 0 <= length <= 365:
            raise ValueError(
                "Choose a term ending within 365 days of its start."
            )

        if self.end_time <= self.start_time:
            raise ValueError(
                "Classes must end after they start on the same day."
            )

        self.weekdays = sorted(set(self.weekdays))
        self.skip_dates = sorted(set(self.skip_dates))

        for day in self.skip_dates:
            if (
                not self.start_date <= day <= self.end_date
                or day.weekday() not in self.weekdays
            ):
                raise ValueError(
                    "Skipped dates must be class meeting dates within the term."
                )

        for offset in range(length + 1):
            day = self.start_date + timedelta(days=offset)

            if day.weekday() in self.weekdays and day not in self.skip_dates:
                local_time(day, self.start_time)
                local_time(day, self.end_time)

        return self


class ClassRead(ClassInput):
    id: str
    owner_id: str


def expand_classes(
    classes: list[ClassRead], week_start: date,
) -> list[CommitmentRead]:
    meetings = []

    for item in classes:
        for offset in range(7):
            day = week_start + timedelta(days=offset)

            if (
                item.start_date <= day <= item.end_date
                and day.weekday() in item.weekdays
                and day not in item.skip_dates
            ):
                meetings.append(CommitmentRead(
                    id=f"{item.id}:{day.isoformat()}",
                    class_id=item.id,
                    owner_id=item.owner_id,
                    title=item.title,
                    start=local_time(day, item.start_time),
                    end=local_time(day, item.end_time),
                ))

    return sorted(meetings, key=lambda item: (item.start, item.id))