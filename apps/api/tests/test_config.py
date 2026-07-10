from __future__ import annotations

from dayboard.config import Settings


def test_model_gateway_and_rate_limit_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_MODEL_NAME", "openai:gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("DAYBOARD_RATE_LIMIT_DEFAULT", "10/minute")
    monkeypatch.setenv("DAYBOARD_RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/9")
    monkeypatch.setenv("DAYBOARD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DAYBOARD_COMMAND_QUEUE_URL", "redis://localhost:6379/8")
    monkeypatch.setenv("DAYBOARD_COMMAND_QUEUE_NAME", "dayboard:test")

    settings = Settings()

    assert settings.agent_model_name == "openai:gpt-4.1-mini"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in repr(settings)
    assert settings.rate_limit_default == "10/minute"
    assert settings.effective_rate_limit_storage_url == "redis://localhost:6379/9"
    assert settings.log_level == "DEBUG"
    assert settings.effective_command_queue_url == "redis://localhost:6379/8"
    assert settings.command_queue_name == "dayboard:test"
