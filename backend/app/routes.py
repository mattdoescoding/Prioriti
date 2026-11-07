from datetime import date, datetime, time, timedelta, timezone
from threading import RLock

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from pymongo import ReturnDocument

from app.availability import Availability
from app.db import OWNER_ID, migrate_events
from app.classes import ClassInput, ClassRead, NY, expand_classes
from app.learning import learning_status, load_model, observe, train
from app.models import CalendarEventInput, CalendarEvent, GroupInput, GroupRead, TaskCreate, TaskRead, TaskStatus, database_time
from app.scheduler import (BlockCreate, BlockPlacement, BlockStatus, ScheduleRequest, ScheduleResult,
                           ScheduledTask, UnscheduledTask, block_id, generate_schedule, placement_error, task_occurrences,
                           rounded_minutes, week_bounds)

router = APIRouter()
plan_lock = RLock()


def public_record(document: dict) -> dict:
    record = dict(document)
    record['id'] = str(record.pop('_id'))
    return record


def record_filter(record_id: str) -> dict:
    if not ObjectId.is_valid(record_id):
        raise HTTPException(status_code=404, detail='Record not found.')
    return {'_id': ObjectId(record_id), 'owner_id': OWNER_ID}


def update_record(collection, record_id: str, values: dict) -> dict:
    document = collection.find_one_and_update(record_filter(record_id), {'$set': values}, return_document=ReturnDocument.AFTER)
    if document is None:
        raise HTTPException(status_code=404, detail='Record not found.')
    return public_record(document)


def delete_record(collection, record_id: str) -> dict[str, bool]:
    if not collection.delete_one(record_filter(record_id)).deleted_count:
        raise HTTPException(status_code=404, detail='Record not found.')
    return {'deleted': True}


def insert_record(collection, body):
    document = {**body.model_dump(mode='python'), 'owner_id': OWNER_ID}
    document['_id'] = collection.insert_one(document).inserted_id
    return public_record(document)


@router.get('/availability', response_model=Availability)
def get_availability(request: Request) -> Availability:
    db = request.app.state.db
    document = db.settings.find_one({'_id': OWNER_ID}) or {}
    saved = document.get('availability')
    if saved is None:
        return Availability()
    old_stock = {'windows': [dict(weekday=i, start_time='09:00', end_time='21:00') for i in range(7)]}
    if not document.get('availability_version') and saved == old_stock:
        saved = Availability().model_dump()
        db.settings.update_one({'_id': OWNER_ID}, {'$set': {'availability': saved, 'availability_version': 1}})
    return Availability.model_validate(saved)


@router.put('/availability', response_model=Availability)
def save_availability(body: Availability, request: Request) -> Availability:
    with plan_lock:
        request.app.state.db.settings.update_one({'_id': OWNER_ID}, {'$set': {
            'availability': body.model_dump(), 'availability_version': 1}}, upsert=True)
        prune_plans(request)
    return body


@router.get('/events', response_model=list[CalendarEvent])
def list_events(request: Request) -> list[CalendarEvent]:
    migrate_events(request.app.state.db)
    return [CalendarEvent.model_validate(public_record(item)) for item in
            request.app.state.db.events.find({'owner_id': OWNER_ID}).sort([('start', 1), ('_id', 1)])]


@router.get('/calendar', response_model=list[CalendarEvent])
def calendar_blocks(request: Request, week_start: date = Query(le=date.max - timedelta(days=7))) -> list[CalendarEvent]:
    start, end = week_bounds(week_start)
    events = [item for item in list_events(request) if item.start < end and item.end > start]
    events.extend(expand_classes(list_classes(request), week_start))
    return sorted(events, key=lambda item: (item.start, item.id))


@router.get('/classes', response_model=list[ClassRead])
def list_classes(request: Request) -> list[ClassRead]:
    return [ClassRead.model_validate(public_record(item)) for item in
            request.app.state.db.classes.find({'owner_id': OWNER_ID}).sort([('title', 1), ('_id', 1)])]


@router.get('/tasks', response_model=list[TaskRead])
def list_tasks(request: Request) -> list[TaskRead]:
    return [TaskRead.model_validate(public_record(item)) for item in
            request.app.state.db.tasks.find({'owner_id': OWNER_ID}).sort([('deadline', 1), ('priority', -1), ('_id', 1)])]


@router.get('/groups', response_model=list[GroupRead])
def list_groups(request: Request) -> list[GroupRead]:
    return [GroupRead.model_validate(public_record(item)) for item in
            request.app.state.db.groups.find({'owner_id': OWNER_ID}).sort([('title', 1), ('_id', 1)])]


def validate_group(request: Request, group_id: str | None):
    if group_id is not None:
        if not ObjectId.is_valid(group_id) or request.app.state.db.groups.find_one(record_filter(group_id)) is None:
            raise HTTPException(status_code=422, detail='Choose an existing group.')


def invalidate_task(request: Request, task_id: str, *, deleted=False):
    db = request.app.state.db
    query = {'owner_id': OWNER_ID, 'task_id': task_id}
    if not deleted:
        query['status'] = 'planned'
    db.schedule_blocks.delete_many(query)
    db.plans.update_many({'owner_id': OWNER_ID}, {'$pull': {'unscheduled': {'task_id': task_id}}})


@router.post('/tasks', response_model=TaskRead, status_code=201)
def create_task(body: TaskCreate, request: Request):
    with plan_lock:
        validate_group(request, body.group_id)
        return insert_record(request.app.state.db.tasks, body)


@router.delete('/tasks')
def delete_all_tasks(request: Request) -> dict[str, int]:
    with plan_lock:
        db = request.app.state.db
        query = {'owner_id': OWNER_ID}
        tasks = db.tasks.delete_many(query).deleted_count
        sessions = db.schedule_blocks.delete_many(query).deleted_count
        db.plans.delete_many(query)
        return {'deleted_tasks': tasks, 'deleted_sessions': sessions}


@router.put('/tasks/{task_id}', response_model=TaskRead)
def update_task(task_id: str, body: TaskCreate, request: Request):
    with plan_lock:
        validate_group(request, body.group_id)
        result = update_record(request.app.state.db.tasks, task_id, body.model_dump())
        request.app.state.db.schedule_blocks.update_many({'owner_id': OWNER_ID, 'task_id': task_id},
            {'$set': {'title': body.title}})
        prune_plans(request, task_id=task_id)
        refresh_task_diagnostics(request, task_id)
        return result


@router.patch('/tasks/{task_id}', response_model=TaskRead)
def change_task_status(task_id: str, body: TaskStatus, request: Request):
    with plan_lock:
        result = update_record(request.app.state.db.tasks, task_id, body.model_dump())
        invalidate_task(request, task_id)
        return result


@router.delete('/tasks/{task_id}')
def delete_task(task_id: str, request: Request):
    with plan_lock:
        result = delete_record(request.app.state.db.tasks, task_id)
        invalidate_task(request, task_id, deleted=True)
        return result


@router.post('/groups', response_model=GroupRead, status_code=201)
def create_group(body: GroupInput, request: Request):
    return insert_record(request.app.state.db.groups, body)


@router.put('/groups/{group_id}', response_model=GroupRead)
def update_group(group_id: str, body: GroupInput, request: Request):
    with plan_lock:
        result = update_record(request.app.state.db.groups, group_id, body.model_dump())
        prune_plans(request)
        return result


@router.delete('/groups/{group_id}')
def delete_group(group_id: str, request: Request):
    with plan_lock:
        result = delete_record(request.app.state.db.groups, group_id)
        request.app.state.db.tasks.update_many({'owner_id': OWNER_ID, 'group_id': group_id}, {'$set': {'group_id': None}})
        return result


@router.post('/events', response_model=CalendarEvent, status_code=201)
def create_event(body: CalendarEventInput, request: Request):
    with plan_lock:
        migrate_events(request.app.state.db)
        result = insert_record(request.app.state.db.events, body)
        prune_plans(request)
        return result


@router.put('/events/{event_id}', response_model=CalendarEvent)
def update_event(event_id: str, body: CalendarEventInput, request: Request):
    with plan_lock:
        migrate_events(request.app.state.db)
        result = update_record(request.app.state.db.events, event_id, body.model_dump())
        prune_plans(request)
        return result


@router.delete('/events/{event_id}')
def delete_event(event_id: str, request: Request):
    with plan_lock:
        migrate_events(request.app.state.db)
        return delete_record(request.app.state.db.events, event_id)


@router.post('/classes', response_model=ClassRead, status_code=201)
def create_class(body: ClassInput, request: Request):
    with plan_lock:
        document = {**body.model_dump(mode='json'), 'owner_id': OWNER_ID}
        document['_id'] = request.app.state.db.classes.insert_one(document).inserted_id
        prune_plans(request)
        return public_record(document)


@router.put('/classes/{class_id}', response_model=ClassRead)
def update_class(class_id: str, body: ClassInput, request: Request):
    with plan_lock:
        result = update_record(request.app.state.db.classes, class_id, body.model_dump(mode='json'))
        prune_plans(request)
        return result


@router.delete('/classes/{class_id}')
def delete_class(class_id: str, request: Request):
    return delete_record(request.app.state.db.classes, class_id)


def all_blocks(request: Request) -> list[ScheduledTask]:
    return [ScheduledTask.model_validate(item) for item in request.app.state.db.schedule_blocks.find({'owner_id': OWNER_ID})]


def save_block(request: Request, block: ScheduledTask, week_start: date):
    request.app.state.db.schedule_blocks.update_one({'_id': block.id, 'owner_id': OWNER_ID}, {'$set': {
        **block.model_dump(), 'owner_id': OWNER_ID, 'week_start': str(week_start)}}, upsert=True)


def prune_plans(request: Request, task_id: str | None = None):
    tasks = list_tasks(request)
    by_id = {task.id: task for task in tasks}
    groups = list_groups(request)
    availability = get_availability(request)
    blocks = all_blocks(request)
    for block in blocks:
        if block.status == 'completed' or (task_id is not None and block.task_id != task_id):
            continue
        document = request.app.state.db.schedule_blocks.find_one({'_id': block.id, 'owner_id': OWNER_ID})
        week = date.fromisoformat(document['week_start'])
        task = by_id.get(block.task_id)
        try:
            error = (task is None or placement_error(task, block, calendar_blocks(request, week), blocks,
                                                    availability, groups, tasks, week))
        except ValueError:
            error = True
        if error:
            request.app.state.db.schedule_blocks.delete_one({'_id': block.id, 'owner_id': OWNER_ID})
            blocks = [other for other in blocks if other.id != block.id]


def refresh_task_diagnostics(request: Request, task_id: str):
    db = request.app.state.db
    task = task_for_block(request, task_id)
    placements = [block for block in all_blocks(request) if block.task_id == task_id]
    present = {block.session_key for block in placements}
    for plan in db.plans.find({'owner_id': OWNER_ID}):
        previous = next((item for item in plan.get('unscheduled', []) if item['task_id'] == task_id), None)
        diagnostics = [item for item in plan.get('unscheduled', []) if item['task_id'] != task_id]
        if task.status == 'todo' and task.repeat_days:
            required = {key for _, key in task_occurrences(task, date.fromisoformat(plan['week_start']))}
            missing = len(required - present)
            if missing:
                diagnostics.append(UnscheduledTask(task_id=task_id, title=task.title, code='partial_repeat',
                    reason=f'{missing} of {len(required)} repeat sessions remain unplaced. '
                           'Generate a plan to fit the remaining sessions within availability, task dates, '
                           'fixed events and daily limits.').model_dump())
        elif task.status == 'todo' and not placements and previous:
            diagnostics.append({**previous, 'title': task.title})
        db.plans.update_one({'_id': plan['_id'], 'owner_id': OWNER_ID}, {'$set': {'unscheduled': diagnostics}})


@router.get('/schedule', response_model=ScheduleResult)
def get_schedule(request: Request, week_start: date = Query(le=date.max - timedelta(days=7))):
    with plan_lock:
        prune_plans(request)
        db = request.app.state.db
        plan = db.plans.find_one({'owner_id': OWNER_ID, 'week_start': str(week_start)}) or {}
        first, last = week_bounds(week_start)
        return ScheduleResult(week_start=week_start,
            effective_start=plan.get('effective_start', max(first, datetime.now(timezone.utc))),
            scheduled=sorted([block for block in all_blocks(request) if first <= block.start < last], key=lambda b: (b.start, b.task_id, b.session_key)),
            unscheduled=plan.get('unscheduled', []), events=calendar_blocks(request, week_start))


@router.post('/schedule/generate', response_model=ScheduleResult)
def create_schedule(body: ScheduleRequest, request: Request):
    with plan_lock:
        try:
            prune_plans(request)
            result = generate_schedule(list_tasks(request), calendar_blocks(request, body.week_start), body.week_start,
                now=datetime.now(timezone.utc), availability=get_availability(request), groups=list_groups(request),
                existing=all_blocks(request), model=load_model(request.app.state.db))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        db = request.app.state.db
        first, last = week_bounds(body.week_start)
        ids = [block.id for block in result.scheduled]
        db.schedule_blocks.delete_many({'owner_id': OWNER_ID, 'start': {'$gte': first, '$lt': last}, '_id': {'$nin': ids}, 'status': 'planned'})
        for block in result.scheduled:
            save_block(request, block, body.week_start)
        db.plans.update_one({'owner_id': OWNER_ID, 'week_start': str(body.week_start)}, {'$set': {
            'effective_start': result.effective_start, 'unscheduled': [item.model_dump() for item in result.unscheduled]}}, upsert=True)
        return result


def get_block(request: Request, block_id: str):
    document = request.app.state.db.schedule_blocks.find_one({'_id': block_id, 'owner_id': OWNER_ID})
    if document is None:
        raise HTTPException(status_code=404, detail='Session not found. Generate a plan first.')
    return document, ScheduledTask.model_validate(document)


def validate_placement(request: Request, task: TaskRead, block: ScheduledTask, week: date, *, check_now=True):
    try:
        error = placement_error(task, block, calendar_blocks(request, week), all_blocks(request),
            get_availability(request), list_groups(request), list_tasks(request), week,
            now=datetime.now(timezone.utc) if check_now else None)
    except ValueError as exception:
        error = str(exception)
    if error:
        raise HTTPException(status_code=422, detail=error)


def task_for_block(request: Request, task_id: str) -> TaskRead:
    document = request.app.state.db.tasks.find_one(record_filter(task_id))
    if document is None:
        raise HTTPException(status_code=404, detail='Task not found.')
    return TaskRead.model_validate(public_record(document))


@router.post('/schedule/blocks', response_model=ScheduledTask, status_code=201)
def create_manual_block(body: BlockCreate, request: Request):
    with plan_lock:
        task = task_for_block(request, body.task_id)
        day = body.start.astimezone(NY).date()
        week = day - timedelta(days=day.weekday())
        key = body.session_key
        if key is None:
            key = 'once'
            if task.repeat_days:
                keys = {block.session_key for block in all_blocks(request) if block.task_id == task.id}
                key = next((f'{day}:{i}' for i in range(task.sessions_per_day) if f'{day}:{i}' not in keys), '')
        block = ScheduledTask(id=block_id(task.id, key), task_id=task.id, title=task.title,
            start=database_time(body.start), end=database_time(body.end),
            scheduled_minutes=rounded_minutes(task), session_key=key, locked=True)
        if request.app.state.db.schedule_blocks.find_one({'_id': block.id, 'owner_id': OWNER_ID}):
            raise HTTPException(status_code=409, detail='This occurrence already has a placement. Move its existing session.')
        validate_placement(request, task, block, week)
        save_block(request, block, week)
        refresh_task_diagnostics(request, task.id)
        if observe(request.app.state.db, task, block, 'manual'):
            train(request.app.state.db)
        return block


@router.put('/schedule/blocks/{session_id}', response_model=ScheduledTask)
def move_block(session_id: str, body: BlockPlacement, request: Request):
    with plan_lock:
        document, block = get_block(request, session_id)
        if block.status == 'completed':
            raise HTTPException(status_code=422, detail='Reopen this completed session before moving it.')
        task = task_for_block(request, block.task_id)
        block = block.model_copy(update={'start': database_time(body.start),
            'end': database_time(body.end), 'locked': True})
        week = date.fromisoformat(document['week_start'])
        validate_placement(request, task, block, week)
        save_block(request, block, week)
        refresh_task_diagnostics(request, task.id)
        if observe(request.app.state.db, task, block, 'manual'):
            train(request.app.state.db)
        return block


@router.patch('/schedule/blocks/{session_id}', response_model=ScheduledTask)
def change_block_status(session_id: str, body: BlockStatus, request: Request):
    with plan_lock:
        document, block = get_block(request, session_id)
        task = task_for_block(request, block.task_id)
        updates = body.model_dump(exclude_unset=True)
        updates['locked'] = body.locked if body.locked is not None else True
        if body.status == 'completed' and not updates['locked']:
            raise HTTPException(status_code=422, detail='Reopen a completed session before unlocking it.')
        if block.status == 'completed' and body.status == 'planned' and 'actual_minutes' not in updates:
            updates['actual_minutes'] = None
        block = block.model_copy(update=updates)
        if body.status == 'planned':
            validate_placement(request, task, block, date.fromisoformat(document['week_start']), check_now=False)
        save_block(request, block, date.fromisoformat(document['week_start']))
        return block


@router.post('/schedule/accept')
def accept_schedule(body: ScheduleRequest, request: Request):
    with plan_lock:
        plan = get_schedule(request, body.week_start)
        tasks = {task.id: task for task in list_tasks(request)}
        accepted = sum(observe(request.app.state.db, tasks[block.task_id], block, 'accepted')
                       for block in plan.scheduled if block.task_id in tasks)
        if accepted:
            train(request.app.state.db)
        return {'accepted': accepted}


@router.get('/learning/status')
def get_learning_status(request: Request):
    return learning_status(request.app.state.db)


@router.post('/learning/train')
def train_learning(request: Request):
    with plan_lock:
        return train(request.app.state.db)


@router.delete('/learning')
def clear_learning(request: Request):
    with plan_lock:
        db = request.app.state.db
        db.feedback.delete_many({'owner_id': OWNER_ID})
        db.learning.delete_one({'_id': OWNER_ID})
        return learning_status(db)
