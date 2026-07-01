"""Jaccard similarity search over precomputed WikiChunk keywords.

Uses simple Russian suffix stripping for morphological normalization,
so 'бронирование' and 'бронированию' map to the same stem 'бронирован'.
"""

import json
import re
from pathlib import Path

from utils.wiki_chunk import WikiChunk, RetrievedChunk

STOPWORDS = {
    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как',
    'так', 'его', 'ее', 'их', 'мы', 'вы', 'ты', 'это', 'все', 'для',
    'по', 'из', 'от', 'до', 'за', 'о', 'об', 'без', 'при', 'над',
    'под', 'но', 'или', 'ан', 'бы', 'уже', 'еще', 'нет', 'да', 'тоже',
    'только', 'может', 'быть', 'был', 'будет', 'есть', 'к', 'у', 'а',
    'the', 'and', 'to', 'of', 'a', 'in', 'is', 'it', 'or', 'but',
    'on', 'at', 'by', 'for', 'with', 'from', 'as', 'an', 'be',
}

_TOKEN_RE = re.compile(r'\b[а-яёa-z]{3,}\b')

# Russian suffixes to strip for normalization (ordered longest-first)
_RU_SUFFIXES = [
    'ования', 'ование', 'ованию', 'овании', 'ован', 'ующ', 'ующи', 'ующий', 'оват',
    'ость', 'ству', 'ство', 'ств', 'нных', 'нный', 'нно', 'нна',
    'ация', 'ации', 'атор', 'атор',
    'ений', 'ение', 'енн', 'ень', 'ова', 'ову', 'овы', 'овом',
    'ешь', 'ете', 'ют', 'ют', 'яет', 'уешь', 'ует',
    'ился', 'илась', 'ятся', 'яется', 'уется',
    'ого', 'ому', 'ыми', 'ая', 'ое', 'ую', 'ый', 'ой', 'ий',
    'ами', 'ях', 'ов', 'ев', 'ей', 'ём', 'ет', 'ут', 'ют',
    'ла', 'ли', 'л', 'на', 'но', 'ны', 'ну', 'ни',
    'ся', 'сь', 'ов', 'ка', 'ки', 'ке', 'ку',
    'а', 'е', 'и', 'о', 'у', 'ы', 'ь', 'ю', 'я',
]

_MIN_STEM_LEN = 3


def _stem(word: str) -> str:
    if len(word) <= _MIN_STEM_LEN:
        return word
    # Try removing each suffix, pick the one that produces shortest valid stem
    best = word
    for suffix in _RU_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM_LEN:
            candidate = word[:-len(suffix)]
            if len(candidate) < len(best):
                best = candidate
    return best


def tokenize(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in STOPWORDS:
            stem = _stem(w)
            if stem not in seen:
                seen.add(stem)
                result.append(stem)
    return result


def jaccard(query_tokens: list[str], chunk_keywords: list[str]) -> float:
    q = set(query_tokens)
    c = set(chunk_keywords)
    if not q or not c:
        return 0.0
    intersection = len(q & c)
    union = len(q | c)
    return intersection / union if union > 0 else 0.0


def load_chunks(index_path: str) -> list[WikiChunk]:
    path = Path(index_path)
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [
        WikiChunk(
            id=c['id'],
            title=c['title'],
            source_path=c['source_path'],
            section=c['section'],
            text=c['text'],
            keywords=c['keywords'],
        )
        for c in data
    ]


def retrieve(chunks: list[WikiChunk], query: str, top_k: int = 3) -> list[RetrievedChunk]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    scored: list[RetrievedChunk] = []
    for chunk in chunks:
        score = jaccard(query_tokens, chunk.keywords)
        if score > 0:
            scored.append(RetrievedChunk(chunk=chunk, score=score))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def format_context(entries: list[RetrievedChunk], base_url: str = '') -> str:
    if not entries:
        return ''
    parts: list[str] = []
    for i, entry in enumerate(entries):
        chunk = entry.chunk
        url = f"{base_url}/{chunk.source_path.replace('.md', '/')}"
        section_label = f"*{chunk.section}*" if chunk.section else ""
        text_lines = '\n'.join(f"> {line}" for line in chunk.text.split('\n'))
        parts.append(
            f"[Источник {i + 1}]: {chunk.title} → {url}\n"
            f"> {section_label}\n>\n{text_lines}"
        )
    return '\n\n---\n\n'.join(parts)
