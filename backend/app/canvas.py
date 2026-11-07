from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Literal, Self

import recurring_ical_events
from fastapi import APIRouter, HTTPException, Request
from icalendar import Calendar
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from pymongo.errors import DuplicateKeyError

from app.classes import NY, local_time
from app.db import OWNER_ID, migrate_events
from app.models import CalendarEventInput, RecordInput, TaskCreate

router = APIRouter(prefix="/canvas")


class CanvasRequest(RecordInput):
    content: str = Field(min_length=1, max_length=2_000_000)
    start_date: date
    end_date: date = Field(le=date.max - timedelta(days=1))
    estimated_minutes: int = Field(default=60, strict=True, gt=0)
    selected_ids: list[str] | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if not 0 <= (self.end_date - self.start_date).days <= 365:
            raise ValueError("Choose an import range of up to 366 days.")
        return self


class CanvasItem(BaseModel):
    source_id: str
    title: str
    kind: Literal["task", "event"]
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    deadline: AwareDatetime | None = None
    duplicate: bool = False
    description: str = ""


class CanvasPreview(BaseModel):
    items: list[CanvasItem]
    warnings: list[str]


def event_time(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return local_time(value.date(), value.strftime("%H:%M")) + timedelta(seconds=value.second)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=NY).astimezone(timezone.utc)


def parse_calendar(body: CanvasRequest) -> CanvasPreview:
    try:
        calendar = Calendar.from_ical(body.content)
        if calendar.name != "VCALENDAR":
            raise ValueError("Expected a calendar file.")
        warnings, recurring, valid = [], set(), []
        for component in calendar.subcomponents:
            if component.name != "VEVENT":
                valid.append(component)
                continue
            title = str(component.get("summary", "Untitled event"))
            if (str(component.get("status", "")).upper() == "CANCELLED"
                    and component.get("recurrence-id") and not component.get("dtstart")):
                component.add("dtstart", component.decoded("recurrence-id"))
            if not component.get("uid") or not component.get("dtstart"):
                warnings.append(f"Skipped {title}: missing event ID or date.")
                continue
            if any(component.get(name) and component[name].params.get("TZID")
                   and getattr(component.decoded(name), "tzinfo", None) is None
                   for name in ("dtstart", "dtend")):
                warnings.append(f"Skipped {title}: unsupported clock information.")
                continue
            rule = component.get("rrule", {})
            if rule and (str(rule.get("FREQ", [""])[0]) not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
                         or any(key in rule for key in ("BYSECOND", "BYMINUTE", "BYHOUR"))):
                raise ValueError("This file contains an unsupported recurrence pattern.")
            if any(key in component for key in ("RRULE", "RDATE", "RECURRENCE-ID")):
                recurring.add(str(component["uid"]))
            valid.append(component)
        calendar.subcomponents = valid
        start = datetime.combine(body.start_date, time.min, tzinfo=NY)
        end = datetime.combine(body.end_date + timedelta(days=1), time.min, tzinfo=NY)
        items = {}
        for index, event in enumerate(recurring_ical_events.of(calendar).after(start)):
            when = event.decoded("dtstart")
            begins = event_time(when)
            if begins >= end:
                break
            if index >= 5000:
                raise ValueError("Choose a smaller range; this import exceeds 5,000 events.")
            if str(event.get("status", "")).upper() == "CANCELLED":
                continue
            uid = str(event["uid"])
            title = str(event.get("summary", "")).strip()
            if not title or len(title) > 200:
                warnings.append("Skipped an event with an empty or overly long title.")
                continue
            occurrence = event_time(event.decoded("recurrence-id", when)).isoformat() if uid in recurring else ""
            source_id = "canvas:" + sha256(f"{uid}\n{occurrence}".encode()).hexdigest()
            assignment = "assignment" in uid.lower() or "/assignments/" in str(event.get("url", ""))
            if assignment:
                deadline = begins if isinstance(when, datetime) else event_time(
                    datetime.combine(when, time(23, 59)),
                )
                if deadline < start:
                    continue
                item = CanvasItem(source_id=source_id, title=title, kind="task", deadline=deadline, description=str(event.get("description", ""))[:5000])
            else:
                finishes = event_time(event.decoded("dtend", when))
                if not isinstance(when, datetime) or finishes <= begins:
                    warnings.append(f"Skipped {title}: no timed meeting duration was provided.")
                    continue
                item = CanvasItem(source_id=source_id, title=title, kind="event", start=begins, end=finishes)
            items[source_id] = item
        return CanvasPreview(items=sorted(items.values(), key=lambda item: item.start or item.deadline),
                             warnings=warnings)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise HTTPException(status_code=422, detail=f"Cannot read this calendar: {error}") from None


@router.post("/preview", response_model=CanvasPreview)
def preview_calendar(body: CanvasRequest, request: Request) -> CanvasPreview:
    migrate_events(request.app.state.db)
    preview = parse_calendar(body)
    ids = [item.source_id for item in preview.items]
    existing = set()
    for collection in (request.app.state.db.tasks, request.app.state.db.events):
        existing.update(record["source_id"] for record in collection.find(
            {"owner_id": OWNER_ID, "source_id": {"$in": ids}}, {"source_id": 1},
        ))
    for item in preview.items:
        item.duplicate = item.source_id in existing
    return preview


@router.post("/import")
def import_calendar(body: CanvasRequest, request: Request) -> dict:
    migrate_events(request.app.state.db)
    preview = parse_calendar(body)
    ids = {item.source_id for item in preview.items}
    selected = ids if body.selected_ids is None else set(body.selected_ids)
    if not selected <= ids:
        raise HTTPException(status_code=422, detail="Some selected entries are no longer in this preview.")
    imported, skipped = {"tasks": 0, "events": 0}, 0
    from app.routes import plan_lock, prune_plans
    with plan_lock:
        for item in preview.items:
            if item.source_id not in selected:
                continue
            if item.kind == "task":
                collection = request.app.state.db.tasks
                values = TaskCreate(title=item.title, deadline=item.deadline, category="Canvas",
                                    estimated_minutes=body.estimated_minutes, description=item.description).model_dump()
            else:
                collection = request.app.state.db.events
                values = CalendarEventInput(title=item.title, start=item.start, end=item.end).model_dump()
            identity = {"owner_id": OWNER_ID, "source_id": item.source_id}
            try:
                result = collection.update_one(identity, {"$setOnInsert": {**values, **identity}}, upsert=True)
                if result.upserted_id is not None:
                    imported[collection.name] += 1
                else:
                    skipped += 1
            except DuplicateKeyError:
                skipped += 1
        prune_plans(request)
    return {"imported": imported, "skipped": skipped, "warnings": preview.warnings}
