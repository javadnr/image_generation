"""Automated daily PostgreSQL backup.

Every day at 00:00 Asia/Tehran the primary (Telegram) instance dumps every
project database (Telegram + Bale) to SQL, packs them into one
``Image_Generation_YYYY-MM-DD_HH-MM-SS.tar.gz`` archive, and uploads it to
BACKUP_TELEGRAM_CHANNEL_ID.

Only one run happens at a time: APScheduler ``max_instances=1`` + an
``asyncio.Lock`` serialize within the process, and a Postgres advisory lock
serializes across processes (duplicate schedulers / workers are safe).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import make_url

from bot.config import settings

logger = logging.getLogger(__name__)

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# Telegram Bot API document upload ceiling (50 MB for bots).
TELEGRAM_UPLOAD_LIMIT = 50 * 1024 * 1024

# pg_dump hard timeout per database (30 min).
DUMP_TIMEOUT = 1800

# Arbitrary constant key for the cross-process advisory lock.
_LOCK_KEY = 9132441

# Databases never dumped (Postgres maintenance db; template dbs are already
# filtered out by the query).
_EXCLUDED_DATABASES = {"postgres"}

_run_lock = asyncio.Lock()

# Manual-backup reservation: claimed synchronously by the button handler so
# two rapid clicks cannot both start a job (the run lock alone can't be
# claimed without awaiting).
_reserved = False


def backup_in_progress() -> bool:
    """True while a backup is running or a manual one is reserved."""
    return _reserved or _run_lock.locked()


def try_reserve_backup() -> bool:
    """Atomically claim a manual backup slot. False when one is already active."""
    global _reserved
    if _reserved or _run_lock.locked():
        return False
    _reserved = True
    return True


def release_reservation() -> None:
    global _reserved
    _reserved = False


def backup_filename(now: datetime | None = None) -> str:
    """Image_Generation_YYYY-MM-DD_HH-MM-SS.tar.gz in Asia/Tehran time."""
    now = now or datetime.now(TEHRAN_TZ)
    return f"Image_Generation_{now.strftime('%Y-%m-%d_%H-%M-%S')}.tar.gz"


def _pg_params() -> dict:
    """Connection params for pg_dump, parsed from DATABASE_URL (no secrets leaked)."""
    url = make_url(settings.DATABASE_URL)
    return {
        "host": url.host or "postgres",
        "port": str(url.port or 5432),
        "user": url.username or "bot",
        "password": url.password or "",
    }


async def discover_databases() -> list:
    """All connectable, non-template project databases on the server."""
    from bot.db.engine import async_session
    async with async_session() as session:
        result = await session.execute(text(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false AND datallowconn = true "
            "ORDER BY datname"
        ))
        return [
            row[0] for row in result.all()
            if row[0] not in _EXCLUDED_DATABASES
        ]


def dump_database(dbname: str, dest_dir: str, params: dict | None = None) -> str:
    """Run pg_dump for one database. Raises on failure; returns the file path."""
    params = params or _pg_params()
    out_path = os.path.join(dest_dir, f"{dbname}.sql")
    cmd = [
        "pg_dump",
        "-h", params["host"], "-p", params["port"],
        "-U", params["user"], "-d", dbname,
        "--no-owner", "--no-privileges",
        "--clean", "--if-exists",
        "-f", out_path,
    ]
    env = {**os.environ, "PGPASSWORD": params["password"]}
    logger.info("pg_dump start: %s -> %s", dbname, out_path)
    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, timeout=DUMP_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pg_dump failed for {dbname}: {result.stderr.strip()[:500]}"
        )
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"pg_dump produced empty output for {dbname}")
    return out_path


def build_archive(sql_files: list, archive_path: str) -> str:
    """Package SQL dumps into a single gzip-compressed tar archive."""
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sql_files:
            tar.add(path, arcname=os.path.basename(path))
    return archive_path


def validate_archive(archive_path: str) -> None:
    """Ensure the archive exists, is non-empty, openable, with no empty members."""
    if not os.path.exists(archive_path):
        raise RuntimeError(f"Archive missing: {archive_path}")
    if os.path.getsize(archive_path) == 0:
        raise RuntimeError("Archive is empty")
    if not tarfile.is_tarfile(archive_path):
        raise RuntimeError("Archive is not a valid tar.gz file")
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise RuntimeError("Archive contains no files")
        for member in members:
            if member.size == 0:
                raise RuntimeError(f"Empty dump inside archive: {member.name}")


async def create_backup(dest_dir: str | None = None) -> tuple:
    """Dump every project database and return (archive_path, databases).

    Raises on the first failure — a partial dump is never packaged. A
    temporary directory created here is removed on failure; when ``dest_dir``
    is supplied the caller owns cleanup.
    """
    databases = await discover_databases()
    if not databases:
        raise RuntimeError("No databases discovered to back up")

    own_dir = dest_dir is None
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="dbbackup_")
    try:
        sql_files = []
        for dbname in databases:
            path = await asyncio.to_thread(dump_database, dbname, dest_dir)
            sql_files.append(path)
        # Only after every dump succeeded do we package them.
        archive_path = os.path.join(dest_dir, backup_filename())
        build_archive(sql_files, archive_path)
        validate_archive(archive_path)
        return archive_path, databases
    except Exception:
        if own_dir:
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise


async def deliver_backup(bot, archive_path: str, databases: list | None = None) -> None:
    """Upload the archive to the configured Telegram channel. Raises on failure."""
    channel_id = settings.BACKUP_TELEGRAM_CHANNEL_ID
    if not channel_id:
        logger.warning("BACKUP_TELEGRAM_CHANNEL_ID not set; skipping delivery")
        return
    size = os.path.getsize(archive_path)
    if size > TELEGRAM_UPLOAD_LIMIT:
        raise RuntimeError(
            f"Archive is {size} bytes, exceeds Telegram's {TELEGRAM_UPLOAD_LIMIT}-byte limit"
        )
    name = os.path.basename(archive_path)
    from aiogram.types import FSInputFile
    document = FSInputFile(archive_path, filename=name)
    stamp = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    caption = (
        "✅ پشتیبان‌گیری روزانه با موفقیت انجام شد.\n"
        "─────────────────\n"
        f"📦 فایل: {name}\n"
        f"🗄 دیتابیس‌ها: {', '.join(sorted(databases or [])) or '—'}\n"
        f"📏 حجم: {size / 1024:.1f} KB\n"
        f"⏰ زمان (تهران): {stamp}"
    )
    await bot.send_document(channel_id, document=document, caption=caption)


async def notify_admins(bot, message: str) -> None:
    """Best-effort DM to every admin. Never raises."""
    if bot is None or not settings.ADMIN_IDS:
        return
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except Exception:
            logger.exception("Failed to notify admin %d", admin_id)


async def run_backup(bot=None, *, deliver: bool = True, notify: bool = True) -> bool:
    """Full cycle: dump -> archive -> validate -> deliver. Returns success.

    Never raises: failures are logged and reported to admins. Temporary
    files are always cleaned up.
    """
    async with _run_lock:
        logger.info("Backup started at %s", datetime.now(TEHRAN_TZ).isoformat())
        tmp_dir = tempfile.mkdtemp(prefix="dbbackup_")
        started = datetime.now(TEHRAN_TZ)
        try:
            archive_path, databases = await create_backup(dest_dir=tmp_dir)
            size = os.path.getsize(archive_path)
            duration = (datetime.now(TEHRAN_TZ) - started).total_seconds()
            logger.info(
                "Backup archive ready: %s (%d bytes) in %.1fs",
                os.path.basename(archive_path), size, duration,
            )
            if deliver:
                await deliver_backup(bot, archive_path, databases)
            logger.info("Backup completed in %.1fs (size=%d)", duration, size)
            return True
        except Exception as e:
            logger.exception("Backup failed")
            if notify:
                await notify_admins(bot, f"⚠️ خطا در پشتیبان‌گیری روزانه:\n{e}")
            return False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


async def _scheduled_job(bot) -> None:
    """Scheduler entry point guarded by a cross-process advisory lock."""
    from bot.db.engine import engine
    try:
        async with engine.connect() as conn:
            got = (
                await conn.execute(
                    text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}
                )
            ).scalar()
            if not got:
                logger.info("Another instance holds the backup lock; skipping run")
                return
            try:
                await run_backup(bot)
            finally:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY}
                )
    except Exception:
        logger.exception("Scheduled backup job crashed")


def start_scheduler(bot):
    """Start the daily 00:00 Asia/Tehran backup job. Returns the scheduler."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone=TEHRAN_TZ)
    scheduler.add_job(
        _scheduled_job,
        CronTrigger(hour=0, minute=0, timezone=TEHRAN_TZ),
        args=[bot],
        id="daily_db_backup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Daily DB backup scheduled at 00:00 Asia/Tehran")
    return scheduler


async def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run a database backup now.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="dump + archive + validate, but do not upload to Telegram",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    bot = None
    if not args.dry_run and settings.BACKUP_TELEGRAM_CHANNEL_ID:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    try:
        ok = await run_backup(bot, deliver=not args.dry_run)
    finally:
        if bot is not None:
            await bot.session.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli()))
