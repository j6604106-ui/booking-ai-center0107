"""Session store: dialog history in Redis with TTL and clear support."""

import json
import time

import redis

from config import settings

MAX_HISTORY = 20
SESSION_TTL_SECONDS = 86400 * 7  # 7 days


class SessionManager:
    def __init__(self):
        self.r = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

    def _key(self, agent: str, user_id: int) -> str:
        return f"session:{agent}:{user_id}"

    def add_message(self, agent: str, user_id: int, role: str, content: str):
        key = self._key(agent, user_id)
        self.r.rpush(key, json.dumps({
            'role': role,
            'content': content,
            'ts': int(time.time()),
        }))
        self.r.ltrim(key, -MAX_HISTORY, -1)
        self.r.expire(key, SESSION_TTL_SECONDS)

    def get_history(self, agent: str, user_id: int, limit: int = 10) -> list[dict]:
        key = self._key(agent, user_id)
        raw = self.r.lrange(key, -limit, -1)
        return [json.loads(m) for m in raw]

    def clear(self, agent: str, user_id: int):
        key = self._key(agent, user_id)
        self.r.delete(key)
