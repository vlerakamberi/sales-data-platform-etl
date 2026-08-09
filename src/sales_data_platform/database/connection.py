"""PostgreSQL connection establishment from validated settings."""

import psycopg

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.exceptions import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
)


def connect_database(settings: Settings) -> psycopg.Connection:
    """Create an explicit infrastructure connection from complete DB settings."""
    if (
        settings.database_host is None
        or settings.database_port is None
        or settings.database_name is None
        or settings.database_username is None
        or settings.database_password is None
    ):
        raise DatabaseConfigurationError(
            "Complete database configuration is required for database operations"
        )

    try:
        return psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            dbname=settings.database_name,
            user=settings.database_username,
            password=settings.database_password.get_secret_value(),
            autocommit=True,
        )
    except psycopg.Error as error:
        raise DatabaseConnectionError(
            "Unable to establish PostgreSQL connection"
        ) from error
