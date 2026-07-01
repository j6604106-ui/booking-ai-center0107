"""LLM client: minimal httpx wrapper over OpenAI-compatible API (Groq, etc)."""

import httpx

from config import settings


class LLMClient:
    def __init__(self, api_key: str = '', model: str = '', base_url: str = ''):
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.base_url = base_url or settings.llm_base_url

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise Exception(f"LLM API error {resp.status_code}: {resp.text}")
            data = resp.json()
            return data.get('choices', [{}])[0].get('message', {}).get('content', '')
