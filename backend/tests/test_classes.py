from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.classes import ClassRead, expand_classes
from app.models import TaskRead
from app.scheduler import generate_schedule

NY = ZoneInfo("America/New_York")


def series(**changes):
    values = dict(
        id="course",
        owner_id="local-development",
        title="Calculus",
        weekdays=[0, 2],
        start_time="09:00",
        end_time="10:00",
        start_date="2026-10-26",
        end_date="2026-11-09",
        skip_dates=[],
    )
    values.update(changes)
    return ClassRead(**values)


def test_semester_boundaries_skips_and_stable_ids():
    item = series(skip_dates=["2026-10-28"])
    first = expand_classes([item], date(2026, 10, 25))

    assert len(first) == 1
    assert first[0].start.astimezone(NY).date() == date(2026, 10, 26)
    assert first[0].class_id == "course"
    assert first == expand_classes([item], date(2026, 10, 25))

    last = expand_classes([item], date(2026, 11, 9))
    assert len(last) == 1
    assert expand_classes([item], date(2026, 11, 10)) == []


def test_classes_keep_wall_time_across_dst():
    item = series(weekdays=[0])

    before = expand_classes([item], date(2026, 10, 26))[0]
    after = expand_classes([item], date(2026, 11, 2))[0]

    assert before.start.hour == 13
    assert after.start.hour == 14
    assert before.start.astimezone(NY).hour == 9
    assert after.start.astimezone(NY).hour == 9


@pytest.mark.parametrize("changes", [
    {"weekdays": []},
    {"weekdays": [7]},
    {"weekdays": [True]},
    {"start_time": "10:00", "end_time": "09:00"},
    {"end_date": "2026-10-01"},
    {"skip_dates": ["2026-12-01"]},
    {
        "start_date": "2026-03-08",
        "end_date": "2026-03-08",
        "weekdays": [6],
        "start_time": "02:30",
        "end_time": "03:30",
    },
    {
        "start_date": "2026-11-01",
        "end_date": "2026-11-01",
        "weekdays": [6],
        "start_time": "01:30",
        "end_time": "03:00",
    },
])
def test_invalid_patterns_are_rejected(changes):
    with pytest.raises(ValidationError):
        series(**changes)


def test_scheduler_reserves_recurring_class_time():
    task = TaskRead(
        id="assignment",
        owner_id="local-development",
        title="Homework",
        deadline=datetime(2026, 10, 26, 12, tzinfo=NY),
        priority=2,
        category="Assignment",
        estimated_minutes=60,
        status="todo",
    )

    result = generate_schedule(
        [task],
        expand_classes([series()], date(2026, 10, 26)),
        date(2026, 10, 26),
        now=datetime(2026, 10, 26, 8, tzinfo=NY),
    )

    assert result.scheduled[0].start == datetime(
        2026, 10, 26, 10, tzinfo=NY,
    )
    assert not result.unscheduled