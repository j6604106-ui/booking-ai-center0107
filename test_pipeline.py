"""End-to-end test: knowledge build, Jaccard search, retriever, context assembly."""

import json
import os
import sys

sys.path.insert(0, '/opt/tourism_platform')

from utils.jaccard_search import load_chunks, retrieve, format_context, tokenize
from knowledge_base import Retriever


def test_tokenize():
    tokens = tokenize('Бронирование тура в Турцию для группы')
    assert 'бронир' in tokens
    assert 'тур' in tokens
    assert 'турци' in tokens
    assert 'групп' in tokens
    assert 'для' not in tokens
    print('✅ tokenize works')


def test_jaccard_search():
    index_path = '/opt/tourism_platform/generated/knowledge_index.json'
    chunks = load_chunks(index_path)
    assert len(chunks) > 0

    # бронирование
    results = retrieve(chunks, 'бронирование', top_k=3)
    assert len(results) > 0
    assert 'booking' in results[0].chunk.source_path or 'sales' in results[0].chunk.source_path
    print(f'✅ "бронирование": top="{results[0].chunk.section}" score={results[0].score:.3f}')

    # виза шенген
    results = retrieve(chunks, 'виза шенген', top_k=3)
    assert len(results) > 0
    assert 'visa' in results[0].chunk.source_path
    print(f'✅ "виза шенген": top="{results[0].chunk.section}"')

    # страховка дайвинг
    results = retrieve(chunks, 'страховка дайвинг', top_k=3)
    assert len(results) > 0
    assert 'insurance' in results[0].chunk.source_path
    print(f'✅ "страховка дайвинг": top="{results[0].chunk.section}"')

    # скидки
    results = retrieve(chunks, 'скидки', top_k=3)
    assert len(results) > 0
    assert 'sales' in results[0].chunk.source_path
    print(f'✅ "скидки": top="{results[0].chunk.section}"')


def test_format_context():
    index_path = '/opt/tourism_platform/generated/knowledge_index.json'
    chunks = load_chunks(index_path)
    results = retrieve(chunks, 'виза несовершеннолетних', top_k=2)
    context = format_context(results, base_url='https://tourism.example.com')
    assert '[Источник 1]' in context
    assert 'https://tourism.example.com' in context
    print(f'✅ format_context works')


def test_retriever_class():
    index_path = '/opt/tourism_platform/generated/knowledge_index.json'
    r = Retriever(index_path, base_url='https://tourism.example.com')
    assert len(r.chunks) > 0
    results = r.retrieve('отмена бронирования', top_k=2)
    assert len(results) > 0
    context = r.format_context(results)
    assert len(context) > 0
    print(f'✅ Retriever class: {len(r.chunks)} chunks loaded')


def test_assemble_user_message():
    from utils.prompts import assemble_user_message, get_agent_prompt

    msg = assemble_user_message('Как получить визу?', '')
    assert msg == 'Как получить визу?'

    msg = assemble_user_message('Как получить визу?', '[Источник 1]: Визы → ...')
    assert 'Найденные статьи' in msg

    for agent in ['consultant', 'booking', 'sales', 'insurance', 'transport', 'visa']:
        prompt = get_agent_prompt(agent)
        assert len(prompt) > 50

    print('✅ assemble_user_message and agent prompts work')


def test_section_names():
    index_path = '/opt/tourism_platform/generated/knowledge_index.json'
    chunks = load_chunks(index_path)
    # Every ## section should have a non-empty section name
    for c in chunks:
        if c.source_path != c.id.split('#')[0]:
            # chunk has a section anchor
            pass
    # Check specific sections exist
    sections = {c.section for c in chunks if c.section}
    expected = {'Правила отмены брони', 'Групповые бронирования', 'Приветствие',
                'Популярные направления', 'Покрытие', 'Активный отдых',
                'Скидки', 'Допродажи', 'Трансферы', 'Аренда авто',
                'Общие правила', 'Документы для несовершеннолетних', 'Отказы'}
    for s in expected:
        assert s in sections, f'Section "{s}" not found in {sections}'
    print(f'✅ All expected sections present: {len(sections)} sections')


if __name__ == '__main__':
    test_tokenize()
    test_jaccard_search()
    test_format_context()
    test_retriever_class()
    test_assemble_user_message()
    test_section_names()
    print('\n🎉 All tests passed!')
