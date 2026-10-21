from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.models import CommitmentRead, TaskRead
from app.scheduler import generate_schedule

NY = ZoneInfo("America/New_York")
WEEK = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 8, tzinfo=NY)


def task(**changes):
    values = dict(
        id="a", owner_id="local-development", title="Assignment",
        deadline=datetime(2026, 10, 22, 18, tzinfo=NY),
        priority=2, category="assignment", estimated_minutes=90,
        status="todo",
    )
    values.update(changes)
    return TaskRead(**values)


def test_avoids_commitment_and_other_tasks():
    commitment = CommitmentRead(
        id="class", owner_id="local-development", title="Class",
        start=datetime(2026, 10, 22, 9, tzinfo=NY),
        end=datetime(2026, 10, 22, 10, 7, tzinfo=NY),
    )
    result = generate_schedule(
        [task(id="a"), task(id="b")], [commitment], WEEK, now=NOW
    )
    first, second = result.scheduled
    assert first.start == datetime(2026, 10, 22, 10, 15, tzinfo=NY)
    assert first.end == datetime(2026, 10, 22, 11, 45, tzinfo=NY)
    assert second.start == first.end
    assert second.end <= task().deadline
    assert result.unscheduled == []


def test_deadline_prevents_late_scheduling():
    result = generate_schedule(
        [task(deadline=datetime(2026, 10, 22, 9, 30, tzinfo=NY))],
        [], WEEK, now=NOW,
    )
    assert result.scheduled == []
    assert result.unscheduled[0].code == "no_slot"
    assert result.unscheduled[0].reason


def test_past_deadline_is_explained():
    result = generate_schedule(
        [task(deadline=NOW)], [], WEEK, now=NOW
    )
    assert result.scheduled == []
    assert result.unscheduled[0].code == "deadline_passed"


def test_overbooked_week_returns_remaining_task():
    tasks = [
        task(
            id=str(i), estimated_minutes=720,
            deadline=datetime(2026, 10, 28, 21, tzinfo=NY),
        )
        for i in range(8)
    ]
    result = generate_schedule(tasks, [], WEEK, now=NOW)
    assert len(result.scheduled) == 7
    assert len(result.unscheduled) == 1
    assert result.unscheduled[0].task_id == "7"
    assert result.unscheduled[0].code == "no_slot"
    assert all(
        a.end <= b.start
        for a, b in zip(result.scheduled, result.scheduled[1:])
    )


def test_completed_tasks_are_ignored():
    result = generate_schedule(
        [task(status="completed")], [], WEEK, now=NOW
    )
    assert result.scheduled == []
    assert result.unscheduled == []


def test_rounds_duration_and_never_starts_in_past():
    result = generate_schedule(
        [task(estimated_minutes=16)], [], WEEK,
        now=datetime(2026, 10, 22, 9, 7, 30, tzinfo=NY),
    )
    block = result.scheduled[0]
    assert block.start == datetime(2026, 10, 22, 9, 15, tzinfo=NY)
    assert block.end == datetime(2026, 10, 22, 9, 45, tzinfo=NY)
    assert block.scheduled_minutes == 30


def test_deadline_priority_and_id_give_deterministic_order():
    tasks = [
        task(id="b", priority=3),
        task(id="low", priority=1),
        task(id="early", priority=1,
             deadline=datetime(2026, 10, 22, 12, tzinfo=NY)),
        task(id="a", priority=3),
    ]
    result = generate_schedule(tasks, [], WEEK, now=NOW)
    assert [block.task_id for block in result.scheduled] == [
        "early", "a", "b", "low"
    ]
    assert result == generate_schedule(
        list(reversed(tasks)), [], WEEK, now=NOW
    )


def test_availability_stays_local_across_daylight_saving_change():
    tasks = [
        task(
            id=str(i), estimated_minutes=720,
            deadline=datetime(2026, 11, 6, 21, tzinfo=NY),
        )
        for i in range(3)
    ]
    result = generate_schedule(
        tasks, [], date(2026, 10, 31),
        now=datetime(2026, 10, 30, 8, tzinfo=NY),
    )
    assert [block.start.hour for block in result.scheduled] == [13, 14, 14]
    assert all(
        block.start.astimezone(NY).hour == 9
        and block.end.astimezone(NY).hour == 21
        for block in result.scheduled
    )