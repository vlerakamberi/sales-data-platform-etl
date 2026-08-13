# Sales Data Platform ETL

Northstar Retail operates across ecommerce and physical retail channels. This
repository addresses the local data-engineering problem behind that scenario:
turning governed product and sales CSV sources into validated, traceable
canonical data while making execution state and failures operationally visible.

`sales-data-platform-etl` is a professionally engineered local ETL platform and
the first stage of a four-repository, enterprise-oriented data engineering
portfolio. It demonstrates explicit contracts, deterministic processing,
SQL-first PostgreSQL engineering, governed Data Quality, application-native
orchestration, durable operational history, and layered automated validation.

> **Status:** Milestones 1–7 are complete and validated. Milestone 8 is in
> progress. Repository 1 remains **NOT COMPLETE**.

## Portfolio position

The portfolio evolves the same engineering problem through four bounded stages:

1. **Repository 1 — Local ETL foundation:** governed ingestion,
   transformation, Data Quality, PostgreSQL, orchestration, testing, and local
   operational readiness.
2. **Repository 2 — Azure/cloud evolution:** a separate future repository for
   cloud platform engineering.
3. **Repository 3 — Big-data evolution:** a separate future repository for
   distributed and large-scale processing concerns.
4. **Repository 4 — Warehouse/analytics evolution:** a separate future
   repository for analytical serving and warehouse concerns.

Repositories 2–4 are portfolio direction, not capabilities implemented here.
Repository 1 establishes the local contracts and evidence from which the later
Azure data engineering progression can evolve.

## What is implemented

### Architecture and data flow

```text
Governed CSV sources
→ deterministic ingestion and provenance
→ versioned canonical transformation
→ governed Data Quality evaluation
→ application-native pipeline control
→ durable PostgreSQL execution evidence
```

The assembled pipeline runs ingestion, transformation, and Data Quality
sequentially. PostgreSQL persists the approved relational foundation and
authoritative pipeline/stage history. Canonical business-output persistence is
not yet part of the assembled orchestration path. See the
[architecture overview](docs/architecture/architecture-overview.md) and
[database design](docs/architecture/database-design.md).

### PostgreSQL and persistence

- SQL-first ordered migrations V001–V004 with SHA-256 integrity and migration
  history validation.
- An approved relational schema, explicit indexes, reference data, and physical
  contract validation without an ORM-owned schema model.
- Durable pipeline and stage execution history, timestamps, terminal state,
  partial progress, and bounded failure classification.

### Governed ingestion

Immutable `v1` contracts cover product catalog, ecommerce sales, and retail
sales CSV sources. Discovery, strict parsing, atomic validation, SHA-256 source
identity, distinct run identity, provenance, and deterministic replay are
explicit contracts. See the
[ingestion architecture](docs/architecture/data-ingestion.md).

### Canonical transformation

Versioned rules map validated source batches into immutable canonical products
and sales lines with ordered outcomes, exact decimal behavior, and continuous
provenance. The transformation core remains independent of PostgreSQL. See the
[transformation architecture](docs/architecture/data-transformation.md).

### Governed Data Quality

Versioned expectations produce structured `SATISFIED`, `VIOLATED`,
`NOT_APPLICABLE`, and `EVALUATION_ERROR` outcomes. A governed blocking violation
completes Data Quality technically but makes the pipeline `BLOCKED`; it is not a
technical failure. See the
[Data Quality architecture](docs/architecture/data-quality.md).

### Pipeline orchestration

The local application coordinates the three fixed stages and returns one of
`SUCCEEDED`, `BLOCKED`, or `FAILED`. Each attempt receives a new pipeline
execution identity and separate durable history. Optional predecessor
correlation does not imply retry or resume. See the
[orchestration architecture](docs/architecture/pipeline-orchestration.md).

### Observability

Centralized console and optional rotating-file logging supports diagnosis.
PostgreSQL history remains authoritative for pipeline/stage lifecycle,
partial-progress visibility, timestamps, and controlled failure metadata.
Operator output is deliberately bounded and privacy-safe; runtime metrics are
derived from persisted timestamps. No external monitoring platform is claimed.

## Operational readiness

The [operational runbook](docs/operations/runbook.md) is the canonical guide for
prerequisites, installation, configuration, PostgreSQL initialization, pipeline
invocation, evidence review, terminal-state interpretation, troubleshooting,
manual replay, validation, and safety boundaries.

## Technology demonstrated

- CPython `>=3.13,<3.14` with a `src` package layout
- PostgreSQL and Psycopg 3
- SQL-first migrations and relational contract validation
- Pydantic and pydantic-settings
- PyYAML and Python centralized logging
- Pytest, pytest-cov, and guarded real-PostgreSQL integration tests
- Ruff linting and formatting

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

## Configuration and security

Validated settings use process environment, then repository-root `.env`, then
safe defaults. Database access requires the complete five-value `DATABASE_*`
group; generic application startup remains database-free. `.env.example`
contains placeholders only, while the ignored `.env` holds environment-specific
values and must never be committed. See the
[configuration guide](docs/development/configuration-guide.md),
[logging guide](docs/development/logging-guide.md), and
[operational runbook](docs/operations/runbook.md#configuration).

## Testing and validation

The layered test architecture uses the lowest sufficient layer: unit/contract,
component integration, cross-layer integration, PostgreSQL-backed system, and
local operator boundary. Guarded system scenarios exercise successful
execution, governed `BLOCKED`, technical `FAILED`, and deterministic replay
against a dedicated `_test` database.

Repeatable validation includes:

```text
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m sales_data_platform
python -m sales_data_platform.orchestration --help
```

See the [testing architecture](docs/architecture/testing.md) for strategy and
the [runbook validation section](docs/operations/runbook.md#validation) for the
PostgreSQL safety boundary.

## Architecture decisions and technical navigation

| Concern | Authoritative documentation | Decision record |
| --- | --- | --- |
| System boundaries | [Architecture overview](docs/architecture/architecture-overview.md) | — |
| PostgreSQL and migrations | [Database design](docs/architecture/database-design.md) | [ADR-001](docs/adr/ADR-001-sql-first-versioned-migration-strategy.md) |
| Governed ingestion | [Ingestion architecture](docs/architecture/data-ingestion.md) | [ADR-002](docs/adr/ADR-002-versioned-source-contracts-and-canonical-ingestion-boundary.md) |
| Canonical transformation | [Transformation architecture](docs/architecture/data-transformation.md) | [ADR-003](docs/adr/ADR-003-canonical-transformation-boundary-and-versioned-transformation-contracts.md) |
| Data Quality | [Data Quality architecture](docs/architecture/data-quality.md) | [ADR-004](docs/adr/ADR-004-governed-versioned-data-quality-expectations-and-structured-outcomes.md) |
| Pipeline orchestration | [Orchestration architecture](docs/architecture/pipeline-orchestration.md) | [ADR-005](docs/adr/ADR-005-application-native-pipeline-orchestration-with-durable-execution-state.md) |
| Operations | [Operational runbook](docs/operations/runbook.md) | — |
| Testing | [Testing architecture](docs/architecture/testing.md) | — |

Additional references: [project structure](docs/project-structure.md),
[development setup](docs/development/setup-guide.md), and
[changelog](CHANGELOG.md).

## Known boundaries

- Repository 1 executes locally and has no Azure/cloud deployment.
- Execution is manual; there is no scheduler.
- There is no automatic retry or automatic resume.
- There is no exactly-once guarantee.
- Stages are sequential; there is no concurrency guarantee.
- There is no external monitoring platform.
- Repository 2 cloud capabilities and Repository 3–4 concerns are intentionally
  excluded.

These are deliberate Repository 1 boundaries. Milestone 8 and later governed
work may improve readiness and presentation without implying that Repository 1
or the wider portfolio is complete.
