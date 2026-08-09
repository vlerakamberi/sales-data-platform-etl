"""Tests for deterministic SQL migration discovery."""

import hashlib
from pathlib import Path

import pytest

from sales_data_platform.common.paths import SQL_MIGRATIONS_DIR
from sales_data_platform.database.exceptions import MigrationDiscoveryError
from sales_data_platform.database.migrations import (
    calculate_checksum,
    discover_migrations,
    parse_migration,
)


def write_migration(
    directory: Path, filename: str, content: bytes = b"SELECT 1;\n"
) -> Path:
    """Create a migration artifact for discovery tests."""
    path = directory / filename
    path.write_bytes(content)
    return path


def test_valid_migration_filename_is_parsed(tmp_path: Path) -> None:
    path = write_migration(tmp_path, "V012__add_example_table.sql")

    migration = parse_migration(path)

    assert migration.version == 12
    assert migration.name == "add_example_table"
    assert migration.filename == path.name
    assert migration.path == path


@pytest.mark.parametrize(
    "filename",
    [
        "001__missing_prefix.sql",
        "V01__short_version.sql",
        "V0001__long_version.sql",
        "V001_missing_separator.sql",
        "V001__Uppercase.sql",
        "V001__.sql",
        "V001__valid.txt",
    ],
)
def test_malformed_migration_names_are_rejected(tmp_path: Path, filename: str) -> None:
    path = write_migration(tmp_path, filename)

    with pytest.raises(MigrationDiscoveryError, match="Malformed migration filename"):
        parse_migration(path)


def test_migrations_are_sorted_by_numeric_version(tmp_path: Path) -> None:
    write_migration(tmp_path, "V003__third.sql")
    write_migration(tmp_path, "V001__first.sql")
    write_migration(tmp_path, "V002__second.sql")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2, 3]


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    write_migration(tmp_path, "V001__first.sql")
    write_migration(tmp_path, "V001__duplicate.sql")

    with pytest.raises(
        MigrationDiscoveryError, match="Duplicate migration versions: 1"
    ):
        discover_migrations(tmp_path)


def test_checksum_uses_exact_file_bytes(tmp_path: Path) -> None:
    content = b"SELECT '\r\n';\r\n"
    path = write_migration(tmp_path, "V001__checksum.sql", content)

    assert calculate_checksum(path) == hashlib.sha256(content).hexdigest()


def test_authoritative_migrations_use_centralized_path() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [1, 2, 3]
    assert all(migration.path.parent == SQL_MIGRATIONS_DIR for migration in migrations)
