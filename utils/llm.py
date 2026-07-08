"""LLM client with fallback chain and circuit breaker (AgentForge-inspired).

Fallback chain: tries providers in order until one succeeds.
Circuit breaker: after 5 consecutive failures → 60s cooldown → half-open probe.

Provider config comes from LLM_PROVIDERS env var (JSON array) or defaults.
"""

import asyncio
import json
import logging
import time

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Default fallback chain: primary → fast fallback → local
DEFAULT_PROVIDERS = [
    {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_key": settings.llm_api_key,
        "timeout": 90,
    },
]

RETRY_BACKOFF = [2, 5, 10]
MAX_RETRIES = 3


class CircuitBreaker:
    """Tracks consecutive failures per provider. Opens circuit after threshold."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = {}
        self._open_since: dict[str, float] = {}

    def is_open(self, provider_id: str) -> bool:
        if provider_id not in self._open_since:
            return False
        elapsed = time.monotonic() - self._open_since[provider_id]
        if elapsed >= self.recovery_timeout:
            # Half-open: allow one probe request
            logger.info(f"Circuit breaker half-open for {provider_id}, probing")
            return False
        return True

    def record_success(self, provider_id: str):
        self._failures.pop(provider_id, None)
        self._open_since.pop(provider_id, None)

    def record_failure(self, provider_id: str):
        failures = self._failures.get(provider_id, 0) + 1
        self._failures[provider_id] = failures
        if failures >= self.failure_threshold:
            self._open_since[provider_id] = time.monotonic()
            logger.warning(f"Circuit breaker OPEN for {provider_id} after {failures} failures, cooldown {self.recovery_timeout}s")


class ProviderConfig:
    """Single LLM provider configuration."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout: int = 90):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.id = f"{base_url}/{model}"

    async def chat(self, messages: list[dict], temperature: float = 0.5, max_tokens: int = 8192) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if content:
                        return content
                    logger.warning(f"Provider {self.id} returned empty content, retrying...")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    return content

                if resp.status_code in (429, 503, 502):
                    logger.warning(f"Provider {self.id} retryable {resp.status_code}, attempt {attempt + 1}/{MAX_RETRIES}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    raise Exception(f"Provider {self.id} error after retries: {resp.status_code}")

                raise Exception(f"Provider {self.id} error {resp.status_code}: {resp.text[:200]}")

            except httpx.TimeoutException:
                logger.warning(f"Provider {self.id} timeout, attempt {attempt + 1}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
                    continue
                raise Exception(f"Provider {self.id} timeout after retries")

        raise Exception(f"Provider {self.id} failed after {MAX_RETRIES} attempts")


def _load_providers() -> list[ProviderConfig]:
    """Load provider chain from env or defaults."""
    providers_json = getattr(settings, 'llm_providers', '')
    if providers_json:
        try:
            raw = json.loads(providers_json)
            return [ProviderConfig(**p) for p in raw]
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse LLM_PROVIDERS, using defaults")

    # Build chain from primary + fallbacks
    primary = ProviderConfig(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=90,
    )
    chain = [primary]

    # Add Groq as fast fallback if key available
    groq_key = getattr(settings, 'groq_api_key', '')
    if groq_key:
        chain.append(ProviderConfig(
            model="llama-3.1-8b-instant",
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
            timeout=30,
        ))

    return chain


class LLMClient:
    """LLM client with fallback chain and circuit breaker."""

    def __init__(self):
        self.providers = _load_providers()
        self.breaker = CircuitBreaker()

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.5,
        max_tokens: int = 8192,
    ) -> str:
        """Try providers in fallback order. Skip circuit-open providers."""

        for provider in self.providers:
            if self.breaker.is_open(provider.id):
                logger.info(f"Skipping {provider.id} — circuit open")
                continue

            try:
                result = await provider.chat(messages, temperature, max_tokens)
                self.breaker.record_success(provider.id)
                logger.info(f"LLM success via {provider.id}")
                return result
            except Exception as e:
                self.breaker.record_failure(provider.id)
                logger.warning(f"Provider {provider.id} failed: {e}")
                continue

        # All providers exhausted
        raise Exception("All LLM providers failed — circuit breakers may be open")
