import pytest
from docket.config import Settings, get_settings
from pydantic import ValidationError


def test_defaults() -> None:
    # _env_file=None so a developer's local .env can't mask the code defaults.
    settings = Settings(_env_file=None)
    assert settings.app_name == "docket"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.log_level == "INFO"
    assert settings.max_attempts == 3
    assert settings.lease_timeout == 30.0


def test_invalid_max_attempts_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_MAX_ATTEMPTS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_lease_timeout_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_LEASE_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKET_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("DOCKET_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite://"
    assert settings.log_level == "DEBUG"


def test_log_level_is_normalized_to_upper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"


def test_invalid_log_level_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_LOG_LEVEL", "TRACE")
    with pytest.raises(ValidationError):
        Settings()


def test_empty_database_url_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_DATABASE_URL", "")
    with pytest.raises(ValidationError):
        Settings()


def test_empty_app_name_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKET_APP_NAME", "")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
