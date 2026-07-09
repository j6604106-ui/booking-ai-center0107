"""LLM response cleanup: strip reasoning tags, remove English planning text."""

import re

# DeepSeek R1 thinking tags pattern
# Matches: <think>...</think> and any variant
_THINK_PATTERN = re.compile(
    r'<think>.*?</think>',
    re.DOTALL,
)

# Safety filter stubs from OpenRouter
_SAFETY_PATTERN = re.compile(
    r'^User Safety:\s*\w+$',
    re.IGNORECASE,
)

# English planning/reasoning lines that leak into content
_PLANNING_LINES = re.compile(
    r'^(\s*)(We need to|I should|Let me|I will|My approach|Step \d+:)',
    re.IGNORECASE,
)


def clean_response(raw: str) -> str:
    """Clean LLM response: remove reasoning tags, safety stubs, English planning."""
    if not raw:
        return ''

    # Remove thinking tags
    cleaned = _THINK_PATTERN.sub('', raw)

    # Remove safety stubs
    if _SAFETY_PATTERN.match(cleaned.strip()):
        return ''

    # Remove English planning lines that leak into response
    lines = cleaned.split('\n')
    meaningful = []
    for line in lines:
        stripped = line.strip()
        if _PLANNING_LINES.match(stripped):
            continue
        meaningful.append(line)

    result = '\n'.join(meaningful).strip()

    # Remove any remaining <...> XML-style tags
    result = re.sub(r'<[^>]+>', '', result)

    return result
