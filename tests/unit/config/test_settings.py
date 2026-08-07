"""Tests for validated application settings."""

import importlib
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from sales_data_platform.common.paths import LOGS_DIR, PROJECT_ROOT
from sales_data_platform.config.settings import Settings


def test_safe_defaults_and_expected_types() -> None:
    settings = Settings(_env_file=None)

    assert settings.application_env == "development"
    assert settings.log_level == "INFO"
    assert settings.log_to_file is False
    assert settings.log_directory == LOGS_DIR
    assert isinstance(settings.application_env, str)
    assert isinstance(settings.log_level, str)
    assert isinstance(settings.log_to_file, bool)
    assert isinstance(settings.log_directory, Path)


def test_process_environment_overrides_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPLICATION_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("LOG_TO_FILE", "true")
    monkeypatch.setenv("LOG_DIRECTORY", "runtime-logs")

    settings = Settings(_env_file=None)

    assert settings.application_env == "production"
    assert settings.log_level == "ERROR"
    assert settings.log_to_file is True
    assert settings.log_directory == PROJECT_ROOT / "runtime-logs"


def test_dotenv_values_load(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APPLICATION_ENV=test\n"
        "LOG_LEVEL=WARNING\n"
        "LOG_TO_FILE=true\n"
        "LOG_DIRECTORY=dotenv-logs\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.application_env == "test"
    assert settings.log_level == "WARNING"
    assert settings.log_to_file is True
    assert settings.log_directory == PROJECT_ROOT / "dotenv-logs"


def test_process_environment_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APPLICATION_ENV=development\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPLICATION_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "CRITICAL")

    settings = Settings(_env_file=env_file)

    assert settings.application_env == "production"
    assert settings.log_level == "CRITICAL"


@pytest.mark.parametrize("value", ["development", "test", "production"])
def test_valid_application_environments_are_accepted(value: str) -> None:
    settings = Settings(_env_file=None, APPLICATION_ENV=value)

    assert settings.application_env == value


def test_invalid_application_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APPLICATION_ENV="staging")


@pytest.mark.parametrize(
    "value",
    ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
)
def test_valid_log_levels_are_accepted(value: str) -> None:
    settings = Settings(_env_file=None, LOG_LEVEL=value)

    assert settings.log_level == value


@pytest.mark.parametrize("value", ["debug", "WARN", "TRACE", "OFF"])
def test_invalid_log_levels_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, LOG_LEVEL=value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("1", True), ("false", False), ("0", False)],
)
def test_boolean_parsing(value: str, expected: bool) -> None:
    settings = Settings(_env_file=None, LOG_TO_FILE=value)

    assert settings.log_to_file is expected


def test_log_directory_defaults_to_centralized_logs_directory() -> None:
    settings = Settings(_env_file=None)

    assert settings.log_directory == LOGS_DIR


def test_relative_log_directory_resolves_against_project_root() -> None:
    settings = Settings(_env_file=None, LOG_DIRECTORY="var/logs")

    assert settings.log_directory == (PROJECT_ROOT / "var" / "logs").resolve()


def test_absolute_log_directory_remains_absolute(tmp_path: Path) -> None:
    absolute_directory = (tmp_path / "application-logs").resolve()

    settings = Settings(_env_file=None, LOG_DIRECTORY=absolute_directory)

    assert settings.log_directory == absolute_directory
    assert settings.log_directory.is_absolute()


def test_log_directory_is_independent_of_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=None, LOG_DIRECTORY="cwd-independent")

    assert settings.log_directory == PROJECT_ROOT / "cwd-independent"


def test_settings_loading_does_not_mutate_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_on_mutation(*args, **kwargs) -> None:
        raise AssertionError("Settings loading attempted to mutate the filesystem")

    monkeypatch.setattr(Path, "mkdir", fail_on_mutation)
    monkeypatch.setattr(Path, "touch", fail_on_mutation)
    monkeypatch.setattr(Path, "write_text", fail_on_mutation)
    monkeypatch.setattr(Path, "write_bytes", fail_on_mutation)

    Settings(_env_file=None)


def test_environment_state_does_not_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "LOG_LEVEL" not in os.environ

    with monkeypatch.context() as context:
        context.setenv("LOG_LEVEL", "ERROR")
        assert Settings(_env_file=None).log_level == "ERROR"

    assert "LOG_LEVEL" not in os.environ
    assert Settings(_env_file=None).log_level == "INFO"


def test_config_package_and_settings_module_import() -> None:
    config_package = importlib.import_module("sales_data_platform.config")
    settings_module = importlib.import_module("sales_data_platform.config.settings")

    assert config_package.__name__ == "sales_data_platform.config"
    assert settings_module.Settings is Settings
