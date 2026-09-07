# AGENTS.md — Image Generation Telegram Bot

## Quick Start

```bash
cp .env.example .env   # fill in BOT_TOKEN, OPENAI_API_KEY, ADMIN_IDS
docker compose up --build
```

## Architecture

aiogram 3.x + PostgreSQL 16 + Docker Compose. Persian UI, private chat only.

```
bot/
├── main.py           # entry point, dispatcher, scheduler
├── config.py         # pydantic-settings from .env
├── texts.py          # all Persian strings
├── db/               # SQLAlchemy async models + engine
├── handlers/         # command/message/callback handlers
├── keyboards/        # reply (main menu) + inline keyboards
├── services/         # user CRUD, image gen, queue, reports
└── middlewares/       # DB session, force-join, bot-enabled, private-chat
```

## Key Flows

### Image Generation
1. User sends text → middleware checks: private chat, bot enabled, force-join
2. Handler checks: quota available, user not already generating
3. Acquire tier semaphore → call OpenAI API → send photo → save to disk → consume quota
4. On error: show Persian error, do NOT consume quota

### Image Edit
User replies to bot's photo with text → handler checks disk has image → call OpenAI edit API

### Daily Reset
APScheduler cron at Iran midnight (IRST). Resets `daily_used` for all users.

## DB Schema

- `users`: telegram_id, tier, daily_used, last_reset_date, is_generating, image_width, image_height, optimize_prompt
- `generated_images`: user_id, message_id, file_path, prompt
- `bot_settings`: single row, bot_enabled flag

## Environment Variables

All in `.env`. See `.env.example` for full list. Key ones:
- `BOT_TOKEN`, `OPENAI_API_KEY`, `ADMIN_IDS` — required
- `FREE_MODEL` through `GOLD_MODEL` — per-tier OpenAI model
- `FREE_QUEUE_SIZE` through `GOLD_QUEUE_SIZE` — 0 = unlimited
- `REQUIRED_CHANNELS` — JSON dict for force-join
- `REPORT_CHANNEL_ID` — premium activation reports

## Middleware Order (important)

```
PrivateChat → BotEnabled → ForceJoin → DBSession → Handler
```

DBSession is last so other middlewares can run without needing a session.

## Common Tasks

### Add a new handler
1. Create in `bot/handlers/your_handler.py`
2. Add `router = Router()` + handlers
3. Register in `bot/main.py`: `dp.include_router(your_handler.router)`
4. Add Persian text constants to `bot/texts.py`

### Add new env var
1. Add to `Settings` class in `bot/config.py`
2. Add to `.env.example`
3. Import `from bot.config import settings` where needed

### Add new DB column
1. Add to model in `bot/db/models.py`
2. Delete old DB volume: `docker compose down -v`
3. Restart: `docker compose up --build`
