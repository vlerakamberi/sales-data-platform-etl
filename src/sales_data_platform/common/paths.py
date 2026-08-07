"""Canonical filesystem paths for the project."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
STAGING_DATA_DIR = DATA_DIR / "staging"
CURATED_DATA_DIR = DATA_DIR / "curated"
SAMPLE_DATA_DIR = DATA_DIR / "sample"
DOCS_DIR = PROJECT_ROOT / "docs"
LOGS_DIR = PROJECT_ROOT / "logs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SQL_DIR = PROJECT_ROOT / "sql"
SQL_DDL_DIR = SQL_DIR / "ddl"
SQL_SEED_DIR = SQL_DIR / "seed"
SQL_QUERIES_DIR = SQL_DIR / "queries"
SQL_MIGRATIONS_DIR = SQL_DIR / "migrations"
