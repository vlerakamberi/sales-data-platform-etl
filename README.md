# Sales Data Platform ETL

This repository is the local data-engineering foundation for the Northstar
Retail Group portfolio. Northstar's intended platform must eventually move
retail sales data through governed ingestion, transformation, quality, and
delivery stages. This repository currently provides the application foundation
for that work; it does not yet implement the ETL pipeline itself.

## Portfolio role and status

This is Repository 1 in a four-repository portfolio. Its role is to establish
the upstream sales-data platform and, in later milestones, the local ETL
capabilities that will supply downstream portfolio repositories. Repository 2
is a future downstream evolution point, not functionality contained here. The
other repositories remain separate portfolio concerns.

**Current status:** Milestone 1 — Project Foundation is complete and validated.

The following capabilities are implemented:

- deterministic, centralized repository paths;
- validated settings with environment and dotenv precedence;
- centralized console and optional rotating-file logging;
- a thin `python -m sales_data_platform` bootstrap;
- side-effect-free package boundaries for future pipeline areas;
- unit and integration tests, coverage reporting, and Ruff checks.

PostgreSQL integration, ingestion, transformation, data quality,
orchestration, monitoring, Azure integration, and the complete ETL pipeline are
planned capabilities. They are not implemented.

## Architecture

The implemented dependency direction is deliberately small:

```text
Application Bootstrap (__main__)
        │
        ├───────────────┐
        ▼               ▼
Validated Settings   Logging Setup
        │             /       \
        ▼            ▼         ▼
   Common Paths   Settings   Common Paths
```

`common.paths` owns path semantics, `config.settings` owns runtime configuration,
and `logging.setup` owns logging behavior. The bootstrap composes those services
without reinterpreting them. See the
[architecture overview](docs/architecture/architecture-overview.md).

## Repository structure

```text
config/                     Declarative logging configuration
data/                       Local raw, staging, curated, and sample areas
docs/                       Architecture and development documentation
logs/                       Generated local log output (ignored except placeholder)
scripts/                    Later-milestone operational scripts
sql/                        Later-milestone SQL areas
src/sales_data_platform/    Python package and application foundation
tests/                      Unit, integration, and fixture areas
```

The detailed tracked/generated/placeholder distinctions are documented in the
[project structure guide](docs/project-structure.md).

## Implemented technology stack

- CPython `>=3.13,<3.14` (validated with CPython 3.13.14)
- Pydantic and pydantic-settings for validated configuration
- PyYAML and the Python standard-library `logging` package
- Pytest and pytest-cov
- Ruff linting and formatting
- setuptools with a `src` package layout

SQL and PostgreSQL directories express planned structure only; no database
runtime or dependency is implemented.

## Quick start

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m sales_data_platform
```

Upgrading pip is recommended but optional. Activation commands for other shells
are in the [setup guide](docs/development/setup-guide.md).

## Development commands

```text
python -m sales_data_platform
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

## Configuration and logging

The active settings are `APPLICATION_ENV`, `LOG_LEVEL`, `LOG_TO_FILE`, and
`LOG_DIRECTORY`. Precedence is process environment, then repository-root `.env`,
then safe defaults. See the
[configuration guide](docs/development/configuration-guide.md).

Logging is initialized only through `configure_logging(settings)`. Console
logging is always enabled after successful setup; rotating-file logging is
optional and uses the resolved setting supplied by the configuration layer. See
the [logging guide](docs/development/logging-guide.md).

## Testing and quality

Tests cover paths, settings, logging, imports, and application startup. Pytest
collects from `tests/` and pytest-cov reports coverage for
`src/sales_data_platform`. Ruff enforces the configured lint and format rules.
No minimum coverage threshold is currently configured.

## Documentation index

- [Architecture overview](docs/architecture/architecture-overview.md)
- [Project structure](docs/project-structure.md)
- [Setup guide](docs/development/setup-guide.md)
- [Development guide](docs/development/development-guide.md)
- [Configuration guide](docs/development/configuration-guide.md)
- [Logging guide](docs/development/logging-guide.md)
- [Changelog](CHANGELOG.md)

## Governance and evolution

Work follows the portfolio's frozen Development Workflow Standard and approved
commit plans. Architecture and scope are agreed before implementation; commits
remain reviewable, secrets and generated outputs stay out of Git, and existing
foundation services must be reused rather than duplicated.

Later Repository 1 milestones may add database and ETL capabilities. Repository
2 may then consume governed outputs through its separately approved scope. This
documentation is not the final Milestone 9 recruiter showcase and does not
claim planned capabilities as complete.
