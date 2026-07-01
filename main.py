"""FastAPI app: Telegram webhook, health check, agent chat endpoints."""

import os
import asyncio

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from config import settings
from knowledge_base import Retriever
from utils.llm import LLMClient
from utils.session_manager import SessionManager
from bot.handler import BotConfig, handle_message, handle_telegram_update

app = FastAPI(title='Tourism Platform', version='1.0.0')

# Lazy init — created once on first request
_bot_config: BotConfig | None = None


def _get_bot_config() -> BotConfig:
    global _bot_config
    if _bot_config is None:
        # Ensure knowledge index exists; build if missing
        if not os.path.exists(settings.knowledge_index_path):
            from scripts.build_knowledge import build_knowledge
            build_knowledge(settings.kb_dir, os.path.dirname(settings.knowledge_index_path))

        retriever = Retriever(settings.knowledge_index_path, settings.knowledge_base_url)
        llm = LLMClient()
        sessions = SessionManager()
        _bot_config = BotConfig(retriever=retriever, llm=llm, sessions=sessions)
    return _bot_config


@app.get('/health')
async def health():
    return JSONResponse({
        'status': 'ok',
        'knowledge_version': '1.0.0',
    })


@app.post('/webhook/{token}')
async def telegram_webhook(token: str, request: Request):
    if token != settings.telegram_bot_token:
        raise HTTPException(status_code=403, detail='Invalid token')

    update = await request.json()
    config = _get_bot_config()

    result = await handle_telegram_update(config, update)
    if result is None:
        return JSONResponse({'status': 'skipped'})

    # Always return 200 to Telegram so it doesn't retry
    return JSONResponse(result)


@app.post('/chat/{agent}')
async def chat_endpoint(agent: str, request: Request):
    body = await request.json()
    user_id = body.get('user_id')
    text = body.get('text', '')
    if not user_id or not text:
        raise HTTPException(status_code=400, detail='user_id and text required')

    config = _get_bot_config()
    response = await handle_message(config, user_id, text, agent)
    return JSONResponse({'response': response, 'agent': agent})


@app.post('/build-kb')
async def build_kb():
    from scripts.build_knowledge import build_knowledge
    count = build_knowledge(settings.kb_dir, os.path.dirname(settings.knowledge_index_path))
    # Reset cached config so next request loads fresh chunks
    global _bot_config
    _bot_config = None
    return JSONResponse({'chunks': count, 'status': 'rebuilt'})
