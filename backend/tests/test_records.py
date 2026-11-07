import pytest
from bson import ObjectId

from app.main import app


TASK = dict(title="Read chapter", deadline="2026-11-10T18:00:00-05:00",
            priority=2, category="Reading", estimated_minutes=45)
EVENT = dict(title="Study group", start="2026-11-09T10:00:00-05:00",
                  end="2026-11-09T11:00:00-05:00")


@pytest.mark.parametrize("path,body", [("tasks", TASK), ("events", EVENT)])
def test_edit_and_delete_saved_records(client, path, body):
    saved = client.post(f"/{path}", json=body).json()
    changed = client.put(f"/{path}/{saved['id']}", json={**body, "title": "Updated"})
    assert changed.status_code == 200
    assert changed.json()["title"] == "Updated"
    assert client.get(f"/{path}").json()[0]["title"] == "Updated"
    assert client.delete(f"/{path}/{saved['id']}").json() == {"deleted": True}
    assert client.get(f"/{path}").json() == []


def test_complete_and_reopen_task(client):
    task = client.post("/tasks", json=TASK).json()
    for status in ["completed", "todo"]:
        result = client.patch(f"/tasks/{task['id']}", json={"status": status})
        assert result.status_code == 200
        assert result.json()["status"] == status
        assert result.json()["title"] == TASK["title"]
    assert client.patch(f"/tasks/{task['id']}", json={"status": "invalid"}).status_code == 422


@pytest.mark.parametrize("path,body", [("tasks", TASK), ("events", EVENT)])
def test_invalid_missing_and_other_owner_records_cannot_be_changed(client, path, body):
    foreign = app.state.db[path].insert_one({**body, "owner_id": "another-owner"}).inserted_id
    for record_id in ["invalid", str(ObjectId()), str(foreign)]:
        assert client.put(f"/{path}/{record_id}", json=body).status_code == 404
        assert client.delete(f"/{path}/{record_id}").status_code == 404
    assert app.state.db[path].count_documents({"_id": foreign}) == 1


def test_invalid_edit_preserves_saved_task(client):
    task = client.post("/tasks", json=TASK).json()
    result = client.put(f"/tasks/{task['id']}", json={**TASK, "estimated_minutes": 0})
    assert result.status_code == 422
    assert client.get("/tasks").json()[0]["estimated_minutes"] == 45
