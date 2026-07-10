from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic import AliasChoices
from pydantic import Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="local", alias="DAYBOARD_ENV")
    log_level: str = Field(default="INFO", alias="DAYBOARD_LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+asyncpg://dayboard:dayboard@localhost:5432/dayboard",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    command_queue_url: str | None = Field(default=None, alias="DAYBOARD_COMMAND_QUEUE_URL")
    command_queue_name: str = Field(default="dayboard:commands", alias="DAYBOARD_COMMAND_QUEUE_NAME")
    stale_run_seconds: int = Field(default=600, alias="DAYBOARD_STALE_RUN_SECONDS", ge=60)
    idempotency_retention_seconds: int = Field(
        default=604800,
        alias="DAYBOARD_IDEMPOTENCY_RETENTION_SECONDS",
        ge=3600,
    )
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
    agent_model_name: str = Field(default="openai:gpt-4o-mini", alias="APP_MODEL_NAME")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    rate_limit_enabled: bool = Field(default=True, alias="DAYBOARD_RATE_LIMIT_ENABLED")
    rate_limit_default: str = Field(default="120/minute", alias="DAYBOARD_RATE_LIMIT_DEFAULT")
    rate_limit_storage_url: str | None = Field(default=None, alias="DAYBOARD_RATE_LIMIT_STORAGE_URL")
    provider_budget_enabled: bool = Field(default=True, alias="DAYBOARD_PROVIDER_BUDGET_ENABLED")
    provider_budget_request_limit: str = Field(
        default="30/minute",
        alias="DAYBOARD_PROVIDER_BUDGET_REQUEST_LIMIT",
    )
    provider_budget_token_limit: str = Field(
        default="60000/day",
        alias="DAYBOARD_PROVIDER_BUDGET_TOKEN_LIMIT",
    )
    provider_budget_storage_url: str | None = Field(
        default=None,
        alias="DAYBOARD_PROVIDER_BUDGET_STORAGE_URL",
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias=AliasChoices("DAYBOARD_CORS_ORIGINS", "CORS_ORIGINS"),
    )

    @property
    def effective_rate_limit_storage_url(self) -> str:
        return self.rate_limit_storage_url or self.redis_url

    @property
    def effective_command_queue_url(self) -> str:
        return self.command_queue_url or self.redis_url

    @property
    def effective_provider_budget_storage_url(self) -> str:
        return self.provider_budget_storage_url or self.redis_url

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
