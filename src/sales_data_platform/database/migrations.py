"""Ordered SQL migration discovery, integrity validation, and execution."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sales_data_platform.common.paths import SQL_MIGRATIONS_DIR
from sales_data_platform.database.exceptions import (
    MigrationDiscoveryError,
    MigrationExecutionError,
    MigrationStateError,
)

if TYPE_CHECKING:
    import psycopg

LOGGER = logging.getLogger(__name__)
MIGRATION_NAME_PATTERN = re.compile(r"^V(?P<version>\d{3})__(?P<name>[a-z0-9_]+)\.sql$")
MIGRATION_TABLE = "schema_migrations"
EXPECTED_METADATA_COLUMNS = (
    ("version", "integer", "NO", None),
    ("filename", "character varying", "NO", 255),
    ("checksum", "character", "NO", 64),
    ("applied_at", "timestamp with time zone", "NO", None),
)
EXPECTED_METADATA_CHECKS = (
    ("ck_schema_migrations_checksum_sha256", "(checksum ~ '^[0-9a-f]{64}$'::text)"),
    ("ck_schema_migrations_version_positive", "(version > 0)"),
)


@dataclass(frozen=True, slots=True)
class Migration:
    """One authoritative versioned SQL migration artifact."""

    version: int
    name: str
    filename: str
    path: Path
    checksum: str

    def read_sql(self) -> str:
        """Read the exact UTF-8 SQL content to execute."""
        return self.path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One migration identity recorded in PostgreSQL."""

    version: int
    filename: str
    checksum: str


def calculate_checksum(path: Path) -> str:
    """Calculate SHA-256 over the migration artifact's exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_migration(path: Path) -> Migration:
    """Parse one migration using the approved VNNN naming convention."""
    match = MIGRATION_NAME_PATTERN.fullmatch(path.name)
    if match is None:
        raise MigrationDiscoveryError(f"Malformed migration filename: {path.name}")
    return Migration(
        version=int(match.group("version")),
        name=match.group("name"),
        filename=path.name,
        path=path,
        checksum=calculate_checksum(path),
    )


def discover_migrations(directory: Path = SQL_MIGRATIONS_DIR) -> tuple[Migration, ...]:
    """Discover, validate, and numerically order repository migrations."""
    if not directory.is_dir():
        raise MigrationDiscoveryError(f"Migration directory not found: {directory}")

    migrations = [parse_migration(path) for path in directory.glob("*.sql")]
    migrations.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in migrations]
    duplicates = sorted(
        {version for version in versions if versions.count(version) > 1}
    )
    if duplicates:
        duplicate_text = ", ".join(str(version) for version in duplicates)
        raise MigrationDiscoveryError(f"Duplicate migration versions: {duplicate_text}")
    if not migrations or migrations[0].version != 1:
        raise MigrationDiscoveryError(
            "Repository migration sequence must begin at V001"
        )
    return tuple(migrations)


def _metadata_table_exists(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('schema_migrations') IS NOT NULL")
        row = cursor.fetchone()
    return bool(row and row[0])


def _database_is_clean(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            )
            """
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def _validate_metadata_table(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'schema_migrations'
            ORDER BY ordinal_position
            """
        )
        columns = tuple(cursor.fetchall())
        cursor.execute(
            """
            SELECT
                constraint_type,
                string_agg(column_name, ',' ORDER BY ordinal_position)
            FROM information_schema.table_constraints
            JOIN information_schema.key_column_usage
              USING (constraint_catalog, constraint_schema, constraint_name)
            WHERE table_constraints.table_schema = current_schema()
              AND table_constraints.table_name = 'schema_migrations'
              AND table_constraints.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            GROUP BY table_constraints.constraint_type
            ORDER BY table_constraints.constraint_type
            """
        )
        keys = tuple(cursor.fetchall())
        cursor.execute(
            """
            SELECT
                check_constraint.conname,
                pg_get_expr(check_constraint.conbin, check_constraint.conrelid)
            FROM pg_catalog.pg_constraint AS check_constraint
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = check_constraint.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = current_schema()
              AND relation.relname = 'schema_migrations'
              AND check_constraint.contype = 'c'
              AND check_constraint.convalidated
            ORDER BY check_constraint.conname
            """
        )
        checks = tuple(cursor.fetchall())
    expected_keys = (("PRIMARY KEY", "version"), ("UNIQUE", "filename"))
    if (
        columns != EXPECTED_METADATA_COLUMNS
        or keys != expected_keys
        or checks != EXPECTED_METADATA_CHECKS
    ):
        raise MigrationStateError("Incompatible schema_migrations relation")


def _record_migration(connection: psycopg.Connection, migration: Migration) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO schema_migrations (version, filename, checksum, applied_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (migration.version, migration.filename, migration.checksum),
        )


def _bootstrap_v001(connection: psycopg.Connection, migration: Migration) -> None:
    if not _database_is_clean(connection):
        raise MigrationStateError(
            "Migration metadata is absent but the database is not clean"
        )
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(migration.read_sql())
            _validate_metadata_table(connection)
            _record_migration(connection, migration)
    except MigrationStateError:
        raise
    except Exception as error:
        raise MigrationExecutionError(
            f"Failed to apply migration {migration.filename}"
        ) from error
    LOGGER.info("Applied migration %s", migration.filename)


def inspect_migration_history(
    connection: psycopg.Connection,
) -> tuple[AppliedMigration, ...]:
    """Read migration identities in deterministic version order."""
    _validate_metadata_table(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT version, filename, checksum
            FROM schema_migrations
            ORDER BY version
            """
        )
        return tuple(AppliedMigration(*row) for row in cursor.fetchall())


def _validate_history(
    migrations: tuple[Migration, ...], history: tuple[AppliedMigration, ...]
) -> None:
    authoritative = {migration.version: migration for migration in migrations}
    for applied in history:
        migration = authoritative.get(applied.version)
        if migration is None:
            raise MigrationStateError(
                f"Unknown applied migration version: {applied.version}"
            )
        if applied.filename != migration.filename:
            raise MigrationStateError(
                f"Applied migration filename mismatch for V{applied.version:03d}"
            )
        if applied.checksum != migration.checksum:
            raise MigrationStateError(
                f"Applied migration checksum mismatch for {migration.filename}"
            )

    expected_prefix = tuple(
        migration.version for migration in migrations[: len(history)]
    )
    applied_versions = tuple(applied.version for applied in history)
    if applied_versions != expected_prefix:
        raise MigrationStateError("Non-contiguous or incompatible migration history")


def apply_migrations(
    connection: psycopg.Connection,
    migrations: tuple[Migration, ...] | None = None,
) -> tuple[Migration, ...]:
    """Validate database history and transactionally apply missing migrations."""
    authoritative = migrations if migrations is not None else discover_migrations()
    if not authoritative or authoritative[0].version != 1:
        raise MigrationDiscoveryError("Authoritative migrations must begin at V001")

    bootstrapped = not _metadata_table_exists(connection)
    if bootstrapped:
        _bootstrap_v001(connection, authoritative[0])

    history = inspect_migration_history(connection)
    _validate_history(authoritative, history)
    applied_versions = {applied.version for applied in history}
    newly_applied: list[Migration] = [authoritative[0]] if bootstrapped else []

    for migration in authoritative:
        if migration.version in applied_versions:
            continue
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(migration.read_sql())
                _record_migration(connection, migration)
        except Exception as error:
            raise MigrationExecutionError(
                f"Failed to apply migration {migration.filename}"
            ) from error
        newly_applied.append(migration)
        LOGGER.info("Applied migration %s", migration.filename)

    return tuple(newly_applied)
