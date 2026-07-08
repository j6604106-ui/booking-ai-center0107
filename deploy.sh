#!/bin/bash
# ============================================
# Tourism Platform — Deploy Script
# ============================================
# Usage: bash deploy.sh
#
# Prerequisites:
#   - Docker + docker-compose installed
#   - LiteLLM running on port 4000 (or change LLM_BASE_URL)
#   - .env file created from .env.example
#   - DNS configured for your domain

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Copy .env.example and fill in your values:"
    echo "   cp .env.example .env"
    exit 1
fi

# Load .env
set -a; source .env; set +a

# Validate required vars
MISSING=""
for var in TELEGRAM_BOT_TOKEN LLM_API_KEY LLM_MODEL LLM_BASE_URL; do
    if [ -z "${!var}" ] || [ "${!var}" = "YOUR_*" ]; then
        MISSING="$MISSING $var"
    fi
done
if [ -n "$MISSING" ]; then
    echo "❌ Missing required env vars: $MISSING"
    echo "   Edit .env and fill in real values"
    exit 1
fi

echo "🚀 Deploying Tourism Platform..."
echo "   Domain: ${DOMAIN:-localhost}"
echo "   Model: $LLM_MODEL"
echo "   LLM: $LLM_BASE_URL"

# Build and start
docker compose up -d --build

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# Check health
STATUS=$(curl -s http://localhost:8000/health 2>/dev/null || echo "failed")
if echo "$STATUS" | grep -q '"status":"ok"'; then
    echo "✅ Services running!"
    echo "   Health: $STATUS"
else
    echo "⚠️ Health check failed — check docker logs:"
    echo "   docker logs tourism_platform"
fi

# Set Telegram webhook (if domain is configured)
if [ -n "$DOMAIN" ]; then
    WEBHOOK_URL="https://${DOMAIN}/webhook/${TELEGRAM_BOT_TOKEN}"
    echo ""
    echo "🔗 Setting Telegram webhook..."
    RESULT=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}")
    if echo "$RESULT" | grep -q '"ok":true'; then
        echo "✅ Webhook set: $WEBHOOK_URL"
    else
        echo "⚠️ Webhook failed: $RESULT"
        echo "   Caddy may still be getting HTTPS certificate — retry in 1-2 minutes:"
        echo "   curl -s 'https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}'"
    fi

    # Set bot commands
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands" \
        -H "Content-Type: application/json" \
        -d '{"commands":[{"command":"start","description":"Начать заново"},{"command":"agents","description":"Список агентов"},{"command":"agent","description":"Переключить агент"},{"command":"clear","description":"Очистить историю"}]}' > /dev/null
    echo "✅ Telegram menu commands set"
fi

echo ""
echo "🎉 Done! Bot is available at: https://${DOMAIN:-localhost}/"
echo "   Telegram: open your bot and send /start"
