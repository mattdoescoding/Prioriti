from app.main import app


def calendar(*events):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Prioriti//EN",
                         *events, "END:VCALENDAR"])


def event(uid, start, end="", extra="", title="Calculus"):
    return "\r\n".join(["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{title}",
                         f"DTSTART{start}", *([f"DTEND{end}"] if end else []),
                         *([extra] if extra else []), "END:VEVENT"])


def request(content, **changes):
    return dict(content=content, start_date="2026-10-26", end_date="2026-11-30",
                estimated_minutes=45, **changes)


def test_preview_distinguishes_meetings_from_assignment_deadlines(client):
    content = calendar(
        event("event-calendar-event-1", ":20261109T140000Z", ":20261109T150000Z"),
        event("event-assignment-2", ":20261110T045900Z", title="Problem set"),
    )
    result = client.post("/canvas/preview", json=request(content))
    assert result.status_code == 200
    items = result.json()["items"]
    assert [(item["kind"], item["title"]) for item in items] == [
        ("event", "Calculus"), ("task", "Problem set")]
    assert items[0]["start"] == "2026-11-09T14:00:00Z"
    assert items[1]["deadline"] == "2026-11-10T04:59:00Z"
    assert app.state.db.tasks.count_documents({}) == 0


def test_recurrence_preserves_skips_changes_and_clock_changes(client):
    content = calendar(
        event("class-1", ";TZID=America/New_York:20261026T090000",
              ";TZID=America/New_York:20261026T100000",
              "RRULE:FREQ=WEEKLY;COUNT=4\r\nEXDATE;TZID=America/New_York:20261102T090000"),
        event("class-1", ";TZID=America/New_York:20261109T100000",
              ";TZID=America/New_York:20261109T110000",
              "RECURRENCE-ID;TZID=America/New_York:20261109T090000"),
        event("class-1", ";TZID=America/New_York:20261116T090000",
              ";TZID=America/New_York:20261116T100000",
              "RECURRENCE-ID;TZID=America/New_York:20261116T090000\r\nSTATUS:CANCELLED"),
    )
    result = client.post("/canvas/preview", json=request(content))
    assert result.status_code == 200
    assert [item["start"] for item in result.json()["items"]] == [
        "2026-10-26T13:00:00Z", "2026-11-09T15:00:00Z"]


def test_import_is_selective_and_repeat_import_preserves_edits(client):
    content = calendar(
        event("event-assignment-1", ":20261109T200000Z", title="Homework"),
        event("meeting-1", ":20261109T140000Z", ":20261109T150000Z"),
    )
    preview = client.post("/canvas/preview", json=request(content)).json()
    assignment = next(item for item in preview["items"] if item["kind"] == "task")
    body = request(content, selected_ids=[assignment["source_id"]])
    result = client.post("/canvas/import", json=body)
    assert result.status_code == 200
    assert result.json()["imported"] == {"tasks": 1, "events": 0}
    task = client.get("/tasks").json()[0]
    assert task["estimated_minutes"] == 45
    client.patch(f"/tasks/{task['id']}", json={"status": "completed"})
    repeated = client.post("/canvas/import", json=body).json()
    assert repeated["imported"] == {"tasks": 0, "events": 0}
    assert repeated["skipped"] == 1
    assert client.get("/tasks").json()[0]["status"] == "completed"
    assert client.get("/events").json() == []
    preview = client.post("/canvas/preview", json=request(content)).json()
    assert next(item for item in preview["items"] if item["kind"] == "task")["duplicate"]


def test_imported_meetings_are_saved_and_reserve_calendar_time(client):
    content = calendar(event("meeting-1", ":20261109T140000Z", ":20261109T150000Z"))
    result = client.post("/canvas/import", json=request(content))
    assert result.status_code == 200
    assert result.json()["imported"]["events"] == 1
    blocks = client.get("/calendar?week_start=2026-11-09").json()
    assert blocks[0]["title"] == "Calculus"
    assert blocks[0]["end"] == "2026-11-09T15:00:00Z"


def test_all_day_assignments_use_end_of_day_and_untimed_meetings_are_reported(client):
    content = calendar(
        event("event-assignment-3", ";VALUE=DATE:20261109", title="Essay"),
        event("all-day-meeting", ";VALUE=DATE:20261109", ";VALUE=DATE:20261110"),
    )
    preview = client.post("/canvas/preview", json=request(content))
    assert preview.status_code == 200
    assert len(preview.json()["items"]) == 1
    assert preview.json()["items"][0]["deadline"] == "2026-11-10T04:59:00Z"
    assert preview.json()["warnings"]


def test_invalid_calendar_and_unknown_selection_do_not_write_records(client):
    assert client.post("/canvas/import", json=request("not a calendar")).status_code == 422
    content = calendar(event("meeting-1", ":20261109T140000Z", ":20261109T150000Z"))
    result = client.post("/canvas/import", json=request(content, selected_ids=["unknown"]))
    assert result.status_code == 422
    assert app.state.db.events.count_documents({}) == 0


def test_floating_times_and_duration_are_preserved(client):
    content = calendar(event("floating-class", ":20261109T090030", extra="DURATION:PT50M"))
    response = client.post("/canvas/preview", json=request(content))
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["start"] == "2026-11-09T14:00:30Z"
    assert item["end"] == "2026-11-09T14:50:30Z"


def test_unknown_clock_information_is_not_silently_reinterpreted(client):
    content = calendar(event("unknown-zone", ";TZID=Unknown/Invalid:20261109T090000",
                             ";TZID=Unknown/Invalid:20261109T100000"))
    response = client.post("/canvas/preview", json=request(content))
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["warnings"]


def test_dense_recurrence_is_rejected_without_saving(client):
    content = calendar(event("dense", ":20261109T140000Z", ":20261109T140001Z",
                             "RRULE:FREQ=SECONDLY;COUNT=1000000"))
    assert client.post("/canvas/import", json=request(content)).status_code == 422
    assert app.state.db.events.count_documents({}) == 0


def test_cancelled_exception_without_start_does_not_restore_a_meeting(client):
    content = calendar(
        event("class-cancel", ":20261109T140000Z", ":20261109T150000Z", "RRULE:FREQ=WEEKLY;COUNT=3"),
        "BEGIN:VEVENT\r\nUID:class-cancel\r\nRECURRENCE-ID:20261116T140000Z\r\nSTATUS:CANCELLED\r\nEND:VEVENT",
    )
    response = client.post("/canvas/preview", json=request(content))
    assert response.status_code == 200
    assert [item["start"] for item in response.json()["items"]] == [
        "2026-11-09T14:00:00Z", "2026-11-23T14:00:00Z"]
