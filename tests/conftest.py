"""Shared test configuration."""

import pytest

CONFIG_ENVIRONMENT_VARIABLES = (
    "APPLICATION_ENV",
    "LOG_LEVEL",
    "LOG_TO_FILE",
    "LOG_DIRECTORY",
)


@pytest.fixture(autouse=True)
def isolate_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent configuration environment state from leaking between tests."""
    for variable in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
