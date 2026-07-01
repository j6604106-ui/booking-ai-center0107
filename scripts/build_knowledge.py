"""Build knowledge index: scan markdown KB files, split into chunks, precompute keywords.

Outputs generated/knowledge_index.json — never edit manually.
Run this script whenever knowledge_bases/*.md are updated.
"""

import json
import os
import re
import sys
from pathlib import Path

# Use the same stemmer/tokenizer as jaccard_search so index keywords match query tokens
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.jaccard_search import tokenize


def chunk_page(source_path: str, title: str, content: str) -> list[dict]:
    body = content.strip()
    sections = re.split(r'\n(?=## )', body)

    chunks: list[dict] = []

    # If there's content before first ## heading, capture it as intro chunk
    if sections and not sections[0].startswith('## '):
        intro = sections[0].strip()
        if intro and len(intro) >= 20:
            header_match = re.match(r'^#\s+(.+)$', intro)
            section_name = header_match.group(1).strip() if header_match else title
            text = re.sub(r'^#\s+.+\n*', '', intro).strip()
            if text and len(text) >= 20:
                keywords = tokenize(f"{title} {section_name} {text[:500]}")
                chunks.append({
                    'id': f"{source_path}#{section_name}",
                    'title': title,
                    'source_path': source_path,
                    'section': section_name,
                    'text': text,
                    'keywords': keywords,
                })
        sections = sections[1:]

    for section in sections:
        section = section.strip()
        if not section:
            continue
        header_match = re.match(r'^##\s+(.+)', section)
        section_name = header_match.group(1).strip() if header_match else ''
        text = re.sub(r'^##\s+.+\n*', '', section).strip()
        if not text or len(text) < 20:
            continue
        keywords = tokenize(f"{title} {section_name} {text[:500]}")
        chunks.append({
            'id': f"{source_path}#{section_name}",
            'title': title,
            'source_path': source_path,
            'section': section_name,
            'text': text,
            'keywords': keywords,
        })

    return chunks


def build_knowledge(kb_dir: str, output_dir: str) -> int:
    kb_path = Path(kb_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []

    for md_file in sorted(kb_path.glob('**/*.md')):
        content = md_file.read_text(encoding='utf-8')
        rel_path = md_file.relative_to(kb_path)
        # Derive title from filename: "booking_knowledge.md" → "Агент по бронированию"
        agent_name = md_file.stem.replace('_knowledge', '')
        title_line_match = re.match(r'^#\s+(.+)', content)
        title = title_line_match.group(1).strip() if title_line_match else agent_name
        source_path = str(rel_path)

        chunks = chunk_page(source_path, title, content)
        all_chunks.extend(chunks)

    index_file = output_path / 'knowledge_index.json'
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"Built {len(all_chunks)} chunks from {kb_path}")
    print(f"Written to {index_file}")
    return len(all_chunks)


if __name__ == '__main__':
    kb_dir = sys.argv[1] if len(sys.argv) > 1 else '/opt/tourism_platform/knowledge_bases'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '/opt/tourism_platform/generated'
    build_knowledge(kb_dir, output_dir)
