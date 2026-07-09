#!/usr/bin/env python3
"""Tourism Bot CLI agent for cc-connect tmux mode.

cc-connect spawns this in a tmux session. It reads user messages,
calls our FastAPI /chat/{agent} API, and prints responses to stdout.
cc-connect polls tmux output and sends it back to the messaging platform.

After each response, prints a PROMPT_MARKER "TB>" so cc-connect's
prompt_pattern can detect when the bot finished responding.
"""

import os
import sys
import requests

API_BASE = os.environ.get("TOURISM_API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("TOURISM_API_KEY", "")
PROMPT_MARKER = "TB>"  # cc-connect prompt_pattern will match this

AGENTS = {
    "consultant": "🎯 Консультант",
    "booking": "📋 Бронирование",
    "sales": "💰 Продажи",
    "insurance": "🛡️ Страхование",
    "transport": "🚗 Транспорт",
    "visa": "🛂 Визы",
}

current_agent = "consultant"


def chat(text: str, agent: str) -> str:
    url = f"{API_BASE}/chat/{agent}"
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    try:
        resp = requests.post(url, headers=headers, json={"user_id": 999, "text": text}, timeout=120)
        if resp.status_code == 200:
            return resp.json().get("response", "No response")
        elif resp.status_code == 401:
            return "❌ API key invalid"
        else:
            return f"❌ Error {resp.status_code}"
    except requests.Timeout:
        return "⚠️ Timeout — try again"
    except requests.ConnectionError:
        return "❌ Tourism platform unreachable"


def handle(text: str) -> str:
    global current_agent
    t = text.strip()

    # Agent switch
    if t.startswith("/agent "):
        parts = t.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().lower() in AGENTS:
            current_agent = parts[1].strip().lower()
            return f"✅ Switched to {AGENTS[current_agent]}"
        return "❌ Unknown agent. Use: /agent consultant|booking|sales|insurance|transport|visa"

    # Agent list
    if t == "/agents":
        lines = [f"/agent {k} — {v}" for k, v in AGENTS.items()]
        return f"Current: {AGENTS[current_agent]}\n{chr(10).join(lines)}"

    # Clear
    if t == "/clear":
        return "✅ History cleared"

    # Regular message
    return chat(t, current_agent)


def main():
    # Print ready marker so cc-connect knows agent is initialized + prompt marker
    print(f"Tourism Bot ready. Ask me about travel!\n{PROMPT_MARKER}", flush=True)

    # Interactive loop — read lines from stdin
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            response = handle(line)
            # Print response + prompt marker so cc-connect knows response is complete
            print(f"{response}\n{PROMPT_MARKER}", flush=True)
        except EOFError:
            break
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
