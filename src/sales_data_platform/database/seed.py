"""Deterministic PostgreSQL reference-data execution."""

import logging
from pathlib import Path

import psycopg

from sales_data_platform.common.paths import SQL_SEED_DIR
from sales_data_platform.database.exceptions import (
    ReferenceDataConflictError,
    ReferenceDataExecutionError,
)

LOGGER = logging.getLogger(__name__)
SALES_CHANNELS_SEED_PATH = SQL_SEED_DIR / "sales_channels.sql"
EXPECTED_SALES_CHANNELS = (
    ("ECOMMERCE", "E-Commerce"),
    ("RETAIL", "Retail"),
)


def seed_sales_channels(
    connection: psycopg.Connection,
    seed_path: Path = SALES_CHANNELS_SEED_PATH,
) -> tuple[str, ...]:
    """Insert missing approved channels and reject conflicting expected rows."""
    expected = dict(EXPECTED_SALES_CHANNELS)
    codes = tuple(expected)

    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("LOCK TABLE sales_channels IN SHARE ROW EXCLUSIVE MODE")
                cursor.execute(
                    """
                    SELECT sales_channel_code, sales_channel_name
                    FROM sales_channels
                    WHERE sales_channel_code = ANY(%s)
                    ORDER BY sales_channel_code
                    """,
                    (list(codes),),
                )
                existing = dict(cursor.fetchall())
                conflicts = tuple(
                    code for code, name in existing.items() if name != expected[code]
                )
                if conflicts:
                    conflict_text = ", ".join(conflicts)
                    raise ReferenceDataConflictError(
                        f"Conflicting sales-channel reference data: {conflict_text}"
                    )

                missing = tuple(code for code in codes if code not in existing)
                if missing:
                    cursor.execute(seed_path.read_text(encoding="utf-8"))
    except ReferenceDataConflictError:
        raise
    except (OSError, psycopg.Error) as error:
        raise ReferenceDataExecutionError(
            "Unable to apply sales-channel reference data"
        ) from error

    LOGGER.info("Sales-channel reference data is current")
    return missing
