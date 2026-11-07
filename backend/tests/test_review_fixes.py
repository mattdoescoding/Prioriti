from datetime import datetime, timedelta

from app.main import app
from app.models import TaskRead
from app.scheduler import generate_schedule
from tests.test_adaptive import NY, NOW, TASK, WEEK, create, freeze, generate


def test_past_completion_can_be_reopened_and_then_moved_forward(client, monkeypatch):
    freeze(monkeypatch)
    create(client)
    block = generate(client)['scheduled'][0]
    path = '/schedule/blocks/' + block['id']
    assert client.patch(path, json={'status': 'completed', 'actual_minutes': 55}).status_code == 200
    from app import routes
    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return (NOW + timedelta(days=1)).astimezone(tz)
    monkeypatch.setattr(routes, 'datetime', Tomorrow)
    reopened = client.patch(path, json={'status': 'planned'})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()['start'] == block['start']
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'][0]['status'] == 'planned'
    moved = client.put(path, json={'start': '2026-11-11T09:00:00-05:00', 'end': '2026-11-11T10:00:00-05:00'})
    assert moved.status_code == 200, moved.text
    assert client.put(path, json={'start': block['start'], 'end': block['end']}).status_code == 422


def test_equal_similarity_feedback_adapts_to_new_observations(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    first = client.post('/schedule/blocks', json={'task_id': task['id'],
        'start': '2026-11-10T09:00:00-05:00', 'end': '2026-11-10T10:00:00-05:00'}).json()
    path = '/schedule/blocks/' + first['id']
    for hour, count in [(9, 12), (17, 40)]:
        for second in range(count):
            start = datetime(2026, 11, 10, hour, 0, second, tzinfo=NY)
            end = start + timedelta(hours=1)
            response = client.put(path, json={'start': start.isoformat(), 'end': end.isoformat()})
            assert response.status_code == 200, response.text
    assert client.get('/learning/status').json()['samples'] == 52
    # The same feedback cannot gain weight from repeated clicks.
    assert client.put(path, json={'start': start.isoformat(), 'end': end.isoformat()}).status_code == 200
    assert client.get('/learning/status').json()['samples'] == 52
    query = TaskRead(id='query', owner_id='local-development', **TASK)
    from app.learning import load_model
    model = load_model(app.state.db)
    plan = generate_schedule([query], [], WEEK, now=NOW, model=model)
    assert plan.scheduled[0].start.astimezone(NY).hour == 17


def test_moving_repeat_retains_remaining_occurrence_diagnostic(client, monkeypatch):
    freeze(monkeypatch)
    group = client.post('/groups', json={'title': 'Limited', 'color': '#123456', 'daily_limit': 1}).json()
    create(client, group_id=group['id'], repeat_days=[0, 1, 2], sessions_per_day=2)
    plan = generate(client)
    assert len(plan['scheduled']) == 3
    assert plan['unscheduled'][0]['reason'].startswith('3 of 6')
    monday = next(b for b in plan['scheduled'] if b['session_key'].startswith('2026-11-09:'))
    result = client.put('/schedule/blocks/' + monday['id'], json={
        'start': '2026-11-09T12:00:00-05:00', 'end': '2026-11-09T13:00:00-05:00'})
    assert result.status_code == 200
    saved = client.get('/schedule?week_start=2026-11-09').json()
    assert len(saved['unscheduled']) == 1
    assert saved['unscheduled'][0]['reason'].startswith('3 of 6')


def test_manual_repeat_creation_updates_each_window_remaining_count(client, monkeypatch):
    freeze(monkeypatch)
    group = client.post('/groups', json={'title': 'Limited', 'color': '#123456', 'daily_limit': 1}).json()
    task = create(client, group_id=group['id'], repeat_days=[0, 1, 2], sessions_per_day=2,
        deadline='2026-11-23T00:00:00-05:00')
    generate(client)
    other = client.post('/schedule/generate', json={'week_start': '2026-11-16'}).json()
    assert other['unscheduled'][0]['reason'].startswith('3 of 6')
    # Increasing a cap permits an extra explicit placement but does not create it automatically.
    client.put('/groups/' + group['id'], json={'title': 'Limited', 'color': '#123456', 'daily_limit': 2})
    response = client.post('/schedule/blocks', json={'task_id': task['id'],
        'start': '2026-11-09T12:00:00-05:00', 'end': '2026-11-09T13:00:00-05:00'})
    assert response.status_code == 201, response.text
    assert client.get('/schedule?week_start=2026-11-09').json()['unscheduled'][0]['reason'].startswith('2 of 6')
    assert client.get('/schedule?week_start=2026-11-16').json()['unscheduled'][0]['reason'].startswith('3 of 6')


def test_date_constrained_repeat_gets_capacity_before_flexible_oneoff(client, monkeypatch):
    freeze(monkeypatch)
    group = client.post('/groups', json={'title': 'Limited', 'color': '#123456', 'daily_limit': 1}).json()
    oneoff = create(client, title='Flexible oneoff', group_id=group['id'])
    repeated = create(client, title='Monday session', group_id=group['id'], repeat_days=[0])
    plan = generate(client)
    assert len(plan['scheduled']) == 2
    assert not plan['unscheduled']
    repeat_block = next(b for b in plan['scheduled'] if b['task_id'] == repeated['id'])
    oneoff_block = next(b for b in plan['scheduled'] if b['task_id'] == oneoff['id'])
    assert datetime.fromisoformat(repeat_block['start']).astimezone(NY).weekday() == 0
    assert datetime.fromisoformat(oneoff_block['start']).astimezone(NY).weekday() != 0


def test_task_metadata_edit_retains_feasible_placement_without_feedback(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    before = generate(client)['scheduled'][0]
    response = client.put('/tasks/' + task['id'], json={**TASK, 'title': 'Updated title', 'description': 'New detail'})
    assert response.status_code == 200
    blocks = client.get('/schedule?week_start=2026-11-09').json()['scheduled']
    assert len(blocks) == 1
    assert blocks[0]['id'] == before['id'] and blocks[0]['start'] == before['start']
    assert blocks[0]['title'] == 'Updated title'
    assert client.get('/learning/status').json()['samples'] == 0
    response = client.put('/tasks/' + task['id'], json={**TASK, 'estimated_minutes': 120})
    assert response.status_code == 200
    assert client.get('/schedule?week_start=2026-11-09').json()['scheduled'] == []


def test_session_can_be_unpinned_without_creating_feedback(client, monkeypatch):
    freeze(monkeypatch)
    task = create(client)
    block = client.post('/schedule/blocks', json={'task_id': task['id'],
        'start': '2026-11-10T16:00:00-05:00', 'end': '2026-11-10T17:00:00-05:00'}).json()
    path = '/schedule/blocks/' + block['id']
    response = client.patch(path, json={'status': 'planned', 'locked': False})
    assert response.status_code == 200, response.text
    assert not response.json()['locked']
    assert client.get('/learning/status').json()['samples'] == 1
    assert client.patch(path, json={'status': 'completed', 'locked': False}).status_code == 422
    assert client.patch(path, json={'status': 'completed'}).status_code == 200
    assert client.patch(path, json={'status': 'planned', 'locked': False}).status_code == 200
