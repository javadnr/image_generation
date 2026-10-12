#!/bin/sh
# Runs before every container start: brings the database schema up to
# the current models (alembic upgrade head), then starts the bot.
# Upgrade is idempotent — a no-op when the DB is already current.
set -e
export PYTHONPATH="/app:${PYTHONPATH}"
alembic upgrade head
exec "$@"
