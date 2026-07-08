"""Session store with model-aware compaction (AgentForge-inspired).

When history exceeds threshold → LLM summarizes old turns → 
replaces with summary + keeps last N turns.

Compaction preserves: key decisions, preferences, pending actions.
"""

import json
import logging
import time

import redis

from config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY = 20
SESSION_TTL_SECONDS = 86400 * 7  # 7 days
COMPACTION_THRESHOLD = 16  # trigger compaction when history >= this
COMPACTION_KEEP_TAIL = 5   # keep last N turns after compaction
SUMMARY_KEY_PREFIX = "summary:"


class SessionManager:
    def __init__(self, llm_client=None):
        self.r = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
        self.llm = llm_client  # for compaction summaries

    def _key(self, agent: str, user_id: int) -> str:
        return f"session:{agent}:{user_id}"

    def _summary_key(self, agent: str, user_id: int) -> str:
        return f"{SUMMARY_KEY_PREFIX}{agent}:{user_id}"

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

    def get_full_history(self, agent: str, user_id: int) -> list[dict]:
        key = self._key(agent, user_id)
        raw = self.r.lrange(key, 0, -1)
        return [json.loads(m) for m in raw]

    def get_summary(self, agent: str, user_id: int) -> str | None:
        key = self._summary_key(agent, user_id)
        val = self.r.get(key)
        return val if val else None

    def clear(self, agent: str, user_id: int):
        key = self._key(agent, user_id)
        self.r.delete(key)
        self.r.delete(self._summary_key(agent, user_id))

    async def compact_if_needed(self, agent: str, user_id: int) -> bool:
        """Compact session if history exceeds threshold.

        Returns True if compaction was performed.
        """
        history = self.get_full_history(agent, user_id)
        if len(history) < COMPACTION_THRESHOLD:
            return False

        if not self.llm:
            logger.warning("No LLM client for compaction, skipping")
            return False

        logger.info(f"Compacting session {agent}:{user_id}, {len(history)} messages")

        # Separate: old messages to summarize + tail to keep
        old = history[:-COMPACTION_KEEP_TAIL]
        tail = history[-COMPACTION_KEEP_TAIL:]

        if not old:
            return False

        # Build summary prompt
        existing_summary = self.get_summary(agent, user_id)
        old_text = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in old)

        summary_prompt = (
            "Сжай историю диалога туристического бота в краткое резюме.\n"
            "Сохраните: ключевые решения, предпочтения клиента, обсуждённые туры, важные факты.\n"
            "Резюме: 2-3 предложения, по-русски.\n"
        )
        if existing_summary:
            summary_prompt += f"\nПредыдущее резюме: {existing_summary}\n"
        summary_prompt += f"\nДиалог для сжатия:\n{old_text}"

        try:
            summary = await self.llm.chat(
                [{'role': 'system', 'content': summary_prompt}],
                temperature=0.3,
                max_tokens=512,
            )
        except Exception as e:
            logger.warning(f"Compaction LLM call failed: {e}")
            return False

        # Strip reasoning tags
        import re
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()

        # Store summary in Redis
        summary_key = self._summary_key(agent, user_id)
        self.r.set(summary_key, summary, ex=SESSION_TTL_SECONDS)

        # Replace history: drop old, keep tail
        main_key = self._key(agent, user_id)
        self.r.delete(main_key)
        for msg in tail:
            self.r.rpush(main_key, json.dumps(msg))
        self.r.expire(main_key, SESSION_TTL_SECONDS)

        logger.info(f"Compacted {agent}:{user_id}: {len(history)} → summary + {len(tail)} messages")
        return True

    def build_messages_with_summary(self, agent: str, user_id: int, system_prompt: str,
                                     limit: int = 10) -> list[dict]:
        """Build messages list including existing summary as context."""
        messages = [{'role': 'system', 'content': system_prompt}]

        summary = self.get_summary(agent, user_id)
        if summary:
            # Inject summary as system context (not a message from user/assistant)
            messages.append({
                'role': 'system',
                'content': f"Краткое резюме предыдущего диалога:\n{summary}",
            })

        history = self.get_history(agent, user_id, limit=limit)
        for msg in history:
            messages.append({'role': msg['role'], 'content': msg['content']})

        return messages
