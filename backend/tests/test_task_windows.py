from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.models import CommitmentRead, TaskRead
from app.scheduler import generate_schedule

NY = ZoneInfo("America/New_York")
WEEK = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 8, tzinfo=NY)


def task(**changes):
    values = dict(
        id="study",
        owner_id="local-development",
        title="Study chemistry",
        deadline=datetime(2026, 11, 5, 21, tzinfo=NY),
        estimated_minutes=45,
        category="Studying",
        priority=2,
    )
    values.update(changes)
    return TaskRead(**values)


def test_thursday_task_cannot_be_scheduled_on_monday():
    item = task(not_before=datetime(2026, 11, 5, 10, 7, tzinfo=NY))
    result = generate_schedule([item], [], WEEK, now=NOW)

    assert result.scheduled[0].start == datetime(
        2026, 11, 5, 10, 15, tzinfo=NY,
    )
    assert result.scheduled[0].end == datetime(
        2026, 11, 5, 11, tzinfo=NY,
    )
    assert not result.unscheduled


def test_full_thursday_does_not_move_task_to_another_day():
    item = task(not_before=datetime(2026, 11, 5, 9, tzinfo=NY))
    busy = CommitmentRead(
        id="busy",
        owner_id="local-development",
        title="Unavailable",
        start=datetime(2026, 11, 5, 9, tzinfo=NY),
        end=datetime(2026, 11, 5, 21, tzinfo=NY),
    )
    result = generate_schedule([item], [busy], WEEK, now=NOW)

    assert not result.scheduled
    assert result.unscheduled[0].code == "no_slot"
    assert result.unscheduled[0].reason


def test_task_available_next_week_is_explained():
    item = task(
        not_before=datetime(2026, 11, 9, 9, tzinfo=NY),
        deadline=datetime(2026, 11, 9, 21, tzinfo=NY),
    )
    result = generate_schedule([item], [], WEEK, now=NOW)

    assert not result.scheduled
    assert result.unscheduled[0].code == "not_available"
    assert result.unscheduled[0].reason


@pytest.mark.parametrize("hour", [19, 20])
def test_invalid_task_window_is_rejected(hour):
    with pytest.raises(
        ValidationError,
        match="Available-from time must be before the deadline",
    ):
        task(
            not_before=datetime(2026, 11, 5, 20, tzinfo=NY),
            deadline=datetime(2026, 11, 5, hour, tzinfo=NY),
        )


def test_existing_tasks_still_start_when_time_is_available():
    result = generate_schedule([task()], [], WEEK, now=NOW)

    assert result.scheduled[0].start == datetime(
        2026, 11, 2, 9, tzinfo=NY,
    )