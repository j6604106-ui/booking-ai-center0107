"""Cost tracking: per-agent, per-model token usage (AgentForge-inspired).

Logs estimated token counts to Redis. Provides stats endpoint.
"""

import json
import logging
import time

import redis

from config import settings

logger = logging.getLogger(__name__)

COST_KEY_PREFIX = "cost:"
GLOBAL_COST_KEY = "cost:global"
COST_TTL = 86400 * 30  # 30 days


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for Russian, ~0.75 words per token."""
    # Simple approximation: 1 token ≈ 4 characters for Russian
    return max(1, len(text) // 4)


class CostTracker:
    """Track LLM token usage per agent and per model."""

    def __init__(self, r: redis.Redis = None):
        self.r = r or redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

    def log_usage(self, agent: str, model: str, user_id: int,
                  input_tokens: int, output_tokens: int):
        """Log a single LLM call's token usage."""
        entry = json.dumps({
            'agent': agent,
            'model': model,
            'user_id': user_id,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'ts': int(time.time()),
        })

        # Per-agent key
        agent_key = f"{COST_KEY_PREFIX}agent:{agent}"
        self.r.rpush(agent_key, entry)
        self.r.ltrim(agent_key, -1000, -1)
        self.r.expire(agent_key, COST_TTL)

        # Global totals (increment)
        self.r.hincrby(GLOBAL_COST_KEY, f"total:{agent}", input_tokens + output_tokens)
        self.r.hincrby(GLOBAL_COST_KEY, f"input:{agent}", input_tokens)
        self.r.hincrby(GLOBAL_COST_KEY, f"output:{agent}", output_tokens)
        self.r.hincrby(GLOBAL_COST_KEY, f"calls:{agent}", 1)
        self.r.expire(GLOBAL_COST_KEY, COST_TTL)

    def get_stats(self) -> dict:
        """Get cost stats per agent."""
        raw = self.r.hgetall(GLOBAL_COST_KEY)
        agents = set()
        stats = {}
        for key, value in raw.items():
            # Parse "total:consultant" → agent = "consultant", type = "total"
            parts = key.split(':', 1)
            if len(parts) == 2:
                agents.add(parts[1])
        for agent in agents:
            stats[agent] = {
                'total_tokens': int(raw.get(f'total:{agent}', 0)),
                'input_tokens': int(raw.get(f'input:{agent}', 0)),
                'output_tokens': int(raw.get(f'output:{agent}', 0)),
                'calls': int(raw.get(f'calls:{agent}', 0)),
            }
        return stats
