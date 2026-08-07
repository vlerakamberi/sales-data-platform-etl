"""Centralized logging configuration."""

import copy
import logging
import logging.config
from pathlib import Path
from typing import Any

import yaml

from sales_data_platform.common.paths import CONFIG_DIR
from sales_data_platform.config.settings import Settings

LOGGING_CONFIG_PATH = CONFIG_DIR / "logging.yaml"
LOG_FILENAME = "sales_data_platform.log"
ROTATING_HANDLER_NAME = "rotating_file"
CONSOLE_HANDLER_NAME = "console"


class LoggingSetupError(RuntimeError):
    """Raised when centralized logging cannot be configured safely."""


def _load_configuration(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open(encoding="utf-8") as config_file:
            configuration = yaml.safe_load(config_file)
    except FileNotFoundError as error:
        raise LoggingSetupError(
            f"Logging configuration file not found: {config_path}"
        ) from error
    except (OSError, yaml.YAMLError) as error:
        raise LoggingSetupError(
            f"Unable to load logging configuration: {config_path}"
        ) from error

    if not isinstance(configuration, dict):
        raise LoggingSetupError("Logging configuration must be a mapping")
    return configuration


def _require_mapping(configuration: dict[str, Any], key: str) -> dict[str, Any]:
    value = configuration.get(key)
    if not isinstance(value, dict):
        raise LoggingSetupError(f"Logging configuration requires '{key}' mapping")
    return value


def _validate_configuration(configuration: dict[str, Any]) -> None:
    if configuration.get("version") != 1:
        raise LoggingSetupError("Logging configuration requires version 1")
    if not isinstance(configuration.get("disable_existing_loggers"), bool):
        raise LoggingSetupError(
            "Logging configuration requires disable_existing_loggers policy"
        )

    formatters = _require_mapping(configuration, "formatters")
    handlers = _require_mapping(configuration, "handlers")
    loggers = _require_mapping(configuration, "loggers")
    root = _require_mapping(configuration, "root")

    if "standard" not in formatters:
        raise LoggingSetupError("Logging configuration requires standard formatter")
    if "sales_data_platform" not in loggers:
        raise LoggingSetupError("Logging configuration requires package logger")
    if root.get("handlers") != [CONSOLE_HANDLER_NAME]:
        raise LoggingSetupError("Root logger must define the console handler")

    console = handlers.get(CONSOLE_HANDLER_NAME)
    rotating_file = handlers.get(ROTATING_HANDLER_NAME)
    if not isinstance(console, dict):
        raise LoggingSetupError("Logging configuration requires console handler")
    if console.get("class") != "logging.StreamHandler":
        raise LoggingSetupError("Console handler configuration is invalid")
    if not isinstance(rotating_file, dict):
        raise LoggingSetupError("Logging configuration requires rotating-file handler")

    required_rotating_values = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": LOG_FILENAME,
        "maxBytes": 5242880,
        "backupCount": 3,
        "encoding": "utf-8",
    }
    for key, expected in required_rotating_values.items():
        if rotating_file.get(key) != expected:
            raise LoggingSetupError(
                f"Rotating-file handler has invalid '{key}' configuration"
            )


def _clear_configured_handlers() -> None:
    for logger in (logging.getLogger(), logging.getLogger("sales_data_platform")):
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()


def configure_logging(settings: Settings) -> None:
    """Configure centralized console and optional rotating-file logging."""
    configuration = copy.deepcopy(_load_configuration(LOGGING_CONFIG_PATH))
    _validate_configuration(configuration)

    handlers = configuration["handlers"]
    root = configuration["root"]
    package_logger = configuration["loggers"]["sales_data_platform"]

    root["level"] = settings.log_level
    handlers[CONSOLE_HANDLER_NAME]["level"] = settings.log_level
    package_logger["level"] = settings.log_level

    if settings.log_to_file:
        try:
            settings.log_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise LoggingSetupError(
                f"Unable to create log directory: {settings.log_directory}"
            ) from error

        handlers[ROTATING_HANDLER_NAME]["level"] = settings.log_level
        handlers[ROTATING_HANDLER_NAME]["filename"] = str(
            settings.log_directory / LOG_FILENAME
        )
        root["handlers"].append(ROTATING_HANDLER_NAME)
    else:
        del handlers[ROTATING_HANDLER_NAME]

    try:
        logging.config.dictConfig(configuration)
    except (ValueError, TypeError, AttributeError, ImportError) as error:
        _clear_configured_handlers()
        raise LoggingSetupError("Unable to apply logging configuration") from error
