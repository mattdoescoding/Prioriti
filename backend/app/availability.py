from datetime import date, timedelta
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.classes import ClockTime, Weekday, local_time
from app.models import RecordInput


class AvailabilityWindow(RecordInput):
    weekday: Weekday
    start_time: ClockTime
    end_time: Annotated[str, Field(pattern=r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")]

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("Availability must end after it starts on the same day.")
        return self


class Availability(RecordInput):
    windows: list[AvailabilityWindow] = Field(default_factory=lambda: [
        AvailabilityWindow(weekday=day, start_time="00:00", end_time="24:00")
        for day in range(7)
    ], max_length=70)

    @model_validator(mode="after")
    def validate_windows(self) -> Self:
        self.windows.sort(key=lambda item: (item.weekday, item.start_time))
        for first, second in zip(self.windows, self.windows[1:]):
            if first.weekday == second.weekday and first.end_time > second.start_time:
                raise ValueError("Availability windows on the same day cannot overlap.")
        return self


def availability_intervals(availability: Availability, start: date, days: int = 7):
    windows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for window in availability.windows:
            if window.weekday == day.weekday():
                end = (local_time(day + timedelta(days=1), "00:00")
                       if window.end_time == "24:00" else local_time(day, window.end_time))
                windows.append((local_time(day, window.start_time), end))
    return windows
