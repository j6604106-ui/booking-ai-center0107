"""Telegram bot handler: processes incoming updates via webhook."""

import logging
from dataclasses import dataclass

from knowledge_base import Retriever
from utils.llm import LLMClient
from utils.session_manager import SessionManager
from utils.prompts import get_agent_prompt, assemble_user_message
from utils.self_learning import SelfLearningEngine
from utils.cost_tracker import CostTracker, estimate_tokens
from utils.response_cleaner import clean_response

logger = logging.getLogger(__name__)

# Common Russian greetings — respond directly without KB/LLM
GREETINGS = {
    'привет', 'здравствуйте', 'хай', 'hello', 'hi', 'добрый день',
    'доброе утро', 'добрый вечер', 'салют', 'ку', 'hey',
}

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
    learning: SelfLearningEngine
    cost: CostTracker
    default_agent: str = 'consultant'


def _get_user_agent(config: BotConfig, user_id: int) -> str:
    return _user_agents.get(user_id, config.default_agent)


async def handle_message(config: BotConfig, user_id: int, text: str, agent: str = '') -> str:
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

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
        return '✅ История диалога очищен.'

    # Greetings — respond directly without LLM
    if text_lower in GREETINGS or (len(text_stripped) < 5 and text_lower in GREETINGS):
        return (
            '👋 Привет! Я помогаю с подбором туров, бронированием, страховкой и визами.\n\n'
            'Напишите ваш вопрос — например:\n'
            '• «Хочу поехать в Турцию на неделю»\n'
            '• «Какие безвизовые страны?»\n'
            '• «Сколько стоит страховка?»\n\n'
            'Или выберите агента: /agents'
        )

    # Regular message
    agent = agent or _get_user_agent(config, user_id)

    # Observe question for self-learning
    config.learning.observe(agent, user_id, text)

    relevant = config.retriever.retrieve(text, top_k=3)
    knowledge_context = config.retriever.format_context(relevant)

    # Compact session if history is long
    await config.sessions.compact_if_needed(agent, user_id)

    # Build messages with summary context
    system_prompt = get_agent_prompt(agent)
    messages = config.sessions.build_messages_with_summary(agent, user_id, system_prompt, limit=10)

    user_content = assemble_user_message(text, knowledge_context)
    messages.append({'role': 'user', 'content': user_content})

    # Estimate input tokens
    input_text = ' '.join(m['content'] for m in messages)
    input_tokens = estimate_tokens(input_text)

    # Try LLM call with fallback handling
    response = ''
    for attempt in range(2):
        try:
            raw_response = await config.llm.chat(messages, temperature=0.5)
            response = clean_response(raw_response)
        except Exception as e:
            logger.error(f'LLM error for user {user_id}: {e}')
            return f'⚠️ Сервис временно недоступен. Попробуйте через минуту.'

        # If response is too short or empty, retry with simpler prompt
        if len(response) < 30:
            logger.warning(f'Short/empty response attempt {attempt+1}: "{response[:50]}"')
            if attempt < 1:
                # Simplify prompt for retry
                messages = messages[:-1]
                messages.append({
                    'role': 'user',
                    'content': f'Ответь кратко по-русски на вопрос туриста: {text}',
                })
                continue
            # Final fallback — give helpful default
            return (
                'Я не смог обработать ваш запрос. Попробуйте:\n'
                '• Задать вопрос более подробно\n'
                '• Переключить агента: /agents\n'
                '• Начать заново: /start'
            )

        # Got a good response — break
        break

    # Track cost
    output_tokens = estimate_tokens(response)
    model = config.llm.providers[0].model if config.llm.providers else 'unknown'
    config.cost.log_usage(agent, model, user_id, input_tokens, output_tokens)

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
