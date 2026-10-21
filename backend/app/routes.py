from fastapi import APIRouter, Request
from datetime import datetime, timezone
from app.scheduler import ScheduleRequest, ScheduleResult, generate_schedule

from app.models import (
    CommitmentCreate,
    CommitmentRead,
    TaskCreate,
    TaskRead,
)

router = APIRouter()
DEV_OWNER_ID = "local-development"


def public_record(document: dict) -> dict:
    record = dict(document)
    record["id"] = str(record.pop("_id"))
    return record


@router.post("/tasks", response_model=TaskRead, status_code=201)
def create_task(body: TaskCreate, request: Request) -> TaskRead:
    document = body.model_dump(mode="python")
    document["owner_id"] = DEV_OWNER_ID
    result = request.app.state.db.tasks.insert_one(document)
    document["_id"] = result.inserted_id
    return TaskRead.model_validate(public_record(document))


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(request: Request) -> list[TaskRead]:
    documents = request.app.state.db.tasks.find(
        {"owner_id": DEV_OWNER_ID}
    ).sort([("deadline", 1), ("priority", -1), ("_id", 1)])
    return [
        TaskRead.model_validate(public_record(document))
        for document in documents
    ]


@router.post("/commitments", response_model=CommitmentRead, status_code=201)
def create_commitment(
    body: CommitmentCreate, request: Request
) -> CommitmentRead:
    document = body.model_dump(mode="python")
    document["owner_id"] = DEV_OWNER_ID
    result = request.app.state.db.commitments.insert_one(document)
    document["_id"] = result.inserted_id
    return CommitmentRead.model_validate(public_record(document))


@router.get("/commitments", response_model=list[CommitmentRead])
def list_commitments(request: Request) -> list[CommitmentRead]:
    documents = request.app.state.db.commitments.find(
        {"owner_id": DEV_OWNER_ID}
    ).sort([("start", 1), ("_id", 1)])
    return [
        CommitmentRead.model_validate(public_record(document))
        for document in documents
    ]

@router.post("/schedule/generate", response_model=ScheduleResult)
def create_schedule(body: ScheduleRequest, request: Request) -> ScheduleResult:
    tasks = list_tasks(request)
    commitments = list_commitments(request)
    return generate_schedule(
        tasks, commitments, body.week_start, now=datetime.now(timezone.utc)
    )