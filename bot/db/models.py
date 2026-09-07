from datetime import date, datetime
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    tier = Column(String(20), default="free")
    daily_used = Column(Integer, default=0)
    last_reset_date = Column(Date, default=date.today)
    is_generating = Column(Boolean, default=False)
    image_width = Column(Integer, default=1024)
    image_height = Column(Integer, default=1024)
    optimize_prompt = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    images = relationship("GeneratedImage", back_populates="user", cascade="all, delete-orphan")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(BigInteger)
    file_path = Column(String(500))
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="images")


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id = Column(Integer, primary_key=True, default=1)
    bot_enabled = Column(Boolean, default=True)
