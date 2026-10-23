from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from pymongo import ReturnDocument

from app.classes import ClassInput, ClassRead, NY, expand_classes
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

def class_filter(class_id: str) -> dict:
    if not ObjectId.is_valid(class_id):
        raise HTTPException(status_code=404, detail="Class not found.")

    return {"_id": ObjectId(class_id), "owner_id": DEV_OWNER_ID}


@router.get("/calendar", response_model=list[CommitmentRead])
def calendar_blocks(
    request: Request,
    week_start: date = Query(le=date.max - timedelta(days=7)),
) -> list[CommitmentRead]:
    start = datetime.combine(
        week_start, time.min, tzinfo=NY,
    ).astimezone(timezone.utc)

    end = datetime.combine(
        week_start + timedelta(days=7), time.min, tzinfo=NY,
    ).astimezone(timezone.utc)

    fixed = [
        item for item in list_commitments(request)
        if item.start < end and item.end > start
    ]

    fixed.extend(expand_classes(list_classes(request), week_start))

    return sorted(fixed, key=lambda item: (item.start, item.id))

@router.get("/classes", response_model=list[ClassRead])
def list_classes(request: Request) -> list[ClassRead]:
    documents = request.app.state.db.classes.find(
        {"owner_id": DEV_OWNER_ID}
    ).sort([("title", 1), ("_id", 1)])

    return [
        ClassRead.model_validate(public_record(item))
        for item in documents
    ]

@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(request: Request) -> list[TaskRead]:
    documents = request.app.state.db.tasks.find(
        {"owner_id": DEV_OWNER_ID}
    ).sort([("deadline", 1), ("priority", -1), ("_id", 1)])
    return [
        TaskRead.model_validate(public_record(document))
        for document in documents
    ]

@router.get("/commitments", response_model=list[CommitmentRead])
def list_commitments(request: Request) -> list[CommitmentRead]:
    documents = request.app.state.db.commitments.find(
        {"owner_id": DEV_OWNER_ID}
    ).sort([("start", 1), ("_id", 1)])
    return [
        CommitmentRead.model_validate(public_record(document))
        for document in documents
    ]

@router.post("/tasks", response_model=TaskRead, status_code=201)
def create_task(body: TaskCreate, request: Request) -> TaskRead:
    document = body.model_dump(mode="python")
    document["owner_id"] = DEV_OWNER_ID
    result = request.app.state.db.tasks.insert_one(document)
    document["_id"] = result.inserted_id
    return TaskRead.model_validate(public_record(document))

@router.post("/commitments", response_model=CommitmentRead, status_code=201)
def create_commitment(
    body: CommitmentCreate, request: Request
) -> CommitmentRead:
    document = body.model_dump(mode="python")
    document["owner_id"] = DEV_OWNER_ID
    result = request.app.state.db.commitments.insert_one(document)
    document["_id"] = result.inserted_id
    return CommitmentRead.model_validate(public_record(document))

@router.post("/schedule/generate", response_model=ScheduleResult)
def create_schedule(
    body: ScheduleRequest, request: Request,
) -> ScheduleResult:
    tasks = list_tasks(request)
    commitments = calendar_blocks(request, body.week_start)

    return generate_schedule(
        tasks,
        commitments,
        body.week_start,
        now=datetime.now(timezone.utc),
    )

@router.post("/classes", response_model=ClassRead, status_code=201)
def create_class(body: ClassInput, request: Request) -> ClassRead:
    document = body.model_dump(mode="json")
    document["owner_id"] = DEV_OWNER_ID

    result = request.app.state.db.classes.insert_one(document)
    document["_id"] = result.inserted_id

    return ClassRead.model_validate(public_record(document))


@router.put("/classes/{class_id}", response_model=ClassRead)
def update_class(
    class_id: str, body: ClassInput, request: Request,
) -> ClassRead:
    document = request.app.state.db.classes.find_one_and_update(
        class_filter(class_id),
        {"$set": body.model_dump(mode="json")},
        return_document=ReturnDocument.AFTER,
    )

    if document is None:
        raise HTTPException(status_code=404, detail="Class not found.")

    return ClassRead.model_validate(public_record(document))

@router.delete("/classes/{class_id}")
def delete_class(class_id: str, request: Request) -> dict[str, bool]:
    result = request.app.state.db.classes.delete_one(
        class_filter(class_id)
    )

    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Class not found.")

    return {"deleted": True}