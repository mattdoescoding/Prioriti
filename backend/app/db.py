import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def connect_database() -> tuple[MongoClient, Database]:
    uri = os.getenv("MONGODB_URI", "").strip()
    database_name = os.getenv("MONGODB_DB", "").strip()

    if not uri or not database_name:
        raise RuntimeError("MONGODB_URI and MONGODB_DB not in backend/.env.")

    client = None
    try:
        client = MongoClient(
            uri,
            tz_aware=True,
            serverSelectionTimeoutMS=3000,
            timeoutMS=5000,
        )
        client.admin.command("ping")
        database = client[database_name]
        database.tasks.create_index([("owner_id", 1), ("deadline", 1)])
        database.commitments.create_index([("owner_id", 1), ("start", 1)])
        return client, database
    except PyMongoError:
        if client is not None:
            client.close()
        raise RuntimeError(
            "Cannot connect to MongoDB. Reference backend/.env and Docker Desktop."
        ) from None