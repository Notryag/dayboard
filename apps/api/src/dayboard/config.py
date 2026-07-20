from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID
from typing import Literal

from pydantic import AliasChoices
from pydantic import Field
from pydantic import SecretStr
from pydantic import field_validator
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
    public_web_url: str = Field(
        default="http://localhost:3000",
        alias="DAYBOARD_PUBLIC_WEB_URL",
    )
    password_reset_ttl_seconds: int = Field(
        default=30 * 60,
        alias="DAYBOARD_PASSWORD_RESET_TTL_SECONDS",
        ge=300,
        le=24 * 60 * 60,
    )
    smtp_host: str | None = Field(default=None, alias="DAYBOARD_SMTP_HOST")
    smtp_port: int = Field(default=587, alias="DAYBOARD_SMTP_PORT", ge=1, le=65535)
    smtp_username: str | None = Field(default=None, alias="DAYBOARD_SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="DAYBOARD_SMTP_PASSWORD")
    smtp_security: Literal["starttls", "ssl", "plain"] = Field(
        default="starttls",
        alias="DAYBOARD_SMTP_SECURITY",
    )
    mail_from_address: str | None = Field(default=None, alias="DAYBOARD_MAIL_FROM_ADDRESS")
    mail_from_name: str = Field(default="Dayboard", alias="DAYBOARD_MAIL_FROM_NAME")
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
    cloudflare_account_id: str | None = Field(default=None, alias="CLOUDFLARE_ACCOUNT_ID")
    cloudflare_api_token: SecretStr | None = Field(
        default=None,
        alias="CLOUDFLARE_API_TOKEN",
    )
    cloudflare_asr_model: str = Field(
        default="@cf/openai/whisper-large-v3-turbo",
        alias="CLOUDFLARE_ASR_MODEL",
    )
    cloudflare_asr_base_url: str = Field(
        default="https://api.cloudflare.com/client/v4",
        alias="CLOUDFLARE_ASR_BASE_URL",
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
    agent_summarization_trigger_tokens: int = Field(
        default=1200,
        alias="DAYBOARD_SUMMARIZATION_TRIGGER_TOKENS",
        ge=256,
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
    northgate_metadata_enabled: bool = Field(
        default=False,
        alias="DAYBOARD_NORTHGATE_METADATA_ENABLED",
    )
    northgate_base_url: str | None = Field(default=None, alias="DAYBOARD_NORTHGATE_BASE_URL")
    northgate_application_key: SecretStr | None = Field(
        default=None,
        alias="DAYBOARD_NORTHGATE_APPLICATION_KEY",
    )
    northgate_canary_tenant_ids: str = Field(
        default="",
        alias="DAYBOARD_NORTHGATE_CANARY_TENANT_IDS",
    )
    rate_limit_enabled: bool = Field(default=True, alias="DAYBOARD_RATE_LIMIT_ENABLED")
    rate_limit_default: str = Field(default="120/minute", alias="DAYBOARD_RATE_LIMIT_DEFAULT")
    rate_limit_registration: str = Field(
        default="5/hour", alias="DAYBOARD_RATE_LIMIT_REGISTRATION"
    )
    rate_limit_login: str = Field(default="10/minute", alias="DAYBOARD_RATE_LIMIT_LOGIN")
    rate_limit_password_reset_request: str = Field(
        default="3/hour",
        alias="DAYBOARD_RATE_LIMIT_PASSWORD_RESET_REQUEST",
    )
    rate_limit_password_reset: str = Field(
        default="5/hour",
        alias="DAYBOARD_RATE_LIMIT_PASSWORD_RESET",
    )
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

    @field_validator("default_timezone")
    @classmethod
    def validate_default_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("DAYBOARD_DEFAULT_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @field_validator("public_web_url")
    @classmethod
    def validate_public_web_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("DAYBOARD_PUBLIC_WEB_URL must use http or https")
        return normalized

    @model_validator(mode="after")
    def require_secure_production_auth(self) -> "Settings":
        canary_ids = self.northgate_canary_tenants
        application_key = (
            self.northgate_application_key.get_secret_value()
            if self.northgate_application_key is not None
            else ""
        )
        if canary_ids and (not self.northgate_base_url or not application_key):
            raise ValueError(
                "Northgate canary tenants require DAYBOARD_NORTHGATE_BASE_URL and "
                "DAYBOARD_NORTHGATE_APPLICATION_KEY"
            )
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
    def northgate_canary_tenants(self) -> frozenset[UUID]:
        tenants: set[UUID] = set()
        for raw in self.northgate_canary_tenant_ids.split(","):
            value = raw.strip()
            if not value:
                continue
            try:
                tenants.add(UUID(value))
            except ValueError as exc:
                raise ValueError(
                    "DAYBOARD_NORTHGATE_CANARY_TENANT_IDS must contain UUIDs"
                ) from exc
        return frozenset(tenants)

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
    def password_reset_mail_enabled(self) -> bool:
        return bool(self.smtp_host and self.mail_from_address)

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
