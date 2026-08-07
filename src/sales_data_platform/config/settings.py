"""Validated application settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sales_data_platform.common.paths import LOGS_DIR, PROJECT_ROOT


class Settings(BaseSettings):
    """Application settings loaded from environment variables and dotenv."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    application_env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias="APPLICATION_ENV",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_directory: Path = Field(
        default=LOGS_DIR,
        validation_alias="LOG_DIRECTORY",
    )

    @field_validator("log_directory", mode="after")
    @classmethod
    def resolve_log_directory(cls, value: Path) -> Path:
        """Resolve relative log directories from the repository root."""
        if value.is_absolute():
            return value.resolve()
        return (PROJECT_ROOT / value).resolve()
