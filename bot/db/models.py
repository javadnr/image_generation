from datetime import date, datetime
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Date, DateTime, ForeignKey, Text, Index, text, JSON
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    tier = Column(String(20), default="free")
    daily_used = Column(Integer, default=0)
    total_used = Column(Integer, default=0)
    token_balance = Column(Integer, default=0)
    last_reset_date = Column(Date, default=date.today)
    is_generating = Column(Boolean, default=False)
    image_width = Column(Integer, default=1024)
    image_height = Column(Integer, default=1024)
    image_quality = Column(String(10), default="low")
    image_model = Column(String(50), default="gpt-image-2.5-flare")
    image_size = Column(String(10), default="square")
    pending_prompt = Column(Text, nullable=True)
    source = Column(String(64), nullable=True)
    optimize_prompt = Column(Boolean, default=False)
    premium_expire_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    images = relationship("GeneratedImage", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    events = relationship("UserEvent", back_populates="user", cascade="all, delete-orphan")


class UserEvent(Base):
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(40), nullable=False)
    event_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="events")

    __table_args__ = (
        Index("ix_user_events_type_created", "event_type", "created_at"),
        Index("ix_user_events_user", "user_id"),
    )


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(BigInteger)
    file_path = Column(String(500))
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="images")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")
    payment_authority = Column(String(255), nullable=True)
    payment_link = Column(String(512), nullable=True)
    payment_ref_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("uq_pending_tx_per_user_plan", "user_id", "plan",
              unique=True, postgresql_where=text("status = 'pending'")),
    )


class Discount(Base):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(20), nullable=False)  # plan name or "all"
    percent = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id = Column(Integer, primary_key=True, default=1)
    bot_enabled = Column(Boolean, default=True)
