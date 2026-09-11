#!/usr/bin/env bash
# setup.sh — One-time setup for Next Level Auto (Cloud-Native, $0)
set -e

echo "🔧 Next Level Auto — Setup"
echo ""

# Check prerequisites
command -v git >/dev/null 2>&1 || { echo "❌ git required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js required"; exit 1; }

echo "✅ Prerequisites OK"

# Initialize git
if [ ! -d .git ]; then
    git init
    git add .
    git commit -m "feat: initial scaffold — cloud-native agentic shop system"
    echo "✅ Git initialized"
fi

# Copy env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚡ .env created — fill in your API keys"
fi

echo ""
echo "🎯 Next steps:"
echo "  1. Fill in .env with your API keys (see README.md)"
echo "  2. Sign up free: OpenRouter, Supabase, Telegram BotFather"
echo "  3. Run: npx wrangler deploy src/workers/telegram-webhook.ts"
echo "  4. Run: cd dashboard && npm install && npm run dev"
echo ""
echo "📖 Full README: README.md"
echo "💰 Total cost: $0 (free tiers)"
