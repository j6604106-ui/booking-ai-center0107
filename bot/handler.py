"""Telegram bot handler: processes incoming updates via webhook."""

import asyncio
from dataclasses import dataclass

from knowledge_base import Retriever
from utils.llm import LLMClient
from utils.session_manager import SessionManager
from utils.prompts import get_agent_prompt, assemble_user_message


@dataclass
class BotConfig:
    retriever: Retriever
    llm: LLMClient
    sessions: SessionManager
    default_agent: str = 'consultant'


async def handle_message(config: BotConfig, user_id: int, text: str, agent: str = '') -> str:
    agent = agent or config.default_agent

    # /clear command — reset session
    if text.strip() == '/clear':
        config.sessions.clear(agent, user_id)
        return '✅ История диалога очищена.'

    # 1. Retrieve relevant KB chunks
    relevant = config.retriever.retrieve(text, top_k=2)
    knowledge_context = config.retriever.format_context(relevant)

    # 2. Get session history
    history = config.sessions.get_history(agent, user_id, limit=10)

    # 3. Assemble messages for LLM
    system_prompt = get_agent_prompt(agent)
    messages = [{'role': 'system', 'content': system_prompt}]

    for msg in history:
        messages.append({'role': msg['role'], 'content': msg['content']})

    # 4. Inject context into user message (NOT saved to history)
    user_content = assemble_user_message(text, knowledge_context)
    messages.append({'role': 'user', 'content': user_content})

    # 5. LLM request
    try:
        response = await config.llm.chat(messages)
    except Exception as e:
        return f'⚠️ Ошибка LLM: {e}'

    # 6. Save to history — original user message (without RAG context)
    config.sessions.add_message(agent, user_id, 'user', text)
    config.sessions.add_message(agent, user_id, 'assistant', response)

    return response


async def handle_telegram_update(config: BotConfig, update: dict) -> dict | None:
    message = update.get('message')
    if not message:
        return None

    user_id = message.get('from', {}).get('id')
    text = message.get('text', '')
    if not user_id or not text:
        return None

    response_text = await handle_message(config, user_id, text)

    return {
        'method': 'sendMessage',
        'chat_id': message['chat']['id'],
        'text': response_text,
        'parse_mode': 'Markdown',
    }
