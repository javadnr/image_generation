import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User, Transaction


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Strip postgresql-specific indexes before DDL (SQLite doesn't support postgresql_where)
    tx_table = Base.metadata.tables["transactions"]
    tx_table.indexes.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
def mock_zarinpal():
    with patch("bot.services.payment.get_zarinpal_client") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


async def _make_user(session, telegram_id=123456, tier="free"):
    user = User(telegram_id=telegram_id, tier=tier)
    session.add(user)
    await session.flush()
    return user


async def _make_pending_tx(session, user, plan, created_ago_minutes=0):
    tx = Transaction(
        id=f"tx-{plan}-{user.telegram_id}",
        user_id=user.id,
        plan=plan,
        amount=500000,
        status="pending",
        payment_authority="test-authority-123",
        created_at=datetime.utcnow() - timedelta(minutes=created_ago_minutes),
    )
    session.add(tx)
    await session.flush()
    return tx


async def _make_paid_tx(session, user, plan):
    tx = Transaction(
        id=f"tx-paid-{plan}-{user.telegram_id}",
        user_id=user.id,
        plan=plan,
        amount=500000,
        status="paid",
        payment_authority="test-authority-paid",
        payment_ref_id="ref-123",
        paid_at=datetime.utcnow(),
    )
    session.add(tx)
    await session.flush()
    return tx


# ─── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_previous_link_creates_new(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-new", "https://zarinpal.com/pg/StartPay/auth-new")
    user = await _make_user(db)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-new"
    assert result["remaining_minutes"] == 30
    assert result["transaction_id"] is not None
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_reuse_pending_link_5min(db, mock_zarinpal):
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=5)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://www.zarinpal.com/pg/StartPay/test-authority-123"
    assert result["remaining_minutes"] == 25
    mock_zarinpal.request_payment.assert_not_called()


@pytest.mark.asyncio
async def test_reuse_pending_link_15min(db, mock_zarinpal):
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=15)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["remaining_minutes"] == 15
    mock_zarinpal.request_payment.assert_not_called()


@pytest.mark.asyncio
async def test_expired_link_creates_new(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-replaced", "https://zarinpal.com/pg/StartPay/auth-replaced")
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=31)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-replaced"
    assert result["remaining_minutes"] == 30
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_paid_link_creates_new(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-new2", "https://zarinpal.com/pg/StartPay/auth-new2")
    user = await _make_user(db)
    tx = await _make_paid_tx(db, user, "bronze")
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-new2"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_status_creates_new(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-cancelled", "https://zarinpal.com/pg/StartPay/auth-cancelled")
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze")
    tx.status = "cancelled"
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-cancelled"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_bronze_link_not_reused_for_silver(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-silver", "https://zarinpal.com/pg/StartPay/auth-silver")
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=5)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "silver")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-silver"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_other_user_link_not_reused(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-other", "https://zarinpal.com/pg/StartPay/auth-other")
    user_a = await _make_user(db, telegram_id=111)
    user_b = await _make_user(db, telegram_id=222)
    tx = await _make_pending_tx(db, user_a, "bronze", created_ago_minutes=5)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user_b, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-other"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_exact_30min_boundary_treated_as_expired(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-boundary", "https://zarinpal.com/pg/StartPay/auth-boundary")
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=30)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-boundary"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_remaining_time_calculated_from_actual_timestamp(db, mock_zarinpal):
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "gold", created_ago_minutes=23)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "gold")

    assert result["remaining_minutes"] == 7


@pytest.mark.asyncio
async def test_paid_link_never_sent_as_reusable(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-new3", "https://zarinpal.com/pg/StartPay/auth-new3")
    user = await _make_user(db)
    paid_tx = await _make_paid_tx(db, user, "silver")
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "silver")

    assert result["payment_link"] != "https://www.zarinpal.com/pg/StartPay/test-authority-paid"
    assert result["payment_link"] == "https://zarinpal.com/pg/StartPay/auth-new3"
    mock_zarinpal.request_payment.assert_called_once()


@pytest.mark.asyncio
async def test_reuse_preserves_same_transaction_id(db, mock_zarinpal):
    user = await _make_user(db)
    tx = await _make_pending_tx(db, user, "bronze", created_ago_minutes=3)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "bronze")

    assert result["transaction_id"] == tx.id


@pytest.mark.asyncio
async def test_new_link_returns_correct_amount(db, mock_zarinpal):
    mock_zarinpal.request_payment.return_value = ("auth-amount", "https://zarinpal.com/pg/StartPay/auth-amount")
    user = await _make_user(db)
    await db.commit()

    from bot.services.payment import create_zarinpal_purchase
    result = await create_zarinpal_purchase(db, user, "silver")

    from bot.services.payment import PLAN_PRICES
    assert result["amount_toman"] == PLAN_PRICES["silver"]
