from __future__ import annotations

from uuid import UUID

from dayboard.config import Settings
from pydantic import ValidationError
import pytest


def test_model_gateway_and_rate_limit_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_MODEL_NAME", "openai:gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("DAYBOARD_NORTHGATE_METADATA_ENABLED", "true")
    monkeypatch.setenv("DAYBOARD_NORTHGATE_BASE_URL", "http://northgate:8080/v1")
    monkeypatch.setenv("DAYBOARD_NORTHGATE_APPLICATION_KEY", "northgate-application-key")
    monkeypatch.setenv(
        "DAYBOARD_NORTHGATE_CANARY_TENANT_IDS",
        "00000000-0000-0000-0000-000000000001",
    )
    monkeypatch.setenv("DAYBOARD_RATE_LIMIT_DEFAULT", "10/minute")
    monkeypatch.setenv("DAYBOARD_RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/9")
    monkeypatch.setenv("DAYBOARD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DAYBOARD_COMMAND_QUEUE_URL", "redis://localhost:6379/8")
    monkeypatch.setenv("DAYBOARD_COMMAND_QUEUE_NAME", "dayboard:test")
    monkeypatch.setenv("DAYBOARD_STALE_RUN_SECONDS", "900")
    monkeypatch.setenv("DAYBOARD_QUEUED_RUN_TIMEOUT_SECONDS", "2400")
    monkeypatch.setenv("DAYBOARD_IDEMPOTENCY_RETENTION_SECONDS", "86400")
    monkeypatch.setenv("DAYBOARD_SUMMARIZATION_NORMAL_TRIGGER_TOKENS", "6000")
    monkeypatch.setenv("DAYBOARD_SUMMARIZATION_EMERGENCY_TRIGGER_TOKENS", "12000")
    monkeypatch.setenv("DAYBOARD_SUMMARIZATION_TARGET_TOKENS", "2000")
    monkeypatch.setenv("DAYBOARD_ASR_PROVIDER", "aliyun")
    monkeypatch.setenv("DAYBOARD_ASR_MAX_AUDIO_SECONDS", "90")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-1")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-secret")

    settings = Settings()

    assert settings.agent_model_name == "openai:gpt-4.1-mini"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "secret-value"
    assert settings.northgate_metadata_enabled is True
    assert settings.northgate_base_url == "http://northgate:8080/v1"
    assert settings.northgate_application_key is not None
    assert settings.northgate_application_key.get_secret_value() == "northgate-application-key"
    assert settings.northgate_canary_tenants == {
        UUID("00000000-0000-0000-0000-000000000001")
    }
    assert "northgate-application-key" not in repr(settings)
    assert "secret-value" not in repr(settings)
    assert settings.rate_limit_default == "10/minute"
    assert settings.effective_rate_limit_storage_url == "redis://localhost:6379/9"
    assert settings.log_level == "DEBUG"
    assert settings.effective_command_queue_url == "redis://localhost:6379/8"
    assert settings.command_queue_name == "dayboard:test"
    assert settings.stale_run_seconds == 900
    assert settings.queued_run_timeout_seconds == 2400
    assert settings.idempotency_retention_seconds == 86400
    assert settings.agent_summarization_normal_trigger_tokens == 6000
    assert settings.agent_summarization_emergency_trigger_tokens == 12000
    assert settings.agent_summarization_target_tokens == 2000
    assert settings.asr_provider == "aliyun"
    assert settings.asr_max_audio_seconds == 90
    assert settings.cloudflare_account_id == "account-1"
    assert settings.cloudflare_api_token is not None
    assert settings.cloudflare_api_token.get_secret_value() == "cloudflare-secret"
    assert "cloudflare-secret" not in repr(settings)


def test_password_auth_requires_secure_cookie_in_production() -> None:
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(DAYBOARD_ENV="production", DAYBOARD_AUTH_MODE="password")


def test_production_rejects_development_identity() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=password"):
        Settings(
            DAYBOARD_ENV="production",
            DAYBOARD_AUTH_MODE="development",
            DAYBOARD_AUTH_COOKIE_SECURE=True,
        )


def test_local_environment_allows_development_identity() -> None:
    settings = Settings(
        DAYBOARD_ENV="local",
        DAYBOARD_AUTH_MODE="development",
        DAYBOARD_AUTH_COOKIE_SECURE=False,
    )

    assert settings.auth_mode == "development"


def test_default_timezone_must_be_valid_iana_name() -> None:
    with pytest.raises(ValidationError, match="DEFAULT_TIMEZONE"):
        Settings(DAYBOARD_DEFAULT_TIMEZONE="Beijing")


def test_northgate_canary_requires_complete_connection() -> None:
    with pytest.raises(ValidationError, match="NORTHGATE_BASE_URL"):
        Settings(
            DAYBOARD_NORTHGATE_CANARY_TENANT_IDS=(
                "00000000-0000-0000-0000-000000000001"
            )
        )


def test_northgate_canary_rejects_invalid_tenant_id() -> None:
    with pytest.raises(ValidationError, match="must contain UUIDs"):
        Settings(DAYBOARD_NORTHGATE_CANARY_TENANT_IDS="not-a-uuid")
