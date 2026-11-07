import math
import re
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256

from app.classes import NY
from app.db import OWNER_ID
from app.models import database_time

METHOD = "TF-IDF cosine similarity with cyclic hour and weekday preferences"


def tokens(title: str, group_id: str | None) -> list[str]:
    words = re.findall(r"\w+", title.casefold())
    if group_id:
        words.extend([f"group_{group_id}"] * 3)
    return words or ["untitled"]


class PreferenceModel:
    def __init__(self, observations: list[dict]):
        self.observations = observations
        documents = [Counter(tokens(item['title'], item.get('group_id'))) for item in observations]
        counts = Counter(word for document in documents for word in document)
        self.idf = {word: math.log((1 + len(documents)) / (1 + count)) + 1
                    for word, count in counts.items()}
        self.vectors = [self.vector(document) for document in documents]

    def vector(self, counts: Counter) -> dict[str, float]:
        values = {word: count * self.idf[word] for word, count in counts.items() if word in self.idf}
        norm = math.sqrt(sum(value * value for value in values.values()))
        return {word: value / norm for word, value in values.items()} if norm else {}

    def preferences(self, task) -> list[tuple[float, datetime]]:
        vector = self.vector(Counter(tokens(task.title, task.group_id)))
        neighbors = []
        for index, (values, observation) in enumerate(zip(self.vectors, self.observations)):
            similarity = sum(value * values.get(word, 0) for word, value in vector.items())
            if similarity >= 0.15:
                recorded = observation.get('recorded_at', datetime.min.replace(tzinfo=timezone.utc))
                neighbors.append((similarity, recorded, index, observation['start'].astimezone(NY)))
        nearest = sorted(neighbors, key=lambda item: item[:3], reverse=True)[:12]
        return [(similarity, start) for similarity, _, _, start in nearest]

    def penalty(self, preferences, candidate: datetime) -> float:
        if not preferences:
            return 0
        local = candidate.astimezone(NY)
        hour = local.hour + local.minute / 60
        total, weight = 0, 0
        for similarity, previous in preferences:
            other_hour = previous.hour + previous.minute / 60
            hour_distance = min(abs(hour - other_hour), 24 - abs(hour - other_hour))
            day_distance = min(abs(local.weekday() - previous.weekday()),
                               7 - abs(local.weekday() - previous.weekday()))
            total += similarity * (hour_distance * 6 + day_distance * 3)
            weight += similarity
        return total / weight


def load_model(db) -> PreferenceModel:
    return PreferenceModel(list(db.feedback.find({'owner_id': OWNER_ID})))


def learning_status(db) -> dict:
    metadata = db.learning.find_one({'_id': OWNER_ID}) or {}
    return {'samples': db.feedback.count_documents({'owner_id': OWNER_ID}),
            'trained_at': metadata.get('trained_at'), 'method': METHOD}


def train(db) -> dict:
    model = load_model(db)
    db.learning.update_one({'_id': OWNER_ID}, {'$set': {
        'trained_at': datetime.now(timezone.utc).isoformat(), 'samples': len(model.observations),
        'vocabulary': model.idf}}, upsert=True)
    return learning_status(db)


def observe(db, task, block, source: str) -> bool:
    placement = f"{OWNER_ID}:{block.id}:{database_time(block.start).isoformat()}:{database_time(block.end).isoformat()}"
    identity = sha256(placement.encode()).hexdigest()
    result = db.feedback.update_one({'_id': identity}, {'$setOnInsert': {
        'owner_id': OWNER_ID, 'task_id': task.id, 'session_key': block.session_key,
        'title': task.title, 'group_id': task.group_id, 'start': block.start,
        'end': block.end, 'source': source, 'recorded_at': database_time(datetime.now(timezone.utc)),
    }}, upsert=True)
    return result.upserted_id is not None
