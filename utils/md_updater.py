import re
from pathlib import Path
from .kb_git_manager import commit_kb_changes
from config import settings


def update_md_section(agent_name: str, section_header: str, new_content: str) -> str:
    file_path = Path(settings.kb_dir) / f"{agent_name}_knowledge.md"
    if not file_path.exists():
        return f"Ошибка: Файл {agent_name} не найден."

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = rf"({re.escape(section_header)}.*?\n)(.*?)(?=\n## |\n# |\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

    if match:
        updated = (
            content[:match.start()]
            + match.group(1)
            + new_content.strip()
            + "\n"
            + content[match.end():]
        )
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated)
        commit_kb_changes(agent_name)
        return f"✅ Успешно: Секция '{section_header}' обновлена."
    return f"❌ Ошибка: Секция '{section_header}' не найдена."