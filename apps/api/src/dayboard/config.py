from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="local", alias="DAYBOARD_ENV")
    database_url: str = Field(
        default="postgresql+asyncpg://dayboard:dayboard@localhost:5432/dayboard",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    default_tenant_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        alias="DAYBOARD_DEFAULT_TENANT_ID",
    )
    default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000002"),
        alias="DAYBOARD_DEFAULT_USER_ID",
    )
    default_timezone: str = Field(default="Asia/Shanghai", alias="DAYBOARD_DEFAULT_TIMEZONE")
    default_locale: str = Field(default="zh-CN", alias="DAYBOARD_DEFAULT_LOCALE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
