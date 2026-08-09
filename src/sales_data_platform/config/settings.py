"""Validated application settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sales_data_platform.common.paths import LOGS_DIR, PROJECT_ROOT, RAW_DATA_DIR


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
    ingestion_source_root: Path = Field(
        default=RAW_DATA_DIR,
        validation_alias="INGESTION_SOURCE_ROOT",
    )
    database_host: str | None = Field(
        default=None,
        min_length=1,
        validation_alias="DATABASE_HOST",
    )
    database_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        validation_alias="DATABASE_PORT",
    )
    database_name: str | None = Field(
        default=None,
        min_length=1,
        validation_alias="DATABASE_NAME",
    )
    database_username: str | None = Field(
        default=None,
        min_length=1,
        validation_alias="DATABASE_USERNAME",
    )
    database_password: SecretStr | None = Field(
        default=None,
        min_length=1,
        validation_alias="DATABASE_PASSWORD",
    )

    @model_validator(mode="after")
    def validate_database_configuration(self) -> "Settings":
        """Require database settings as one complete optional group."""
        database_values = (
            self.database_host,
            self.database_port,
            self.database_name,
            self.database_username,
            self.database_password,
        )
        configured_count = sum(value is not None for value in database_values)
        if configured_count not in (0, len(database_values)):
            raise ValueError(
                "Database configuration must be either fully provided or fully absent"
            )
        return self

    @field_validator("log_directory", "ingestion_source_root", mode="after")
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        """Resolve relative configured paths from the repository root."""
        if value.is_absolute():
            return value.resolve()
        return (PROJECT_ROOT / value).resolve()
