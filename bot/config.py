import json
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    ADMIN_IDS: list[int] = []
    DB_PASSWORD: str = "changeme"
    DATABASE_URL: str = "postgresql+asyncpg://bot:changeme@postgres:5432/imagebot"
    API_SERVER: str = "telegram"
    FREE_MODEL: str = "gpt-image-1-mini"
    BRONZE_MODEL: str = "gpt-image-1-mini"
    SILVER_MODEL: str = "gpt-image-1-mini"
    GOLD_MODEL: str = "gpt-image-1-mini"
    FREE_QUEUE_SIZE: int = 3
    BRONZE_QUEUE_SIZE: int = 10
    SILVER_QUEUE_SIZE: int = 25
    GOLD_QUEUE_SIZE: int = 0
    FREE_LIMIT: int = 2
    BRONZE_LIMIT: int = 10
    SILVER_LIMIT: int = 25
    GOLD_LIMIT: int = 50
    BRONZE_MAX_LIMIT: int = 100
    SILVER_MAX_LIMIT: int = 300
    GOLD_MAX_LIMIT: int = 600
    BOT_ENABLED: bool = True
    BRONZE_PRICE: int = 500000
    SILVER_PRICE: int = 800000
    GOLD_PRICE: int = 1400000
    REPORT_CHANNEL_ID: int | None = None
    REQUIRED_CHANNELS: dict[str, str] = {}
    BADGE: str = "@kiteck_TM"
    ZARINPAL_API_URL: str = ""
    ZARINPAL_PROJECT_ID: int = 0
    BALE_PROVIDER_TOKEN: str = ""
    PREMIUM_DURATION_DAYS: int = 30
    PAYMENT_REPORT_CHANNEL_ID: int | None = None

    @validator("ADMIN_IDS", pre=True)
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v or []

    @validator("REPORT_CHANNEL_ID", pre=True)
    def parse_report_channel(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @validator("PAYMENT_REPORT_CHANNEL_ID", pre=True)
    def parse_payment_report_channel(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
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
