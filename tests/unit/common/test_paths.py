"""Tests for centralized project path management."""

import importlib
from pathlib import Path

from sales_data_platform.common import paths


def test_project_root_matches_repository_root() -> None:
    expected_root = Path(__file__).resolve().parents[3]

    assert paths.PROJECT_ROOT == expected_root
    assert paths.PROJECT_ROOT.is_absolute()


def test_all_canonical_paths_are_path_instances() -> None:
    canonical_paths = (
        paths.PROJECT_ROOT,
        paths.CONFIG_DIR,
        paths.DATA_DIR,
        paths.RAW_DATA_DIR,
        paths.STAGING_DATA_DIR,
        paths.CURATED_DATA_DIR,
        paths.SAMPLE_DATA_DIR,
        paths.DOCS_DIR,
        paths.LOGS_DIR,
        paths.SCRIPTS_DIR,
        paths.SQL_DIR,
        paths.SQL_DDL_DIR,
        paths.SQL_SEED_DIR,
        paths.SQL_QUERIES_DIR,
        paths.SQL_MIGRATIONS_DIR,
    )

    assert all(isinstance(path, Path) for path in canonical_paths)


def test_canonical_paths_have_expected_portable_semantics() -> None:
    root = paths.PROJECT_ROOT
    expected_paths = {
        paths.CONFIG_DIR: root / "config",
        paths.DATA_DIR: root / "data",
        paths.RAW_DATA_DIR: root / "data" / "raw",
        paths.STAGING_DATA_DIR: root / "data" / "staging",
        paths.CURATED_DATA_DIR: root / "data" / "curated",
        paths.SAMPLE_DATA_DIR: root / "data" / "sample",
        paths.DOCS_DIR: root / "docs",
        paths.LOGS_DIR: root / "logs",
        paths.SCRIPTS_DIR: root / "scripts",
        paths.SQL_DIR: root / "sql",
        paths.SQL_DDL_DIR: root / "sql" / "ddl",
        paths.SQL_SEED_DIR: root / "sql" / "seed",
        paths.SQL_QUERIES_DIR: root / "sql" / "queries",
        paths.SQL_MIGRATIONS_DIR: root / "sql" / "migrations",
    }

    assert all(actual == expected for actual, expected in expected_paths.items())


def test_paths_are_independent_of_current_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    expected_root = paths.PROJECT_ROOT
    monkeypatch.chdir(tmp_path)

    reloaded_paths = importlib.reload(paths)

    assert reloaded_paths.PROJECT_ROOT == expected_root
    assert reloaded_paths.CONFIG_DIR == expected_root / "config"
    assert reloaded_paths.SQL_MIGRATIONS_DIR == expected_root / "sql" / "migrations"


def test_import_does_not_mutate_filesystem(monkeypatch) -> None:
    def fail_on_mutation(*args, **kwargs) -> None:
        raise AssertionError("Import attempted to mutate the filesystem")

    monkeypatch.setattr(Path, "mkdir", fail_on_mutation)
    monkeypatch.setattr(Path, "touch", fail_on_mutation)
    monkeypatch.setattr(Path, "write_text", fail_on_mutation)
    monkeypatch.setattr(Path, "write_bytes", fail_on_mutation)

    importlib.reload(paths)
