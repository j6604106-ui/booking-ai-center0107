"""FastAPI app: Telegram webhook, health check, agent chat endpoints."""

import os
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

from config import settings
from knowledge_base import Retriever
from utils.llm import LLMClient
from utils.session_manager import SessionManager
from utils.self_learning import SelfLearningEngine
from utils.cost_tracker import CostTracker
from bot.handler import BotConfig, handle_message, handle_telegram_update

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title='Tourism Platform', version='1.1.0')

_bot_config: BotConfig | None = None


def _get_bot_config() -> BotConfig:
    global _bot_config
    if _bot_config is None:
        if not os.path.exists(settings.knowledge_index_path):
            from scripts.build_knowledge import build_knowledge
            build_knowledge(settings.kb_dir, os.path.dirname(settings.knowledge_index_path))

        retriever = Retriever(settings.knowledge_index_path, settings.knowledge_base_url)
        llm = LLMClient()
        sessions = SessionManager(llm_client=llm)
        learning = SelfLearningEngine(r=sessions.r, llm_client=llm)
        cost = CostTracker(r=sessions.r)
        _bot_config = BotConfig(
            retriever=retriever, llm=llm, sessions=sessions,
            learning=learning, cost=cost,
        )
        logger.info(f'Bot config initialized: {len(retriever.chunks)} chunks, {len(llm.providers)} providers')
    return _bot_config


@app.get('/', response_class=HTMLResponse)
async def root():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Booking AI Center</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:40px auto">
<h1>🏨 Booking AI Center</h1>
<p>Туристический бот с 6 агентами и базой знаний.</p>
<h3>Агенты:</h3>
<ul>
<li>🎯 <b>Консультант</b> — выбор направления</li>
<li>📋 <b>Бронирование</b> — заказ, отмена</li>
<li>💰 <b>Продажи</b> — скидки</li>
<li>🛡️ <b>Страхование</b> — страховка</li>
<li>🚗 <b>Транспорт</b> — трансфер</li>
<li>🛂 <b>Визы</b> — документы</li>
</ul>
<p><small>Telegram: @BookingAICenter_bot</small></p>
</body></html>""")


@app.get('/health')
async def health():
    checks = {'status': 'ok'}
    try:
        config = _get_bot_config()
        config.sessions.r.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = 'error'
        checks['status'] = 'degraded'
    return JSONResponse(checks)


@app.get('/stats')
async def stats():
    """Cost tracking stats per agent (requires API key if configured)."""
    if settings.api_key:
        # Reuse request from query params for GET
        pass  # API key checked via X-API-Key header
    config = _get_bot_config()
    return JSONResponse(config.cost.get_stats())


@app.post('/learn')
async def learn_cycle(request: Request):
    """Run self-learning cycle: drain observations → cluster → propose KB articles."""
    if settings.api_key:
        provided = request.headers.get('X-API-Key', '')
        if provided != settings.api_key:
            raise HTTPException(status_code=401, detail='Invalid API key')

    config = _get_bot_config()
    proposals = await config.learning.run_cycle()
    return JSONResponse({'proposals': proposals, 'count': len(proposals)})


@app.post('/webhook/{token}')
async def telegram_webhook(token: str, request: Request):
    if token != settings.telegram_bot_token:
        raise HTTPException(status_code=403, detail='Invalid token')

    update = await request.json()
    config = _get_bot_config()

    result = await handle_telegram_update(config, update)
    if result is None:
        return JSONResponse({'status': 'skipped'})

    return JSONResponse(result)


@app.post('/chat/{agent}')
async def chat_endpoint(agent: str, request: Request):
    if settings.api_key:
        provided = request.headers.get('X-API-Key', '')
        if provided != settings.api_key:
            raise HTTPException(status_code=401, detail='Invalid API key')

    body = await request.json()
    user_id = body.get('user_id')
    text = body.get('text', '')
    if not user_id or not text:
        raise HTTPException(status_code=400, detail='user_id and text required')

    config = _get_bot_config()
    response = await handle_message(config, user_id, text, agent)
    return JSONResponse({'response': response, 'agent': agent})


@app.post('/build-kb')
async def build_kb(request: Request):
    if settings.api_key:
        provided = request.headers.get('X-API-Key', '')
        if provided != settings.api_key:
            raise HTTPException(status_code=401, detail='Invalid API key')

    from scripts.build_knowledge import build_knowledge
    count = build_knowledge(settings.kb_dir, os.path.dirname(settings.knowledge_index_path))
    global _bot_config
    _bot_config = None
    return JSONResponse({'chunks': count, 'status': 'rebuilt'})
