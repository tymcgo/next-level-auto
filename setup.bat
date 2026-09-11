@echo off
REM setup.bat — One-time setup for Next Level Auto on Windows (Cloud-Native, $0)
echo Next Level Auto — Setup (Windows)
echo.

where node >nul 2>nul || (echo Node.js required — install from https://nodejs.org && exit /b 1)
where git >nul 2>nul || (echo Git required — install from https://git-scm.com && exit /b 1)

echo Prerequisites OK

if not exist .git (
    git init
    git add .
    git commit -m "feat: initial scaffold — cloud-native agentic shop system"
    echo Git initialized
)

if not exist .env (
    copy .env.example .env
    echo .env created — fill in your API keys (see README.md)
)

echo.
echo Next steps:
echo   1. Fill in .env with your API keys (see README.md)
echo   2. Sign up free: OpenRouter, Supabase, Telegram BotFather
echo   3. Run: npx wrangler deploy src/workers/telegram-webhook.ts
echo   4. Run: cd dashboard ^&^& npm install ^&^& npm run dev
echo.
echo Full README: README.md
echo Total cost: $0 (free tiers)
