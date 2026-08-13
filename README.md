# Sales Data Platform ETL

This repository is the local data-engineering foundation for the Northstar
Retail Group portfolio. It now includes a governed local ingestion boundary
that turns approved source files into validated, provenance-aware batches for
later transformation and persistence; it does not yet implement the complete
ETL pipeline.

## Portfolio role and status

This is Repository 1 in a four-repository portfolio. Its role is to establish
the upstream sales-data platform and, in later milestones, the local ETL
capabilities that will supply downstream portfolio repositories. Repository 2
is a future downstream evolution point, not functionality contained here. The
other repositories remain separate portfolio concerns.

**Current status:** Milestone 3 — Data Ingestion Layer is complete and
validated. Milestone 4 — Data Transformation Layer is complete and validated.
Milestone 5 — Data Quality Framework is complete and validated. Milestone 6 —
Pipeline Orchestration is complete and validated. Milestone 7 — Testing is
complete and validated. Repository 1 remains in active development and is not
complete.

The following capabilities are implemented:

- deterministic, centralized repository paths;
- validated settings with environment and dotenv precedence;
- centralized console and optional rotating-file logging;
- a thin `python -m sales_data_platform` bootstrap;
- explicit PostgreSQL connection infrastructure using validated settings;
- SQL-first V001/V002/V003 migrations with ordered execution, provenance, and
  SHA-256 integrity validation;
- the approved nine-table relational schema and six explicit indexes;
- deterministic `ECOMMERCE` and `RETAIL` sales-channel reference data;
- read-only physical-schema and exact reference-data contract validation;
- guarded real-PostgreSQL tests using a dedicated `_test` database;
- immutable `v1` contracts for product-catalog, ecommerce-sales, and
  retail-sales CSV sources;
- deterministic discovery, SHA-256 source identity, strict parsing, atomic
  validation, provenance, replay semantics, and safe lifecycle logging;
- deterministic, versioned transformation from `ValidatedBatch` to canonical
  products and sales lines for all three governed `v1` contracts, with explicit
  record outcomes and continuous provenance;
- PostgreSQL-independent local transformation validation that preserves the
  separation between canonical business records and later persistence;
- deterministic coordination of ingestion, transformation, and Data Quality
  for the three governed `v1` contracts, with PostgreSQL-backed execution
  history and a safe manual/local invocation boundary;
- immutable derived pipeline and stage runtime metrics calculated only from
  authoritative persisted timestamps;
- side-effect-free package boundaries for future pipeline areas;
- unit and integration tests, coverage reporting, and Ruff checks.

Canonical business-data persistence, scheduling, quarantine, cloud ingestion,
and later Repository 1 capabilities remain planned.

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

`common.paths` owns path semantics, `config.settings` owns runtime
configuration, `logging.setup` owns logging behavior, and `database` contains
explicit connection, migration, seed, and PostgreSQL contract-validation
infrastructure. Normal application bootstrap remains database-free. See the
[architecture overview](docs/architecture/architecture-overview.md).

## Repository structure

```text
config/                     Declarative logging configuration
data/                       Local raw, staging, curated, and sample areas
docs/                       Architecture and development documentation
logs/                       Generated local log output (ignored except placeholder)
scripts/                    Later-milestone operational scripts
sql/                        Authoritative migrations, seed, and SQL areas
src/sales_data_platform/    Python package and application foundation
tests/                      Unit and guarded PostgreSQL integration tests
```

Local ingestion sources use the configured `INGESTION_SOURCE_ROOT` and the
layout `<source-family>/v<version>/<file>.csv`. Tracked end-to-end fixtures live
under `tests/fixtures/ingestion/data/raw/`; runtime data remains under the
configured source root (default `data/raw`).

The detailed tracked/generated/placeholder distinctions are documented in the
[project structure guide](docs/project-structure.md).

## Implemented technology stack

- CPython `>=3.13,<3.14` (validated with CPython 3.13.14)
- Pydantic and pydantic-settings for validated configuration
- PostgreSQL with Psycopg 3
- PyYAML and the Python standard-library `logging` package
- Pytest and pytest-cov
- Ruff linting and formatting
- setuptools with a `src` package layout

SQL migration and seed artifacts are authoritative. Python provides only the
supporting connection, execution, integrity, and validation boundaries; no ORM
or alternative schema model is used.

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

Run one local pipeline execution after configuring PostgreSQL and applying the
repository migrations through V004:

```powershell
python -m sales_data_platform.orchestration `
  --contract-id <northstar.product_catalog|northstar.ecommerce_sales|northstar.retail_sales> `
  --contract-version 1 `
  --source-path <path>
```

An optional predecessor correlation may be supplied with:

```powershell
--predecessor-execution-id <UUID>
```

The generic `python -m sales_data_platform` startup remains database-free. The
orchestration command provides manual/local invocation only: it does not apply
migrations or introduce automatic retry, resume, scheduling, or concurrency.

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
`LOG_DIRECTORY`. Database operations additionally use `DATABASE_HOST`,
`DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USERNAME`, and
`DATABASE_PASSWORD` as one complete optional group. Precedence is process
environment, then repository-root `.env`, then safe defaults. Normal startup
does not require database configuration. See the
[configuration guide](docs/development/configuration-guide.md).

Logging is initialized only through `configure_logging(settings)`. Console
logging is always enabled after successful setup; rotating-file logging is
optional and uses the resolved setting supplied by the configuration layer. See
the [logging guide](docs/development/logging-guide.md).

## Testing and quality

Tests cover the Milestone 1 foundation, Milestone 2 database contracts, the
Milestone 3 ingestion chain, and the locally implemented Milestone 4 boundary
from `ValidatedBatch` through canonical transformation outcomes. Synthetic
tracked fixtures prove all three contracts, stable identity and provenance,
deterministic replay, exact decimal derivation, ordered outcome accounting, and
non-disclosure of raw customer data in transformation logs. Core ingestion and
transformation tests are PostgreSQL-independent. PostgreSQL tests still require a
separately provisioned database whose configured name ends in `_test`; they
verify configured and connected names before allowlisted cleanup and never
create or drop databases.

Pytest collects from `tests/` and pytest-cov reports coverage for
`src/sales_data_platform`. Ruff enforces the configured lint and format rules.
No minimum coverage threshold is currently configured.

## Documentation index

- [Architecture overview](docs/architecture/architecture-overview.md)
- [Database design](docs/architecture/database-design.md)
- [Data ingestion architecture](docs/architecture/data-ingestion.md)
- [ADR-001: SQL-first versioned migrations](docs/adr/ADR-001-sql-first-versioned-migration-strategy.md)
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

Later Repository 1 milestones may add ETL capabilities. Repository 2 may then
consume governed outputs through its separately approved scope. This
documentation is not the final Milestone 9 recruiter showcase and does not
claim planned capabilities or Repository 1 itself as complete.
