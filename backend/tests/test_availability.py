from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models import TaskRead
from app.scheduler import generate_schedule

NY = ZoneInfo("America/New_York")
WEEK = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 8, tzinfo=NY)


def task(minutes=60):
    return TaskRead(id="study", owner_id="local-development", title="Study",
                    deadline=datetime(2026, 11, 15, 23, tzinfo=NY),
                    category="Study", estimated_minutes=minutes)


def test_availability_is_saved_and_can_close_every_day(client):
    assert len(client.get("/availability").json()["windows"]) == 7
    windows = [{"weekday": 2, "start_time": "18:00", "end_time": "20:00"}]
    assert client.put("/availability", json={"windows": windows}).status_code == 200
    assert client.get("/availability").json()["windows"] == windows
    assert client.put("/availability", json={"windows": []}).status_code == 200
    assert client.get("/availability").json()["windows"] == []


@pytest.mark.parametrize("windows", [
    [{"weekday": 7, "start_time": "09:00", "end_time": "10:00"}],
    [{"weekday": 0, "start_time": "10:00", "end_time": "09:00"}],
    [{"weekday": 0, "start_time": "9:00", "end_time": "10:00"}],
    [{"weekday": 0, "start_time": "09:00", "end_time": "11:00"},
     {"weekday": 0, "start_time": "10:00", "end_time": "12:00"}],
])
def test_invalid_windows_are_rejected(client, windows):
    assert client.put("/availability", json={"windows": windows}).status_code == 422


def test_scheduler_uses_split_windows_and_closed_days():
    from app.availability import Availability

    availability = Availability(windows=[
        dict(weekday=2, start_time="10:07", end_time="11:00"),
        dict(weekday=2, start_time="14:00", end_time="16:00"),
    ])
    result = generate_schedule([task(45), task(90).model_copy(update={"id": "other"})],
                               [], WEEK, now=NOW, availability=availability)
    assert [(item.start.astimezone(NY).strftime("%a %H:%M"), item.scheduled_minutes)
            for item in result.scheduled] == [("Wed 10:15", 45), ("Wed 14:00", 90)]


def test_empty_availability_explains_unscheduled_tasks():
    from app.availability import Availability

    result = generate_schedule([task()], [], WEEK, now=NOW,
                               availability=Availability(windows=[]))
    assert not result.scheduled
    assert result.unscheduled[0].code == "no_slot"


def test_scheduler_allows_blocks_longer_than_old_default_window():
    from app.availability import Availability

    availability = Availability(windows=[dict(weekday=0, start_time="06:00", end_time="23:00")])
    result = generate_schedule([task(780)], [], WEEK, now=NOW, availability=availability)
    assert result.scheduled[0].scheduled_minutes == 780


def test_generation_uses_saved_windows_and_excludes_completed_tasks(client, monkeypatch):
    from app import routes

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)

    monkeypatch.setattr(routes, "datetime", Clock)
    saved = client.post("/tasks", json=task().model_dump(mode="json", exclude={"id", "owner_id", "source_id"})).json()
    client.put("/availability", json={"windows": [dict(weekday=2, start_time="18:00", end_time="20:00")]})
    result = client.post("/schedule/generate", json={"week_start": "2026-11-09"}).json()
    assert result["scheduled"][0]["start"] == "2026-11-11T23:00:00Z"
    client.patch(f"/tasks/{saved['id']}", json={"status": "completed"})
    result = client.post("/schedule/generate", json={"week_start": "2026-11-09"}).json()
    assert not result["scheduled"]
    assert not result["unscheduled"]


def test_clock_change_cannot_shift_availability_outside_saved_hours():
    from app.availability import Availability

    item = task(30).model_copy(update={
        "deadline": datetime(2027, 3, 14, 5, tzinfo=NY),
        "not_before": datetime(2027, 3, 14, 3, tzinfo=NY),
    })
    availability = Availability(windows=[dict(weekday=6, start_time="01:30", end_time="02:30")])
    with pytest.raises(ValueError):
        generate_schedule([item], [], date(2027, 3, 14),
                          now=datetime(2027, 3, 14, 0, tzinfo=NY), availability=availability)
