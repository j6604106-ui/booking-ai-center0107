"""LLM client: httpx wrapper over OpenAI-compatible API with retry/backoff."""

import asyncio
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]  # seconds between retries


class LLMClient:
    def __init__(self, api_key: str = '', model: str = '', base_url: str = ''):
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.base_url = base_url or settings.llm_base_url

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
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
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if content:
                        return content
                    # reasoning model returned null content — retry once more
                    logger.warning("LLM returned empty content, retrying...")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    return content  # return empty as last resort

                # Retryable errors: 429 (rate limit), 503 (overloaded)
                if resp.status_code in (429, 503, 502):
                    logger.warning(f"LLM retryable error {resp.status_code}, attempt {attempt + 1}/{MAX_RETRIES}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    raise Exception(f"LLM API error after {MAX_RETRIES} retries: {resp.status_code} {resp.text}")

                # Non-retryable errors: 401, 403, 400, etc
                raise Exception(f"LLM API error {resp.status_code}: {resp.text}")

            except httpx.TimeoutException:
                logger.warning(f"LLM timeout, attempt {attempt + 1}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
                    continue
                raise Exception(f"LLM timeout after {MAX_RETRIES} retries")

        raise Exception(f"LLM failed after {MAX_RETRIES} attempts")
