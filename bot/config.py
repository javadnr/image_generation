import json
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    ADMIN_IDS: list[int] = []
    DB_PASSWORD: str = "changeme"
    DATABASE_URL: str = "postgresql+asyncpg://bot:changeme@postgres:5432/imagebot"
    FREE_MODEL: str = "gpt-image-1-mini"
    BRONZE_MODEL: str = "gpt-image-1-mini"
    SILVER_MODEL: str = "gpt-image-1-mini"
    GOLD_MODEL: str = "gpt-image-1-mini"
    FREE_QUEUE_SIZE: int = 3
    BRONZE_QUEUE_SIZE: int = 10
    SILVER_QUEUE_SIZE: int = 25
    GOLD_QUEUE_SIZE: int = 0
    BOT_ENABLED: bool = True
    BRONZE_PRICE: int = 500000
    SILVER_PRICE: int = 800000
    GOLD_PRICE: int = 1400000
    REPORT_CHANNEL_ID: int | None = None
    REQUIRED_CHANNELS: dict[str, str] = {}

    @validator("ADMIN_IDS", pre=True)
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @validator("REQUIRED_CHANNELS", pre=True)
    def parse_channels(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
