"""PostgreSQL migration infrastructure."""

from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.migrations import apply_migrations

__all__ = ["apply_migrations", "connect_database"]
