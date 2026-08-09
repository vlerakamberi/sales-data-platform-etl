"""Shared test configuration."""

import os

import pytest

CONFIG_ENVIRONMENT_VARIABLES = (
    "APPLICATION_ENV",
    "LOG_LEVEL",
    "LOG_TO_FILE",
    "LOG_DIRECTORY",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
)


@pytest.fixture(autouse=True)
def isolate_configuration_environment(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Prevent configuration environment state from leaking between tests."""
    database_environment = {
        variable: os.environ.get(variable)
        for variable in CONFIG_ENVIRONMENT_VARIABLES
        if variable.startswith("DATABASE_")
    }
    for variable in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    if request.node.get_closest_marker("postgresql") is not None:
        for variable, value in database_environment.items():
            if value is not None:
                monkeypatch.setenv(variable, value)
