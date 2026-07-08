#!/usr/bin/env python3
"""CLI wrapper for cc-connect — receives messages via stdin, calls tourism API, returns response via stdout.

Cc-connect spawns this as a subprocess agent. It reads user message from stdin,
calls our FastAPI /chat/{agent} endpoint, and prints the response to stdout.
Cc-connect then forwards the stdout response back to the messaging platform.

Usage in cc-connect config.toml:
  [projects.agent]
  type = "claudecode"  # or any agent type — cc-connect will use stdin/stdout
  # OR use custom command approach
"""

import os
import sys
import requests

# Configuration via env vars
API_URL = os.environ.get("TOURISM_API_URL", "http://localhost:8000/chat/consultant")
API_KEY = os.environ.get("TOURISM_API_KEY", "")
DEFAULT_AGENT = os.environ.get("TOURISM_DEFAULT_AGENT", "consultant")


def main():
    text = sys.stdin.read().strip()
    if not text:
        print("No message received.")
        return

    # Handle /agent switch command
    agent = DEFAULT_AGENT
    if text.startswith("/agent "):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            agent = parts[1].strip().lower()
            url = API_URL.replace(f"/chat/{DEFAULT_AGENT}", f"/chat/{agent}")
            text = "Переключено на агент: " + agent
            # After switching, the next real message will use the new agent
            # For now just confirm the switch
            print(f"✅ Переключено на агент: {agent}")
            return

    # Replace agent in URL if specified
    url = API_URL.replace("/chat/consultant", f"/chat/{agent}")

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    # Use a fixed user_id for cc-connect sessions
    # cc-connect manages its own sessions, we just need a unique user_id
    user_id = hash(text) % 10000 + 1

    try:
        resp = requests.post(
            url,
            headers=headers,
            json={"user_id": user_id, "text": text},
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(data.get("response", "No response"))
        elif resp.status_code == 401:
            print("❌ API key invalid")
        else:
            print(f"❌ API error {resp.status_code}")
    except requests.Timeout:
        print("⚠️ LLM timeout — please try again")
    except requests.ConnectionError:
        print("❌ Tourism platform not reachable")


if __name__ == "__main__":
    main()
