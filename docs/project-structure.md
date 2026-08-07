# Project structure

This guide distinguishes source-controlled foundation content from generated,
ignored, and later-milestone areas.

| Area | Purpose | Current state |
| --- | --- | --- |
| `config/` | Declarative application configuration | `logging.yaml` is tracked and active. |
| `data/` | Raw, staging, curated, and sample data zones | Directories are tracked with placeholders; generated datasets are ignored. |
| `docs/` | Architecture and development guidance | Markdown documentation is tracked; diagram space is currently a placeholder. |
| `logs/` | Local application log output | The placeholder is tracked; generated `*.log` files are ignored. |
| `scripts/` | Operational or helper scripts | Placeholder only; no operational scripts are implemented. |
| `sql/` | DDL, seed, query, and migration organization | Placeholders only; no database implementation exists. |
| `src/` | Installable Python source | Path, settings, logging, bootstrap, and package boundaries are implemented. |
| `tests/` | Automated verification | Unit and integration tests cover the implemented foundation. |

## Source-controlled content

Source-controlled content includes Python source and tests, `pyproject.toml`,
`.env.example`, `config/logging.yaml`, documentation, and `.gitkeep` files that
preserve approved empty directories.

## Generated and ignored content

The local `.venv`, real `.env`, Python caches, coverage artifacts, generated log
files, and generated raw/staging/curated data are local outputs and must not be
committed. `.env.example` remains a safe tracked template.

## Implemented source areas

- `common/`: canonical path ownership.
- `config/`: validated application settings.
- `logging/`: centralized logging initialization.
- `__main__.py`: minimal application composition.

The `ingestion/`, `transformation/`, `quality/`, and `orchestration/` packages
are boundaries only. The `scripts/` and `sql/` trees and parts of `data/` and
`docs/` remain later-milestone placeholders.
