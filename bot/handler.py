"""Telegram bot handler: processes incoming updates via webhook."""

import logging
from dataclasses import dataclass

from knowledge_base import Retriever
from utils.llm import LLMClient
from utils.session_manager import SessionManager
from utils.prompts import get_agent_prompt, assemble_user_message

logger = logging.getLogger(__name__)

AGENTS = {
    'consultant': '🎯 Консультант — выбор направления',
    'booking': '📋 Бронирование — заказ, отмена, группы',
    'sales': '💰 Продажи — скидки, допродажи',
    'insurance': '🛡️ Страхование — страховка, покрытие',
    'transport': '🚗 Транспорт — трансфер, аренда',
    'visa': '🛂 Визы — шенген, документы, отказы',
}

# Per-user agent selection
_user_agents: dict[int, str] = {}


@dataclass
class BotConfig:
    retriever: Retriever
    llm: LLMClient
    sessions: SessionManager
    default_agent: str = 'consultant'


def _get_user_agent(config: BotConfig, user_id: int) -> str:
    return _user_agents.get(user_id, config.default_agent)


async def handle_message(config: BotConfig, user_id: int, text: str, agent: str = '') -> str:
    text_stripped = text.strip()

    # /start command
    if text_stripped == '/start':
        _user_agents[user_id] = config.default_agent
        config.sessions.clear(config.default_agent, user_id)
        agent_list = '\n'.join(f'  {v}' for v in AGENTS.values())
        return (
            '👋 Привет! Я — туристический бот Booking AI Center.\n\n'
            'Выберите агента командой /agent <имя>:\n'
            f'{agent_list}\n\n'
            'Команды:\n'
            '  /clear — очистить историю\n'
            '  /agents — список агентов\n'
            '  /start — начать заново\n\n'
            'Или просто напишите вопрос — я отвечу как консультант.'
        )

    # /agents command
    if text_stripped == '/agents':
        agent_list = '\n'.join(f'  /agent {k} — {v}' for k, v in AGENTS.items())
        current = _get_user_agent(config, user_id)
        return f'Текущий агент: {AGENTS.get(current, current)}\n\nДоступные:\n{agent_list}'

    # /agent <name> — switch agent
    if text_stripped.startswith('/agent'):
        parts = text_stripped.split(maxsplit=1)
        if len(parts) < 2:
            agent_list = '\n'.join(f'  /agent {k}' for k in AGENTS)
            return f'Укажите агент:\n{agent_list}'
        requested = parts[1].strip().lower()
        if requested not in AGENTS:
            return f'❌ Агент "{requested}" не найден. Используйте /agents для списка.'
        _user_agents[user_id] = requested
        config.sessions.clear(requested, user_id)
        return f'✅ Переключено на: {AGENTS[requested]}'

    # /clear command
    if text_stripped == '/clear':
        agent = _get_user_agent(config, user_id)
        config.sessions.clear(agent, user_id)
        return '✅ История диалога очищена.'

    # Regular message
    agent = agent or _get_user_agent(config, user_id)

    relevant = config.retriever.retrieve(text, top_k=2)
    knowledge_context = config.retriever.format_context(relevant)

    history = config.sessions.get_history(agent, user_id, limit=10)

    system_prompt = get_agent_prompt(agent)
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        messages.append({'role': msg['role'], 'content': msg['content']})

    user_content = assemble_user_message(text, knowledge_context)
    messages.append({'role': 'user', 'content': user_content})

    try:
        response = await config.llm.chat(messages)
    except Exception as e:
        logger.error(f'LLM error for user {user_id}: {e}')
        return f'⚠️ Ошибка LLM: {e}'

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
    }
