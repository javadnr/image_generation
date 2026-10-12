import json
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = ""
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
    FREE_USAGE_TOKEN: int = 1000
    PROFIT_PERCENTAGE: float = 0.0
    IMAGE_EDIT_COST_TOKENS: int = 4000
    BRONZE_MAX_TOKEN: int = 10000
    SILVER_MAX_TOKEN: int = 25000
    GOLD_MAX_TOKEN: int = 60000
    BOT_ENABLED: bool = True
    REPORT_CHANNEL_ID: int | None = None
    PROCESSED_REQUESTS_CHANNEL_ID: int | None = None
    REQUIRED_CHANNELS: dict[str, str] = {}
    MODELS: dict = {}
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

    @validator("PROCESSED_REQUESTS_CHANNEL_ID", pre=True)
    def parse_processed_channel(cls, v):
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

    @validator("MODELS", pre=True)
    def parse_models(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            return json.loads(v)
        return v or {}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
