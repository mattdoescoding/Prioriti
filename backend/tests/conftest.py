import mongomock
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    mongo = mongomock.MongoClient(tz_aware=True)
    app.state.db = mongo.prioriti
    app.state.mongo_client = mongo
    client = TestClient(app)
    yield client
    client.close()
    mongo.close()
