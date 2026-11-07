from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from math import ceil
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field

from app.models import CalendarEvent, GroupRead, RecordInput, TaskRead, database_time
from app.availability import Availability, availability_intervals
from app.learning import PreferenceModel

NY = ZoneInfo('America/New_York')
UTC = timezone.utc
STEP = timedelta(minutes=15)


class ScheduleRequest(RecordInput):
    week_start: date = Field(le=date.max - timedelta(days=7))


class ScheduledTask(BaseModel):
    id: str
    task_id: str
    title: str
    start: AwareDatetime
    end: AwareDatetime
    scheduled_minutes: int
    duration_source: Literal['user_estimate'] = 'user_estimate'
    locked: bool = False
    status: Literal['planned', 'completed'] = 'planned'
    session_key: str = 'once'
    actual_minutes: int | None = None


class UnscheduledTask(BaseModel):
    task_id: str
    title: str
    code: Literal['window_elapsed', 'deadline_passed', 'duration_exceeds_day',
                  'no_slot', 'not_available', 'partial_repeat']
    reason: str


class ScheduleResult(BaseModel):
    week_start: date
    effective_start: AwareDatetime
    scheduled: list[ScheduledTask]
    unscheduled: list[UnscheduledTask]
    events: list[CalendarEvent]


class BlockPlacement(RecordInput):
    start: AwareDatetime
    end: AwareDatetime


class BlockCreate(BlockPlacement):
    task_id: str
    session_key: str | None = None


class BlockStatus(RecordInput):
    status: Literal['planned', 'completed']
    locked: bool | None = None
    actual_minutes: int | None = Field(default=None, strict=True, gt=0)


def task_occurrences(task: TaskRead, week_start: date) -> list[tuple[date | None, str]]:
    if not task.repeat_days:
        return [(None, 'once')]
    return [(week_start + timedelta(days=i), f'{week_start + timedelta(days=i)}:{session}')
            for i in range(7) if (week_start + timedelta(days=i)).weekday() in task.repeat_days
            for session in range(task.sessions_per_day)]


def block_id(task_id: str, key: str) -> str:
    return sha256(f'{task_id}:{key}'.encode()).hexdigest()[:32]


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    return (datetime.combine(week_start, time.min, tzinfo=NY).astimezone(UTC),
            datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=NY).astimezone(UTC))


def rounded_minutes(task: TaskRead) -> int:
    return ((task.estimated_minutes + 14) // 15) * 15


def overlaps(start: datetime, end: datetime, intervals) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in intervals)


def placement_error(task: TaskRead, block: ScheduledTask, events: list[CalendarEvent],
                    other_blocks: list[ScheduledTask], availability: Availability,
                    groups: list[GroupRead], tasks: list[TaskRead], week_start: date,
                    *, now: datetime | None = None) -> str | None:
    start, end = block.start, block.end
    first, last = week_bounds(week_start)
    if task.status != 'todo':
        return 'This task is completed.'
    if end <= start or (end - start).total_seconds() != rounded_minutes(task) * 60:
        return f'This session must last {rounded_minutes(task)} minutes.'
    if start < first or end > last:
        return 'Place the session inside its seven-day planning window.'
    if now is not None and start < now:
        return 'A planned session cannot start in the past.'
    if end > task.deadline or (task.not_before is not None and start < task.not_before):
        return 'This placement is outside the task available-from time and deadline.'
    local = start.astimezone(NY)
    day = local.date()
    if task.repeat_days:
        if local.weekday() not in task.repeat_days:
            return 'Choose one of this task’s repeat weekdays.'
        try:
            key_day, index = block.session_key.split(':')
            valid_key = key_day == str(day) and 0 <= int(index) < task.sessions_per_day
        except (ValueError, TypeError):
            valid_key = False
        if not valid_key:
            return 'A repeated session must keep its occurrence date and session number.'
    elif block.session_key != 'once':
        return 'A one-off task has one session.'
    if not any(start >= a and end <= b for a, b in availability_intervals(availability, day, days=1)):
        return 'This placement is outside your saved availability.'
    if overlaps(start, end, [(e.start, e.end) for e in events]):
        return 'This placement overlaps a fixed calendar event.'
    others = [b for b in other_blocks if b.id != block.id]
    if overlaps(start, end, [(b.start, b.end) for b in others]):
        return 'This placement overlaps another task session.'
    same_day = [b for b in others if b.start.astimezone(NY).date() == day]
    if sum(b.task_id == task.id for b in same_day) >= (task.sessions_per_day if task.repeat_days else 1):
        return 'This placement exceeds the task’s daily session limit.'
    group = next((g for g in groups if g.id == task.group_id), None)
    if group:
        group_tasks = {t.id for t in tasks if t.group_id == group.id}
        if sum(b.task_id in group_tasks for b in same_day) >= group.daily_limit:
            return 'This placement exceeds the group’s daily session limit.'
    return None


def generate_schedule(tasks: list[TaskRead], events: list[CalendarEvent], week_start: date,
                      *, now: datetime, availability: Availability | None = None,
                      groups: list[GroupRead] | None = None,
                      existing: list[ScheduledTask] | None = None,
                      model: PreferenceModel | None = None) -> ScheduleResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be an aware datetime.')
    window_start, window_end = week_bounds(week_start)
    clock = database_time(now)
    if clock < now:
        clock += timedelta(milliseconds=1)
    effective_start = max(window_start, clock)
    availability = availability if availability is not None else Availability()
    groups_by_id = {group.id: group for group in groups or []}
    tasks_by_id = {task.id: task for task in tasks}
    visible_events = sorted([e for e in events if e.start < window_end and e.end > window_start],
                            key=lambda item: (item.start, item.id))
    windows = availability_intervals(availability, week_start)
    existing = existing or []
    retained = [b for b in existing if b.task_id in tasks_by_id
                and (b.status == 'completed' or (b.locked and tasks_by_id[b.task_id].status == 'todo'))
                and b.start >= window_start and b.start < window_end]
    result = ScheduleResult(week_start=week_start, effective_start=effective_start,
                            scheduled=list(retained), unscheduled=[], events=visible_events)
    busy = [(e.start, e.end) for e in visible_events] + [(b.start, b.end) for b in retained]
    completed = {(b.task_id, b.session_key) for b in existing if b.status == 'completed'}
    satisfied = (completed | {(b.task_id, b.session_key) for b in retained}
                 | {(b.task_id, b.session_key) for b in existing
                    if not window_start <= b.start < window_end})
    day_load = Counter()
    group_load = Counter()
    task_load = Counter()
    for block in retained:
        day = block.start.astimezone(NY).date()
        day_load[day] += block.scheduled_minutes
        task_load[(block.task_id, day)] += 1
        group_load[(tasks_by_id[block.task_id].group_id, day)] += 1
    ordered_tasks = sorted((task for task in tasks if task.status == 'todo'),
                           key=lambda task: (task.deadline, -task.priority, task.id))
    model = model or PreferenceModel([])
    preferences_by_task = {task.id: model.preferences(task) for task in ordered_tasks}
    occurrences = [(task, day, key) for task in ordered_tasks
                   for day, key in task_occurrences(task, week_start) if (task.id, key) not in satisfied]

    def flexibility(occurrence):
        task, occurrence_day, key = occurrence
        task_start = max(effective_start, task.not_before or effective_start)
        duration = timedelta(minutes=rounded_minutes(task))
        eligible = []
        for start, end in windows:
            if occurrence_day is not None and start.astimezone(NY).date() != occurrence_day:
                continue
            candidate = datetime.fromtimestamp(ceil(max(start, task_start).timestamp() / 900) * 900, UTC)
            limit = min(end, task.deadline, window_end)
            if candidate + duration <= limit:
                eligible.append((start.astimezone(NY).date(), limit))
        dates = {day for day, _ in eligible}
        last_end = max((end for _, end in eligible), default=task.deadline)
        return len(dates), last_end, task.deadline, -task.priority, task.id, key

    missing = Counter()
    for task, occurrence_day, key in sorted(occurrences, key=flexibility):
        minutes = rounded_minutes(task)
        duration = timedelta(minutes=minutes)
        task_start = max(effective_start, task.not_before or effective_start)
        preferences = preferences_by_task[task.id]
        group = groups_by_id.get(task.group_id)
        candidates = []
        for day_start, day_end in windows:
            day = day_start.astimezone(NY).date()
            if occurrence_day is not None and day != occurrence_day:
                continue
            if group and group_load[(group.id, day)] >= group.daily_limit:
                continue
            if task_load[(task.id, day)] >= (task.sessions_per_day if task.repeat_days else 1):
                continue
            candidate = datetime.fromtimestamp(ceil(max(day_start, task_start).timestamp() / 900) * 900, UTC)
            while candidate + duration <= min(day_end, task.deadline, window_end):
                end = candidate + duration
                if not overlaps(candidate, end, busy):
                    local = candidate.astimezone(NY)
                    hour = local.hour + local.minute / 60
                    finish_hour = hour + minutes / 60
                    # Hours are a preference; all real minutes in availability remain feasible.
                    daytime = max(0, 9 - hour) * 4 + max(0, finish_hour - 18) * 4
                    if hour < 6 or hour >= 22:
                        daytime += 35
                    score = daytime + max(0, hour - 9) * 0.25 + day_load[day] / 60 * 8
                    if group:
                        preferred_start = int(group.preferred_start[:2]) + int(group.preferred_start[3:]) / 60
                        preferred_end = int(group.preferred_end[:2]) + int(group.preferred_end[3:]) / 60
                        score += max(0, preferred_start - hour) * 3 + max(0, finish_hour - preferred_end) * 3
                    for other in result.scheduled:
                        if other.task_id == task.id and other.start.astimezone(NY).date() == day:
                            gap = abs((candidate - other.start).total_seconds()) / 60
                            score += max(0, 180 - gap) / 15
                    score += model.penalty(preferences, candidate)
                    candidates.append((score, candidate, end))
                candidate += STEP
        if not candidates:
            missing[task.id] += 1
            continue
        _, start, end = min(candidates)
        block = ScheduledTask(id=block_id(task.id, key), task_id=task.id, title=task.title,
                              start=start, end=end, scheduled_minutes=minutes, session_key=key)
        result.scheduled.append(block)
        busy.append((start, end))
        day = start.astimezone(NY).date()
        day_load[day] += minutes
        task_load[(task.id, day)] += 1
        group_load[(task.group_id, day)] += 1
    for task in ordered_tasks:
        minutes = rounded_minutes(task)
        task_start = max(effective_start, task.not_before or effective_start)
        if not missing[task.id]:
            continue
        code, reason = 'no_slot', f'No continuous {minutes}-minute block fits within availability, task dates, fixed events and daily limits.'
        if effective_start >= window_end:
            code, reason = 'window_elapsed', 'This seven-day window has already ended.'
        elif task.deadline <= effective_start:
            code, reason = 'deadline_passed', 'The deadline is at or before the planning start.'
        elif task_start >= window_end:
            code, reason = 'not_available', 'This task becomes available after this seven-day window.'
        elif windows and minutes > max(int((b-a).total_seconds() // 60) for a, b in windows):
            code, reason = 'duration_exceeds_day', 'The rounded duration exceeds your longest availability window.'
        if task.repeat_days:
            code = 'partial_repeat'
            reason = f'{missing[task.id]} of {len(task_occurrences(task, week_start))} repeat sessions could not fit. ' + reason
        result.unscheduled.append(UnscheduledTask(task_id=task.id, title=task.title, code=code, reason=reason))
    result.scheduled.sort(key=lambda block: (block.start, block.task_id, block.session_key))
    return result
