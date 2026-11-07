from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event, RLock

import pytest
from fastapi import Request

from app.db import OWNER_ID
from app.learning import load_model
from app.main import app
from app.models import TaskRead

WEEK = '2026-11-09'
TASK = dict(title='Calculus practice', category='Study', estimated_minutes=45,
            deadline='2026-11-16T00:00:00-05:00')


@pytest.fixture
def workspace(client, monkeypatch):
    from app import routes
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat('2026-11-09T08:00:00-05:00').astimezone(tz)
    monkeypatch.setattr(routes, 'datetime', Clock)
    group = client.post('/groups', json={'title': 'Math', 'color': '#4285f4'}).json()
    task = client.post('/tasks', json={**TASK, 'group_id': group['id'], 'repeat_days': [0, 2], 'sessions_per_day': 2}).json()
    assert client.post('/tasks', json={**TASK, 'status': 'completed'}).status_code == 201
    assert client.put('/availability', json=client.get('/availability').json()).status_code == 200
    assert client.post('/events', json={'title': 'Lecture', 'start': '2026-11-10T12:00:00-05:00', 'end': '2026-11-10T13:00:00-05:00'}).status_code == 201
    plan = client.post('/schedule/generate', json={'week_start': WEEK}).json()
    assert len(plan['scheduled']) == 4
    assert client.patch('/schedule/blocks/' + plan['scheduled'][0]['id'], json={'status': 'completed', 'actual_minutes': 40}).status_code == 200
    assert client.post('/schedule/accept', json={'week_start': WEEK}).json()['accepted'] == 4
    db = app.state.db
    db.plans.insert_one({'owner_id': OWNER_ID, 'week_start': '2026-11-16', 'unscheduled': [{'task_id': task['id']}]})
    for collection in ('tasks', 'schedule_blocks', 'plans', 'feedback'):
        db[collection].insert_one({'_id': 'other', 'owner_id': 'other'})
    db.learning.insert_one({'_id': 'other', 'vocabulary': {'private': 1}})
    return db, TaskRead.model_validate(task)


def test_task_reset_removes_all_progress_but_preserves_settings_and_learning(client, workspace):
    db, _ = workspace
    preserved = {name: list(db[name].find()) for name in ('groups', 'events', 'settings', 'feedback', 'learning')}
    response = client.delete('/tasks')
    assert response.status_code == 200, response.text
    assert response.json() == {'deleted_tasks': 2, 'deleted_sessions': 4}
    assert client.get('/tasks').json() == []
    schedule = client.get('/schedule', params={'week_start': WEEK}).json()
    assert schedule['scheduled'] == schedule['unscheduled'] == []
    assert schedule['events'][0]['title'] == 'Lecture'
    for name in ('tasks', 'schedule_blocks', 'plans'):
        assert list(db[name].find()) == [{'_id': 'other', 'owner_id': 'other'}]
    for name, records in preserved.items():
        assert list(db[name].find()) == records
    assert client.post('/tasks', json=TASK).status_code == 201


def test_learning_reset_forgets_history_and_weights_without_changing_tasks_or_plans(client, workspace):
    db, task = workspace
    assert load_model(db).preferences(task)
    preserved = {name: list(db[name].find()) for name in ('tasks', 'schedule_blocks', 'plans', 'groups', 'events', 'settings')}
    response = client.delete('/learning')
    assert response.status_code == 200, response.text
    assert response.json()['samples'] == 0
    assert response.json()['trained_at'] is None
    assert client.get('/learning/status').json() == response.json()
    assert list(db.feedback.find()) == [{'_id': 'other', 'owner_id': 'other'}]
    assert list(db.learning.find()) == [{'_id': 'other', 'vocabulary': {'private': 1}}]
    model = load_model(db)
    assert model.preferences(task) == []
    assert model.idf == {}
    for name, records in preserved.items():
        assert list(db[name].find()) == records
    assert client.post('/schedule/generate', json={'week_start': WEEK}).status_code == 200
    assert client.get('/learning/status').json()['samples'] == 0
    assert client.post('/schedule/accept', json={'week_start': WEEK}).json()['accepted'] == 4
    assert client.get('/learning/status').json()['samples'] == 4


def test_resets_are_safe_to_repeat_on_an_empty_workspace(client):
    for _ in range(2):
        assert client.delete('/tasks').json() == {'deleted_tasks': 0, 'deleted_sessions': 0}
        response = client.delete('/learning')
        assert response.status_code == 200
        assert response.json()['samples'] == 0
        assert response.json()['trained_at'] is None


def test_reset_waits_for_an_in_flight_canvas_import(client, monkeypatch):
    from app import routes
    from app.canvas import CanvasRequest, import_calendar
    first_written, release, attempted = Event(), Event(), Event()
    lock, blocked = RLock(), []

    class ObservedLock:
        def __enter__(self):
            acquired = lock.acquire(blocking=False)
            blocked.append(not acquired)
            attempted.set()
            if not acquired:
                lock.acquire()

        def __exit__(self, *args):
            lock.release()

    monkeypatch.setattr(routes, 'plan_lock', ObservedLock())
    collection = app.state.db.tasks
    update = collection.update_one

    def pause_first_write(*args, **kwargs):
        result = update(*args, **kwargs)
        if not first_written.is_set():
            first_written.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(collection, 'update_one', pause_first_write)
    events = [f'BEGIN:VEVENT\r\nUID:event-assignment-{i}\r\nSUMMARY:Task {i}\r\nDTSTART:20261109T200000Z\r\nEND:VEVENT' for i in range(2)]
    body = CanvasRequest(content='\r\n'.join(['BEGIN:VCALENDAR', 'VERSION:2.0', *events, 'END:VCALENDAR']), start_date=WEEK, end_date='2026-11-15')
    request = Request({'type': 'http', 'app': app})
    with ThreadPoolExecutor(max_workers=2) as pool:
        importing = pool.submit(import_calendar, body, request)
        try:
            assert first_written.wait(5)
            attempted.clear()
            resetting = pool.submit(routes.delete_all_tasks, request)
            assert attempted.wait(5)
            assert blocked[-1], 'Reset must wait for the entire import to finish.'
        finally:
            release.set()
        assert importing.result()['imported']['tasks'] == 2
        assert resetting.result()['deleted_tasks'] == 2
    assert client.get('/tasks').json() == []
