"""Daily database backup: naming, archive, validation, delivery, failure."""
import asyncio
import os
import re
import tarfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from bot.services import backup as backup_svc


TEHRAN = ZoneInfo("Asia/Tehran")
FILENAME_RE = re.compile(r"^Image_Generation_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.tar\.gz$")


# ---------- naming ----------

def test_backup_filename_format():
    name = backup_svc.backup_filename()
    assert FILENAME_RE.match(name)


def test_backup_filename_uses_tehran_time():
    dt = datetime(2026, 10, 18, 0, 0, 0, tzinfo=TEHRAN)
    assert backup_svc.backup_filename(dt) == "Image_Generation_2026-10-18_00-00-00.tar.gz"


# ---------- pg params ----------

def test_pg_params_parsed_from_url(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(
        settings, "DATABASE_URL",
        "postgresql+asyncpg://bot:secret@postgres:5432/imagebot",
    )
    p = backup_svc._pg_params()
    assert p == {"host": "postgres", "port": "5432", "user": "bot", "password": "secret"}


# ---------- dump ----------

def test_dump_database_nonzero_exit_raises(tmp_path, monkeypatch):
    class R:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(backup_svc.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="pg_dump failed for imagebot"):
        backup_svc.dump_database("imagebot", str(tmp_path))


def test_dump_database_empty_output_raises(tmp_path, monkeypatch):
    class R:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(backup_svc.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="empty output"):
        backup_svc.dump_database("imagebot", str(tmp_path))


# ---------- archive build + validate ----------

def test_build_and_validate_archive(tmp_path):
    (tmp_path / "imagebot.sql").write_text("CREATE TABLE t();\nCOPY t FROM stdin;\n1\n\\.\n")
    (tmp_path / "imagebot_bale.sql").write_text("SELECT 1;\n")
    archive = str(tmp_path / "Image_Generation_2026-10-18_00-00-00.tar.gz")
    backup_svc.build_archive(
        [str(tmp_path / "imagebot.sql"), str(tmp_path / "imagebot_bale.sql")], archive,
    )
    backup_svc.validate_archive(archive)
    with tarfile.open(archive, "r:gz") as tar:
        names = sorted(tar.getnames())
    assert names == ["imagebot.sql", "imagebot_bale.sql"]


def test_validate_missing_archive_raises(tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        backup_svc.validate_archive(str(tmp_path / "nope.tar.gz"))


def test_validate_empty_file_raises(tmp_path):
    p = tmp_path / "empty.tar.gz"
    p.write_bytes(b"")
    with pytest.raises(RuntimeError, match="empty"):
        backup_svc.validate_archive(str(p))


def test_validate_non_tar_raises(tmp_path):
    p = tmp_path / "bad.tar.gz"
    p.write_bytes(b"not a tarball")
    with pytest.raises(RuntimeError):
        backup_svc.validate_archive(str(p))


def test_validate_empty_member_raises(tmp_path):
    (tmp_path / "empty.sql").write_text("")
    archive = str(tmp_path / "a.tar.gz")
    backup_svc.build_archive([str(tmp_path / "empty.sql")], archive)
    with pytest.raises(RuntimeError, match="Empty dump inside archive"):
        backup_svc.validate_archive(archive)


# ---------- create_backup orchestration ----------

@pytest.mark.asyncio
async def test_create_backup_packages_all_databases(tmp_path, monkeypatch):
    async def fake_discover():
        return ["imagebot", "imagebot_bale"]

    def fake_dump(dbname, dest_dir):
        path = os.path.join(dest_dir, f"{dbname}.sql")
        with open(path, "w") as f:
            f.write(f"-- dump of {dbname}\n")
        return path

    monkeypatch.setattr(backup_svc, "discover_databases", fake_discover)
    monkeypatch.setattr(backup_svc, "dump_database", fake_dump)

    archive, dbs = await backup_svc.create_backup(dest_dir=str(tmp_path))
    assert dbs == ["imagebot", "imagebot_bale"]
    assert FILENAME_RE.match(os.path.basename(archive))
    with tarfile.open(archive, "r:gz") as tar:
        assert sorted(tar.getnames()) == ["imagebot.sql", "imagebot_bale.sql"]


@pytest.mark.asyncio
async def test_create_backup_aborts_on_dump_failure(tmp_path, monkeypatch):
    async def fake_discover():
        return ["imagebot", "imagebot_bale"]

    calls = []

    def fake_dump(dbname, dest_dir):
        calls.append(dbname)
        if dbname == "imagebot_bale":
            raise RuntimeError("dump exploded")
        path = os.path.join(dest_dir, f"{dbname}.sql")
        with open(path, "w") as f:
            f.write("partial")
        return path

    monkeypatch.setattr(backup_svc, "discover_databases", fake_discover)
    monkeypatch.setattr(backup_svc, "dump_database", fake_dump)

    with pytest.raises(RuntimeError, match="dump exploded"):
        await backup_svc.create_backup(dest_dir=str(tmp_path))
    # no archive was produced
    assert not any(n.startswith("Image_Generation_") for n in os.listdir(tmp_path))


@pytest.mark.asyncio
async def test_create_backup_no_databases_raises(monkeypatch):
    async def fake_discover():
        return []

    monkeypatch.setattr(backup_svc, "discover_databases", fake_discover)
    with pytest.raises(RuntimeError, match="No databases"):
        await backup_svc.create_backup()


# ---------- delivery ----------

@pytest.mark.asyncio
async def test_deliver_uploads_exact_filename(tmp_path, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHANNEL_ID", -100123)

    archive = tmp_path / "Image_Generation_2026-10-18_00-00-00.tar.gz"
    (tmp_path / "d.sql").write_text("SELECT 1;\n")
    backup_svc.build_archive([str(tmp_path / "d.sql")], str(archive))

    bot = MagicMock()
    bot.send_document = AsyncMock()
    await backup_svc.deliver_backup(bot, str(archive), ["imagebot"])

    args, kwargs = bot.send_document.call_args
    assert args[0] == -100123
    assert kwargs["document"].filename == archive.name
    assert archive.name in kwargs["caption"]
    assert "imagebot" in kwargs["caption"]


@pytest.mark.asyncio
async def test_deliver_skipped_without_channel(tmp_path, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHANNEL_ID", None)

    archive = tmp_path / "x.tar.gz"
    (tmp_path / "d.sql").write_text("SELECT 1;\n")
    backup_svc.build_archive([str(tmp_path / "d.sql")], str(archive))

    bot = MagicMock()
    bot.send_document = AsyncMock()
    await backup_svc.deliver_backup(bot, str(archive), ["imagebot"])
    bot.send_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_rejects_oversized_archive(tmp_path, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHANNEL_ID", -100123)
    monkeypatch.setattr(backup_svc, "TELEGRAM_UPLOAD_LIMIT", 10)

    archive = tmp_path / "big.tar.gz"
    archive.write_bytes(b"x" * 100)

    bot = MagicMock()
    bot.send_document = AsyncMock()
    with pytest.raises(RuntimeError, match="exceeds Telegram"):
        await backup_svc.deliver_backup(bot, str(archive), ["imagebot"])
    bot.send_document.assert_not_awaited()


# ---------- run_backup ----------

@pytest.mark.asyncio
async def test_run_backup_success(tmp_path, monkeypatch):
    archive = tmp_path / "Image_Generation_2026-10-18_00-00-00.tar.gz"
    (tmp_path / "d.sql").write_text("SELECT 1;\n")
    backup_svc.build_archive([str(tmp_path / "d.sql")], str(archive))

    async def fake_create(dest_dir=None):
        return str(archive), ["imagebot"]

    monkeypatch.setattr(backup_svc, "create_backup", fake_create)
    assert await backup_svc.run_backup(bot=None, deliver=False) is True


@pytest.mark.asyncio
async def test_run_backup_failure_notifies_admins(monkeypatch):
    from bot.config import settings

    async def boom(dest_dir=None):
        raise RuntimeError("no space left")

    monkeypatch.setattr(backup_svc, "create_backup", boom)
    monkeypatch.setattr(settings, "ADMIN_IDS", [111, 222])

    bot = MagicMock()
    bot.send_message = AsyncMock()
    ok = await backup_svc.run_backup(bot=bot, deliver=True)

    assert ok is False
    assert bot.send_message.await_count == 2
    assert "خطا" in bot.send_message.call_args.args[1]


@pytest.mark.asyncio
async def test_run_backup_never_raises(monkeypatch):
    async def boom(dest_dir=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(backup_svc, "create_backup", boom)
    # bot None + no admins -> must still return False, not raise
    assert await backup_svc.run_backup(bot=None, deliver=True) is False


@pytest.mark.asyncio
async def test_run_backup_notify_false_silences_admins(monkeypatch):
    from bot.config import settings

    async def boom(dest_dir=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(backup_svc, "create_backup", boom)
    monkeypatch.setattr(settings, "ADMIN_IDS", [111])
    bot = MagicMock()
    bot.send_message = AsyncMock()
    assert await backup_svc.run_backup(bot=bot, deliver=True, notify=False) is False
    bot.send_message.assert_not_awaited()


# ---------- reservation (manual overlap guard) ----------

def test_reservation_is_atomic():
    backup_svc.release_reservation()
    assert backup_svc.try_reserve_backup() is True
    assert backup_svc.try_reserve_backup() is False  # second click rejected
    assert backup_svc.backup_in_progress() is True
    backup_svc.release_reservation()
    assert backup_svc.backup_in_progress() is False
    assert backup_svc.try_reserve_backup() is True
    backup_svc.release_reservation()


# ---------- admin button handler ----------

def _admin_callback(user_id=7, chat_id=123):
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.message.chat.id = chat_id
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_backup_now_runs_and_reports_success(monkeypatch):
    from bot.config import settings
    from bot.handlers import admin as admin_h

    monkeypatch.setattr(settings, "ADMIN_IDS", [7])
    backup_svc.release_reservation()

    async def fake_run(bot=None, *, deliver=True, notify=True):
        assert notify is False  # handler reports the outcome itself
        return True

    monkeypatch.setattr(backup_svc, "run_backup", fake_run)

    cb = _admin_callback()
    await admin_h.backup_now(cb, session=None)
    await asyncio.sleep(0.05)

    cb.answer.assert_awaited_once_with(admin_h.texts.ADMIN_BACKUP_STARTED)
    cb.bot.send_message.assert_awaited_once()
    assert cb.bot.send_message.call_args.args[0] == 123
    assert admin_h.texts.ADMIN_BACKUP_DONE in cb.bot.send_message.call_args.args[1]
    assert backup_svc.backup_in_progress() is False


@pytest.mark.asyncio
async def test_backup_now_reports_failure(monkeypatch):
    from bot.config import settings
    from bot.handlers import admin as admin_h

    monkeypatch.setattr(settings, "ADMIN_IDS", [7])
    backup_svc.release_reservation()

    async def fake_run(bot=None, *, deliver=True, notify=True):
        return False

    monkeypatch.setattr(backup_svc, "run_backup", fake_run)

    cb = _admin_callback()
    await admin_h.backup_now(cb, session=None)
    await asyncio.sleep(0.05)

    assert admin_h.texts.ADMIN_BACKUP_FAILED in cb.bot.send_message.call_args.args[1]
    assert backup_svc.backup_in_progress() is False


@pytest.mark.asyncio
async def test_backup_now_rejects_when_busy(monkeypatch):
    from bot.config import settings
    from bot.handlers import admin as admin_h

    monkeypatch.setattr(settings, "ADMIN_IDS", [7])
    backup_svc.release_reservation()
    assert backup_svc.try_reserve_backup() is True
    try:
        cb = _admin_callback()
        await admin_h.backup_now(cb, session=None)
        args, kwargs = cb.answer.call_args
        assert args[0] == admin_h.texts.ADMIN_BACKUP_BUSY
        assert kwargs.get("show_alert") is True
        cb.bot.send_message.assert_not_awaited()
    finally:
        backup_svc.release_reservation()


@pytest.mark.asyncio
async def test_backup_now_denies_non_admin(monkeypatch):
    from bot.config import settings
    from bot.handlers import admin as admin_h

    monkeypatch.setattr(settings, "ADMIN_IDS", [7])
    backup_svc.release_reservation()

    cb = _admin_callback(user_id=999)
    await admin_h.backup_now(cb, session=None)
    args, kwargs = cb.answer.call_args
    assert "دسترسی" in args[0]
    assert kwargs.get("show_alert") is True
    assert backup_svc.backup_in_progress() is False


def test_admin_status_has_backup_button():
    from bot.keyboards.inline import admin_status
    data = [b.callback_data for row in admin_status(True).inline_keyboard for b in row]
    assert "backup_now" in data
    assert "toggle_bot" in data and "reset_daily" in data
