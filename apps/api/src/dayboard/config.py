from __future__ import annotations

from functools import lru_cache
from uuid import UUID
from typing import Literal

from pydantic import AliasChoices
from pydantic import Field
from pydantic import SecretStr
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="local", alias="DAYBOARD_ENV")
    log_level: str = Field(default="INFO", alias="DAYBOARD_LOG_LEVEL")
    auth_mode: Literal["development", "password"] = Field(
        default="development", alias="DAYBOARD_AUTH_MODE"
    )
    auth_session_cookie_name: str = Field(
        default="dayboard_session", alias="DAYBOARD_AUTH_SESSION_COOKIE_NAME"
    )
    auth_session_ttl_seconds: int = Field(
        default=30 * 24 * 60 * 60,
        alias="DAYBOARD_AUTH_SESSION_TTL_SECONDS",
        ge=3600,
    )
    auth_cookie_secure: bool = Field(default=False, alias="DAYBOARD_AUTH_COOKIE_SECURE")
    database_url: str = Field(
        default="postgresql+asyncpg://dayboard:dayboard@localhost:5432/dayboard",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    command_queue_url: str | None = Field(default=None, alias="DAYBOARD_COMMAND_QUEUE_URL")
    command_queue_name: str = Field(
        default="dayboard:commands", alias="DAYBOARD_COMMAND_QUEUE_NAME"
    )
    stale_run_seconds: int = Field(default=600, alias="DAYBOARD_STALE_RUN_SECONDS", ge=60)
    queued_run_timeout_seconds: int = Field(
        default=1800,
        alias="DAYBOARD_QUEUED_RUN_TIMEOUT_SECONDS",
        ge=300,
    )
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
    asr_provider: str = Field(default="aliyun", alias="DAYBOARD_ASR_PROVIDER")
    asr_max_audio_seconds: int = Field(
        default=60,
        alias="DAYBOARD_ASR_MAX_AUDIO_SECONDS",
        ge=5,
        le=600,
    )
    asr_max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        alias="DAYBOARD_ASR_MAX_UPLOAD_BYTES",
        ge=1024,
    )
    volcengine_asr_app_id: str | None = Field(default=None, alias="VOLCENGINE_ASR_APP_ID")
    volcengine_asr_access_key: SecretStr | None = Field(
        default=None,
        alias="VOLCENGINE_ASR_ACCESS_KEY",
    )
    volcengine_asr_resource_id: str = Field(
        default="volc.bigasr.auc",
        alias="VOLCENGINE_ASR_RESOURCE_ID",
    )
    aliyun_asr_api_key: SecretStr | None = Field(default=None, alias="ALIYUN_ASR_API_KEY")
    aliyun_asr_model: str = Field(
        default="qwen3-asr-flash",
        alias="ALIYUN_ASR_MODEL",
    )
    aliyun_asr_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        alias="ALIYUN_ASR_BASE_URL",
    )
    agent_model_name: str = Field(default="openai:gpt-4o-mini", alias="APP_MODEL_NAME")
    agent_checkpointer_backend: Literal["memory", "sqlite", "postgres"] = Field(
        default="postgres",
        alias="DAYBOARD_CHECKPOINTER_BACKEND",
    )
    agent_checkpointer_database_url: str | None = Field(
        default=None,
        alias="DAYBOARD_CHECKPOINTER_DATABASE_URL",
    )
    agent_summarization_enabled: bool = Field(
        default=True,
        alias="DAYBOARD_SUMMARIZATION_ENABLED",
    )
    agent_summarization_model_name: str | None = Field(
        default=None,
        alias="DAYBOARD_SUMMARIZATION_MODEL_NAME",
    )
    agent_summarization_trigger_messages: int = Field(
        default=40,
        alias="DAYBOARD_SUMMARIZATION_TRIGGER_MESSAGES",
        ge=4,
    )
    agent_summarization_keep_messages: int = Field(
        default=12,
        alias="DAYBOARD_SUMMARIZATION_KEEP_MESSAGES",
        ge=2,
    )
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    rate_limit_enabled: bool = Field(default=True, alias="DAYBOARD_RATE_LIMIT_ENABLED")
    rate_limit_default: str = Field(default="120/minute", alias="DAYBOARD_RATE_LIMIT_DEFAULT")
    rate_limit_registration: str = Field(
        default="5/hour", alias="DAYBOARD_RATE_LIMIT_REGISTRATION"
    )
    rate_limit_login: str = Field(default="10/minute", alias="DAYBOARD_RATE_LIMIT_LOGIN")
    rate_limit_command: str = Field(default="20/minute", alias="DAYBOARD_RATE_LIMIT_COMMAND")
    rate_limit_voice: str = Field(default="10/minute", alias="DAYBOARD_RATE_LIMIT_VOICE")
    rate_limit_storage_url: str | None = Field(
        default=None, alias="DAYBOARD_RATE_LIMIT_STORAGE_URL"
    )
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

    @model_validator(mode="after")
    def require_secure_production_auth(self) -> "Settings":
        if self.environment.lower() != "production":
            return self
        if self.auth_mode != "password":
            raise ValueError("Production requires DAYBOARD_AUTH_MODE=password")
        if not self.auth_cookie_secure:
            raise ValueError(
                "Password auth in production requires DAYBOARD_AUTH_COOKIE_SECURE=true"
            )
        return self

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

    @property
    def effective_checkpointer_database_url(self) -> str | None:
        if self.agent_checkpointer_backend == "memory":
            return None
        if self.agent_checkpointer_database_url:
            return self.agent_checkpointer_database_url
        if self.agent_checkpointer_backend == "sqlite":
            raise ValueError("SQLite checkpointer requires DAYBOARD_CHECKPOINTER_DATABASE_URL")
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
