from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.main import app
from app.models import TaskRead
from app.scheduler import generate_schedule

NY = ZoneInfo('America/New_York')
WEEK = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 0, tzinfo=NY)
TASK = dict(title='Calculus practice', category='Study', estimated_minutes=60,
            deadline='2026-11-16T00:00:00-05:00', description='Solve problems')


def freeze(monkeypatch):
    from app import routes
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)
    monkeypatch.setattr(routes, 'datetime', Clock)


def create(client, **changes):
    response = client.post('/tasks', json={**TASK, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def generate(client):
    response = client.post('/schedule/generate', json={'week_start': str(WEEK)})
    assert response.status_code == 200, response.text
    return response.json()


def test_default_is_24_hours_and_old_stock_settings_upgrade(client):
    from app.db import OWNER_ID
    windows = client.get('/availability').json()['windows']
    assert all(w['start_time'] == '00:00' and w['end_time'] == '24:00' for w in windows)
    app.state.db.settings.insert_one({'_id': OWNER_ID, 'availability': {'windows': [
        dict(weekday=i, start_time='09:00', end_time='21:00') for i in range(7)]}})
    assert client.get('/availability').json()['windows'] == windows
    custom = {'windows': [dict(weekday=0, start_time='23:00', end_time='24:00')]}
    assert client.put('/availability', json=custom).status_code == 200
    assert client.get('/availability').json() == custom


def test_dst_full_days_use_real_midnight_boundaries():
    from app.availability import Availability, availability_intervals
    for day, hours in [(date(2026, 11, 1), 25), (date(2027, 3, 14), 23)]:
        start, end = availability_intervals(Availability(), day, days=1)[0]
        assert (end - start).total_seconds() == hours * 3600
        assert end.astimezone(NY).hour == 0


def test_daytime_soft_preference_and_midnight_when_needed():
    task = TaskRead(id='t', owner_id='local-development', **TASK)
    planned = generate_schedule([task], [], WEEK, now=NOW)
    assert planned.scheduled[0].start.astimezone(NY).hour == 9
    night = task.model_copy(update={'deadline': NOW + timedelta(hours=1)})
    planned = generate_schedule([night], [], WEEK, now=NOW)
    assert planned.scheduled[0].start == NOW


def test_load_balances_eligible_days():
    tasks = [TaskRead(id=str(i), owner_id='local-development', **TASK) for i in range(7)]
    planned = generate_schedule(tasks, [], WEEK, now=NOW)
    assert len({b.start.astimezone(NY).date() for b in planned.scheduled}) == 7


def test_repeat_sessions_group_limits_and_group_deletion(client, monkeypatch):
    freeze(monkeypatch)
    group = client.post('/groups', json={'title': 'Math', 'color': '#4285f4', 'daily_limit': 2}).json()
    task = create(client, group_id=group['id'], repeat_days=[0, 2, 4], sessions_per_day=3)
    plan = generate(client)
    assert len(plan['scheduled']) == 6
    assert len({b['session_key'] for b in plan['scheduled']}) == 6
    assert plan['unscheduled'][0]['task_id'] == task['id']
    assert '3' in plan['unscheduled'][0]['reason']
    assert client.delete('/groups/' + group['id']).status_code == 200
    assert client.get('/tasks').json()[0]['group_id'] is None
    assert client.post('/tasks', json={**TASK, 'group_id': group['id']}).status_code == 422


def test_persist_move_complete_accept_and_learning(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    plan = generate(client)
    block = plan['scheduled'][0]
    assert client.get('/schedule?week_start=2026-11-09').json() == plan
    assert client.get('/learning/status').json()['samples'] == 0
    move = {'start': '2026-11-10T16:00:00-05:00', 'end': '2026-11-10T17:00:00-05:00'}
    moved = client.put('/schedule/blocks/' + block['id'], json=move)
    assert moved.status_code == 200, moved.text
    assert moved.json()['locked']
    assert client.get('/learning/status').json()['samples'] == 1
    again = generate(client)['scheduled'][0]
    assert again['start'] == moved.json()['start']
    accepted = client.post('/schedule/accept', json={'week_start': str(WEEK)})
    assert accepted.json()['accepted'] == 0
    assert client.post('/schedule/accept', json={'week_start': str(WEEK)}).json()['accepted'] == 0
    done = client.patch('/schedule/blocks/' + block['id'], json={'status': 'completed', 'actual_minutes': 55})
    assert done.status_code == 200
    assert generate(client)['scheduled'][0]['status'] == 'completed'
    assert len(generate(client)['scheduled']) == 1
    assert client.post('/learning/train').json()['trained_at']
    create(client, title='Calculus practice worksheet')
    learned = [b for b in generate(client)['scheduled'] if b['task_id'] != task['id']][0]
    assert datetime.fromisoformat(learned['start']).astimezone(NY).hour in [15, 16, 17]


def test_accept_deduplicates_and_persistence_does_not_self_train(client, monkeypatch):
    freeze(monkeypatch)
    create(client)
    generate(client)
    generate(client)
    assert client.get('/learning/status').json()['samples'] == 0
    body = {'week_start': str(WEEK)}
    assert client.post('/schedule/accept', json=body).json()['accepted'] == 1
    assert client.post('/schedule/accept', json=body).json()['accepted'] == 0
    assert client.get('/learning/status').json()['samples'] == 1


def test_moves_reject_conflicts_duration_windows_and_task_deletion_invalidates(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    block = generate(client)['scheduled'][0]
    event = dict(title='Meeting', start='2026-11-10T16:00:00-05:00', end='2026-11-10T17:00:00-05:00')
    assert client.post('/events', json=event).status_code == 201
    assert client.put('/schedule/blocks/' + block['id'], json={k: event[k] for k in ['start', 'end']}).status_code in [404, 409, 422]
    block = generate(client)['scheduled'][0]
    assert client.put('/schedule/blocks/' + block['id'], json={
        'start': '2026-11-11T16:00:00-05:00', 'end': '2026-11-11T16:30:00-05:00'}).status_code == 422
    assert client.put('/tasks/' + task['id'], json={**TASK, 'title': 'Changed'}).status_code == 200
    saved = client.get('/schedule?week_start=2026-11-09').json()['scheduled'][0]
    assert saved['id'] == block['id'] and saved['start'] == block['start']
    assert saved['title'] == 'Changed'
    block = generate(client)['scheduled'][0]
    assert block['title'] == 'Changed'
    assert client.delete('/tasks/' + task['id']).status_code == 200
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'] == []


def test_event_migration_preserves_ids_sources_and_edits(client):
    from app.db import OWNER_ID
    old_id = app.state.db.commitments.insert_one(dict(owner_id=OWNER_ID, title='Old',
        start=datetime(2026, 11, 9, 14, tzinfo=timezone.utc), end=datetime(2026, 11, 9, 15, tzinfo=timezone.utc),
        source_id='canvas:old')).inserted_id
    blocks = client.get('/calendar?week_start=2026-11-09').json()
    assert blocks[0]['id'] == str(old_id)
    assert blocks[0]['source_id'] == 'canvas:old'
    assert client.put('/events/' + str(old_id), json=dict(title='Edited', start=blocks[0]['start'], end=blocks[0]['end'])).status_code == 200
    assert client.get('/calendar?week_start=2026-11-09').json()[0]['title'] == 'Edited'
    assert app.state.db.events.count_documents({}) == 1
    assert app.state.db.commitments.count_documents({}) == 1
    assert client.get('/commitments').status_code == 404


def test_create_manual_session_locks_trains_and_rejects_duplicate(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    body = {'task_id': task['id'], 'start': '2026-11-11T15:00:00-05:00',
            'end': '2026-11-11T16:00:00-05:00'}
    response = client.post('/schedule/blocks', json=body)
    assert response.status_code == 201, response.text
    block = response.json()
    assert block['locked'] and block['session_key'] == 'once'
    assert generate(client)['scheduled'][0]['id'] == block['id']
    assert client.post('/schedule/blocks', json=body).status_code == 409
    assert client.get('/learning/status').json()['samples'] == 1


def test_repeat_manual_limits_and_completion_only_satisfies_that_occurrence(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client, repeat_days=[0, 2], sessions_per_day=2)
    body = {'task_id': task['id'], 'start': '2026-11-09T09:00:00-05:00',
            'end': '2026-11-09T10:00:00-05:00'}
    first = client.post('/schedule/blocks', json=body).json()
    assert client.patch('/schedule/blocks/' + first['id'], json={'status': 'completed'}).status_code == 200
    result = generate(client)
    assert len(result['scheduled']) == 4
    assert sum(b['status'] == 'completed' for b in result['scheduled']) == 1
    assert len({b['id'] for b in result['scheduled']}) == 4
    assert client.put('/schedule/blocks/' + next(b['id'] for b in result['scheduled'] if b['session_key'] == '2026-11-09:1'), json={
        'start': '2026-11-11T12:00:00-05:00', 'end': '2026-11-11T13:00:00-05:00'}).status_code == 422
    assert client.post('/schedule/blocks', json={**body,
        'start': '2026-11-10T12:00:00-05:00', 'end': '2026-11-10T13:00:00-05:00'}).status_code == 422


def test_manual_respects_availability_not_before_deadline_and_caps(client, monkeypatch):
    freeze(monkeypatch)
    group = client.post('/groups', json={'title': 'One daily', 'color': '#123456', 'daily_limit': 1}).json()
    first = create(client, group_id=group['id'], not_before='2026-11-10T10:00:00-05:00',
                   deadline='2026-11-11T18:00:00-05:00')
    second = create(client, group_id=group['id'])
    def place(task, day, hour, end_hour=None):
        return client.post('/schedule/blocks', json={'task_id': task['id'],
            'start': f'2026-11-{day:02}T{hour:02}:00:00-05:00',
            'end': f'2026-11-{day:02}T{end_hour or hour + 1:02}:00:00-05:00'})
    assert place(first, 9, 10).status_code == 422
    assert place(first, 11, 18).status_code == 422
    assert place(first, 10, 10).status_code == 201
    assert place(second, 10, 12).status_code == 422
    client.put('/availability', json={'windows': []})
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'] == []
    assert place(second, 11, 12).status_code == 422


def test_new_fixed_events_prune_conflicts_and_deleted_migration_does_not_resurrect(client, monkeypatch):
    freeze(monkeypatch)
    create(client)
    block = generate(client)['scheduled'][0]
    event = client.post('/events', json={'title': 'Fixed', 'start': block['start'], 'end': block['end']}).json()
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'] == []
    result = generate(client)
    assert all(not (b['start'] < event['end'] and b['end'] > event['start']) for b in result['scheduled'])
    from app.db import OWNER_ID
    legacy = app.state.db.commitments.insert_one(dict(owner_id=OWNER_ID, title='Legacy',
        start=datetime(2026, 11, 12, 14, tzinfo=timezone.utc), end=datetime(2026, 11, 12, 15, tzinfo=timezone.utc))).inserted_id
    client.get('/events')
    assert client.delete('/events/' + str(legacy)).status_code == 200
    assert str(legacy) not in {e['id'] for e in client.get('/calendar?week_start=2026-11-09').json()}


def test_learned_feedback_is_isolated_and_reloadable(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    body = {'task_id': task['id'], 'start': '2026-11-10T16:00:00-05:00', 'end': '2026-11-10T17:00:00-05:00'}
    assert client.post('/schedule/blocks', json=body).status_code == 201
    from app.learning import load_model
    import mongomock
    db = app.state.db
    model = load_model(db)
    query = TaskRead(id='query', owner_id='local-development', **TASK)
    assert model.preferences(query)
    assert not load_model(mongomock.MongoClient(tz_aware=True).other).preferences(query)
    assert len(load_model(db).preferences(query)) == 1


def test_oneoff_cannot_be_regenerated_in_another_week(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client, deadline='2026-12-01T00:00:00-05:00')
    generate(client)
    other = client.post('/schedule/generate', json={'week_start': '2026-11-16'}).json()
    assert other['scheduled'] == []
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'][0]['task_id'] == task['id']


def test_manual_placement_clears_stale_unscheduled_reason(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client, not_before='2026-11-16T12:00:00-05:00', deadline='2026-11-20T18:00:00-05:00')
    assert generate(client)['unscheduled']
    body = {'task_id': task['id'], 'start': '2026-11-16T13:00:00-05:00', 'end': '2026-11-16T14:00:00-05:00'}
    assert client.post('/schedule/blocks', json=body).status_code == 201
    assert client.get('/schedule?week_start=2026-11-09').json()['unscheduled'] == []


def test_invalid_fields_and_explicit_legacy_hours_are_preserved(client):
    windows = {'windows': [dict(weekday=i, start_time='09:00', end_time='21:00') for i in range(7)]}
    assert client.put('/availability', json=windows).status_code == 200
    assert client.get('/availability').json() == windows
    for changes in [{'description': 'x' * 5001}, {'repeat_days': [True]}, {'repeat_days': [7]},
                    {'sessions_per_day': 0}, {'sessions_per_day': 13}]:
        assert client.post('/tasks', json={**TASK, **changes}).status_code == 422
    for changes in [{'daily_limit': 0}, {'color': 'red'}, {'preferred_start': '19:00'}]:
        assert client.post('/groups', json={'title': 'Study', 'color': '#123456', **changes}).status_code == 422


def test_canvas_preserves_task_description(client):
    from tests.test_canvas import calendar, event, request
    content = calendar(event('description-assignment', ':20261109T200000Z', extra='DESCRIPTION:Read chapter four'))
    assert client.post('/canvas/import', json=request(content)).status_code == 200
    assert client.get('/tasks').json()[0]['description'] == 'Read chapter four'


def test_learned_early_hour_can_outweigh_soft_daytime_default(client, monkeypatch):
    freeze(monkeypatch)
    first = create(client)
    assert client.post('/schedule/blocks', json={'task_id': first['id'],
        'start': '2026-11-10T08:00:00-05:00', 'end': '2026-11-10T09:00:00-05:00'}).status_code == 201
    second = create(client, title='Calculus practice exercises')
    block = next(b for b in generate(client)['scheduled'] if b['task_id'] == second['id'])
    assert datetime.fromisoformat(block['start']).astimezone(NY).hour == 8


def test_schedule_and_feedback_timestamps_match_mongodb_millisecond_precision(client, monkeypatch):
    freeze(monkeypatch)
    task = TaskRead(id='t', owner_id='local-development', **TASK)
    now = NOW.replace(microsecond=123456)
    result = generate_schedule([task], [], WEEK, now=now)
    assert result.effective_start.microsecond % 1000 == 0
    assert result.effective_start >= now
    saved = create(client)
    response = client.post('/schedule/blocks', json={'task_id': saved['id'],
        'start': '2026-11-10T16:00:00.123456-05:00', 'end': '2026-11-10T17:00:00.123456-05:00'})
    assert response.status_code == 201
    assert datetime.fromisoformat(response.json()['start']).microsecond % 1000 == 0
    assert client.post('/schedule/accept', json={'week_start': str(WEEK)}).json()['accepted'] == 0
