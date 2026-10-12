import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from app.db import connect_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    client, database = await run_in_threadpool(connect_database)
    app.state.mongo_client = client
    app.state.db = database

    try:
        yield
    finally:
        await run_in_threadpool(client.close)


app = FastAPI(title="Prioriti API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health(request: Request) -> dict[str, str]:
    try:
        request.app.state.mongo_client.admin.command("ping")
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable; please retry.",
        ) from None

    return {"status": "ok", "database": "connected"}