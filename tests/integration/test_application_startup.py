"""Integration tests for the application bootstrap."""

import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from sales_data_platform.common.paths import PROJECT_ROOT
from sales_data_platform.config.settings import Settings
from sales_data_platform.logging.setup import LoggingSetupError


@pytest.fixture(autouse=True)
def reset_logging_handlers():
    """Close logging handlers installed during each startup test."""
    yield
    for logger in (logging.getLogger(), logging.getLogger("sales_data_platform")):
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()


def isolated_settings(log_directory: Path, *, to_file: bool = False) -> Settings:
    """Create settings without consulting the repository dotenv file."""
    return Settings(
        _env_file=None,
        LOG_TO_FILE=to_file,
        LOG_DIRECTORY=log_directory,
    )


@pytest.mark.parametrize(
    "package_name",
    [
        "sales_data_platform.ingestion",
        "sales_data_platform.transformation",
        "sales_data_platform.quality",
        "sales_data_platform.orchestration",
    ],
)
def test_package_boundaries_import_without_operational_side_effects(
    package_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handlers_before = tuple(logging.getLogger().handlers)

    def fail(*args, **kwargs) -> None:
        raise AssertionError("Package import caused an operational side effect")

    monkeypatch.setattr(Path, "mkdir", fail)
    monkeypatch.setattr(logging, "basicConfig", fail)
    sys.modules.pop(package_name, None)

    package = importlib.import_module(package_name)

    assert package.__name__ == package_name
    assert tuple(logging.getLogger().handlers) == handlers_before
    assert not any(tmp_path.iterdir())


def test_importing_main_module_does_not_execute_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sales_data_platform.logging as centralized_logging

    original_configure_logging = centralized_logging.configure_logging

    def fail(*args, **kwargs) -> None:
        raise AssertionError("Import executed application startup")

    monkeypatch.setattr(centralized_logging, "configure_logging", fail)
    sys.modules.pop("sales_data_platform.__main__", None)

    module = importlib.import_module("sales_data_platform.__main__")

    assert callable(module.main)
    module.configure_logging = original_configure_logging


def test_direct_main_succeeds_and_logs_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sales_data_platform import __main__ as application

    log_directory = tmp_path / "disabled-logs"
    monkeypatch.setattr(
        application, "Settings", lambda: isolated_settings(log_directory)
    )

    result = application.main()

    output = capsys.readouterr().err
    assert result == 0
    assert (
        "INFO | sales_data_platform.__main__ | Application started successfully"
        in output
    )
    assert not log_directory.exists()
    assert not (log_directory / "sales_data_platform.log").exists()


def test_bootstrap_uses_centralized_configuration_and_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sales_data_platform import __main__ as application

    settings = isolated_settings(tmp_path / "logs")
    calls: list[object] = []

    def load_settings() -> Settings:
        calls.append("settings")
        return settings

    def configure(received_settings: Settings) -> None:
        calls.append(received_settings)

    monkeypatch.setattr(application, "Settings", load_settings)
    monkeypatch.setattr(application, "configure_logging", configure)

    assert application.main() == 0
    assert calls == ["settings", settings]


def test_file_enabled_startup_uses_isolated_log_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sales_data_platform import __main__ as application

    log_directory = tmp_path / "application-logs"
    monkeypatch.setattr(
        application,
        "Settings",
        lambda: isolated_settings(log_directory, to_file=True),
    )

    assert application.main() == 0
    log_file = log_directory / "sales_data_platform.log"
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_file.is_file()
    assert "Application started successfully" in log_file.read_text(encoding="utf-8")


def test_startup_is_independent_of_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sales_data_platform import __main__ as application

    working_directory = tmp_path / "working"
    working_directory.mkdir()
    log_directory = tmp_path / "logs"
    monkeypatch.chdir(working_directory)
    monkeypatch.setattr(
        application, "Settings", lambda: isolated_settings(log_directory)
    )

    assert application.main() == 0
    assert Path.cwd() == working_directory
    assert not log_directory.exists()


def test_python_module_execution_succeeds_from_repository_environment() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    environment["LOG_TO_FILE"] = "false"

    result = subprocess.run(
        [sys.executable, "-m", "sales_data_platform"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Application started successfully" in result.stderr


def test_invalid_configuration_prevents_successful_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sales_data_platform import __main__ as application

    monkeypatch.setenv("APPLICATION_ENV", "invalid")

    with pytest.raises(ValidationError):
        application.main()


def test_logging_failure_prevents_successful_startup_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sales_data_platform import __main__ as application

    monkeypatch.setattr(
        application, "Settings", lambda: isolated_settings(tmp_path / "logs")
    )

    def fail_logging(settings: Settings) -> None:
        raise LoggingSetupError("logging unavailable")

    def fail_basic_config(*args, **kwargs) -> None:
        raise AssertionError("Unexpected basicConfig fallback")

    monkeypatch.setattr(application, "configure_logging", fail_logging)
    monkeypatch.setattr(logging, "basicConfig", fail_basic_config)

    with pytest.raises(LoggingSetupError, match="logging unavailable"):
        application.main()


def test_future_packages_are_not_executed_during_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sales_data_platform import __main__ as application

    future_packages = (
        "sales_data_platform.ingestion",
        "sales_data_platform.transformation",
        "sales_data_platform.quality",
        "sales_data_platform.orchestration",
    )
    for package_name in future_packages:
        sys.modules.pop(package_name, None)
    monkeypatch.setattr(
        application, "Settings", lambda: isolated_settings(tmp_path / "logs")
    )

    assert application.main() == 0
    assert all(package_name not in sys.modules for package_name in future_packages)


def test_repeated_startup_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sales_data_platform import __main__ as application

    monkeypatch.setattr(
        application, "Settings", lambda: isolated_settings(tmp_path / "logs")
    )

    assert application.main() == 0
    first_handler_count = len(logging.getLogger().handlers)
    assert application.main() == 0
    second_handler_count = len(logging.getLogger().handlers)

    output = capsys.readouterr().err
    assert first_handler_count == second_handler_count == 1
    assert output.count("Application started successfully") == 2
