"""Tests for centralized logging setup."""

import importlib
import logging
import logging.config
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from sales_data_platform.common.paths import CONFIG_DIR
from sales_data_platform.config.settings import Settings
from sales_data_platform.logging import configure_logging
from sales_data_platform.logging import setup as logging_setup


@pytest.fixture(autouse=True)
def reset_logging_handlers():
    """Close handlers installed by each test."""
    yield
    for logger in (logging.getLogger(), logging.getLogger("sales_data_platform")):
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()


def make_settings(
    log_directory: Path, *, level: str = "INFO", to_file: bool = False
) -> Settings:
    """Build isolated settings without reading the repository dotenv file."""
    return Settings(
        _env_file=None,
        LOG_LEVEL=level,
        LOG_TO_FILE=to_file,
        LOG_DIRECTORY=log_directory,
    )


def test_configuration_is_discovered_through_config_dir() -> None:
    assert logging_setup.LOGGING_CONFIG_PATH == CONFIG_DIR / "logging.yaml"


def test_import_has_no_logging_or_filesystem_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_handlers = tuple(logging.getLogger().handlers)

    def fail(*args, **kwargs) -> None:
        raise AssertionError("Import caused a side effect")

    monkeypatch.setattr(Path, "mkdir", fail)
    monkeypatch.setattr(logging.config, "dictConfig", fail)

    importlib.reload(logging_setup)

    assert tuple(logging.getLogger().handlers) == original_handlers


def test_console_only_logging_emits_info_and_suppresses_debug(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(tmp_path / "logs"))
    logger = logging.getLogger("sales_data_platform.test")

    logger.debug("hidden debug message")
    logger.info("visible info message")

    output = capsys.readouterr().err
    assert "hidden debug message" not in output
    assert "INFO | sales_data_platform.test | visible info message" in output
    assert not (tmp_path / "logs").exists()
    assert not any(
        isinstance(handler, RotatingFileHandler)
        for handler in logging.getLogger().handlers
    )


@pytest.mark.parametrize(
    ("level", "emitted", "suppressed"),
    [("DEBUG", "debug event", None), ("WARNING", "warning event", "info event")],
)
def test_representative_runtime_levels(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    level: str,
    emitted: str,
    suppressed: str | None,
) -> None:
    configure_logging(make_settings(tmp_path / "logs", level=level))
    logger = logging.getLogger("sales_data_platform.runtime")

    if level == "DEBUG":
        logger.debug(emitted)
    else:
        logger.info(suppressed)
        logger.warning(emitted)

    output = capsys.readouterr().err
    assert emitted in output
    if suppressed is not None:
        assert suppressed not in output


def test_file_logging_creates_directory_and_rotating_file(tmp_path: Path) -> None:
    log_directory = tmp_path / "nested" / "logs"
    configure_logging(make_settings(log_directory, to_file=True))
    logger = logging.getLogger("sales_data_platform.file")

    logger.info("persisted message")

    file_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    assert log_directory.is_dir()
    assert (log_directory / "sales_data_platform.log").is_file()
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    handler.flush()
    assert handler.maxBytes == 5242880
    assert handler.backupCount == 3
    assert handler.encoding == "utf-8"
    assert "persisted message" in (log_directory / "sales_data_platform.log").read_text(
        encoding="utf-8"
    )


def test_existing_log_directory_is_handled_safely(tmp_path: Path) -> None:
    log_directory = tmp_path / "existing"
    log_directory.mkdir()

    configure_logging(make_settings(log_directory, to_file=True))

    assert (log_directory / "sales_data_platform.log").is_file()


def test_repeated_initialization_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = make_settings(tmp_path / "logs", to_file=True)
    configure_logging(settings)
    first_count = len(logging.getLogger().handlers)

    configure_logging(settings)
    second_count = len(logging.getLogger().handlers)
    logging.getLogger("sales_data_platform.repeat").info("one message")

    output = capsys.readouterr().err
    assert first_count == second_count == 2
    assert output.count("one message") == 1


def test_package_logger_uses_centralized_hierarchy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(tmp_path / "logs"))

    logging.getLogger("sales_data_platform.component").warning("package warning")

    output = capsys.readouterr().err
    assert "WARNING | sales_data_platform.component | package warning" in output


def test_invalid_yaml_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_config = tmp_path / "logging.yaml"
    invalid_config.write_text("handlers: [invalid", encoding="utf-8")
    monkeypatch.setattr(logging_setup, "LOGGING_CONFIG_PATH", invalid_config)

    with pytest.raises(logging_setup.LoggingSetupError, match="Unable to load"):
        configure_logging(make_settings(tmp_path / "logs"))


def test_missing_required_structure_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_config = tmp_path / "logging.yaml"
    invalid_config.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setattr(logging_setup, "LOGGING_CONFIG_PATH", invalid_config)

    with pytest.raises(
        logging_setup.LoggingSetupError, match="disable_existing_loggers"
    ):
        configure_logging(make_settings(tmp_path / "logs"))


def test_invalid_file_handler_configuration_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_config = tmp_path / "logging.yaml"
    config_text = logging_setup.LOGGING_CONFIG_PATH.read_text(encoding="utf-8")
    invalid_config.write_text(
        config_text.replace("backupCount: 3", "backupCount: invalid"),
        encoding="utf-8",
    )
    monkeypatch.setattr(logging_setup, "LOGGING_CONFIG_PATH", invalid_config)

    with pytest.raises(logging_setup.LoggingSetupError, match="backupCount"):
        configure_logging(make_settings(tmp_path / "logs", to_file=True))


def test_missing_yaml_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging_setup, "LOGGING_CONFIG_PATH", tmp_path / "missing.yaml")

    with pytest.raises(logging_setup.LoggingSetupError, match="not found"):
        configure_logging(make_settings(tmp_path / "logs"))


def test_enabled_directory_creation_failure_is_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs) -> None:
        raise OSError("unavailable")

    log_directory = tmp_path / "unavailable"
    monkeypatch.setattr(Path, "mkdir", fail)

    with pytest.raises(
        logging_setup.LoggingSetupError, match="Unable to create log directory"
    ):
        configure_logging(make_settings(log_directory, to_file=True))


def test_setup_does_not_read_environment_or_dotenv_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = Path.open

    def fail_getenv(*args, **kwargs):
        raise AssertionError("Logging setup read the process environment")

    def guarded_open(path: Path, *args, **kwargs):
        if path.name == ".env":
            raise AssertionError("Logging setup read dotenv directly")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(Path, "open", guarded_open)

    configure_logging(make_settings(tmp_path / "logs"))


def test_setup_does_not_resolve_log_directory_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path / "logs", to_file=True)

    def fail_resolve(*args, **kwargs):
        raise AssertionError("Logging setup re-resolved the log directory")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    configure_logging(settings)


def test_logging_is_independent_of_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working_directory = tmp_path / "working"
    working_directory.mkdir()
    log_directory = tmp_path / "logs"
    monkeypatch.chdir(working_directory)

    configure_logging(make_settings(log_directory, to_file=True))
    logging.getLogger("sales_data_platform.cwd").info("cwd independent")

    assert (log_directory / "sales_data_platform.log").is_file()
