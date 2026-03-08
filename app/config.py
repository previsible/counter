from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str = ""
    database_url: str = "sqlite:///calories.db"
    daily_calorie_target: int = 2000
    timezone: str = "Europe/London"


@lru_cache
def get_settings() -> Settings:
    return Settings()
