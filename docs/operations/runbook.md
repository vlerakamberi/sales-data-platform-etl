# Repository 1 operational runbook

## Purpose and scope

This runbook is the canonical operator guide for preparing, configuring,
initializing, invoking, observing, diagnosing, interpreting, and safely rerunning
the existing Repository 1 local ETL platform.

The operational boundary is one manual, sequential execution of ingestion,
canonical transformation, and business Data Quality evaluation with durable
pipeline and stage history in PostgreSQL. This guide documents validated local
behavior; it is not a cloud deployment model. Repository 1 remains in active
development and is not formally complete.

## Prerequisites

### External prerequisites

- CPython `>=3.13,<3.14` (Python 3.13.x).
- PostgreSQL reachable with credentials authorized to create and update objects
  in the selected database schema.
- Git for obtaining and inspecting the repository.

Docker, a cloud account, and an external scheduler are not prerequisites.

### Repository-controlled setup

The repository supplies the Python package, development dependencies, SQL-first
migrations, validated configuration model, logging configuration, governed
source contracts, and local orchestration entry point.

## Environment setup and installation

From the repository root, create and activate a virtual environment, then
install the project in editable mode with its development tools:

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

For POSIX-compatible shells, activate with `source .venv/bin/activate` and copy
the example with `cp .env.example .env`. The local `.env` is ignored by Git and
must not be committed.

## Configuration

Configuration is loaded by `sales_data_platform.config.settings.Settings` with
this precedence:

```text
process environment
→ repository-root .env
→ safe defaults
```

Environment-variable names are case-insensitive. Supported settings are:

| Variable | Contract | Example/default meaning |
| --- | --- | --- |
| `APPLICATION_ENV` | `development`, `test`, or `production` | `development` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` | `INFO` |
| `LOG_TO_FILE` | Boolean | `false`; console logging only |
| `LOG_DIRECTORY` | Path | `logs`; relative paths resolve from repository root |
| `INGESTION_SOURCE_ROOT` | Path | `data/raw`; relative paths resolve from repository root |
| `DATABASE_HOST` | Non-empty host | Environment-specific; for example `localhost` |
| `DATABASE_PORT` | Integer `1`–`65535` | Common local value: `5432` |
| `DATABASE_NAME` | Non-empty database name | Environment-specific |
| `DATABASE_USERNAME` | Non-empty role name | Environment-specific |
| `DATABASE_PASSWORD` | Non-empty secret | Local secret; never commit a real value |

The five `DATABASE_*` settings form one optional group: supply all five for any
database operation or omit all five for database-free generic startup. Do not
commit `.env`, credentials, connection strings, or complete settings output.

The three supported source contracts and discovery directories under
`INGESTION_SOURCE_ROOT` are:

| Contract ID | Version | Source directory |
| --- | --- | --- |
| `northstar.product_catalog` | `1` | `product_catalog/v1` |
| `northstar.ecommerce_sales` | `1` | `ecommerce_sales/v1` |
| `northstar.retail_sales` | `1` | `retail_sales/v1` |

`--source-path` must identify an eligible physical `.csv` file discovered
directly in the applicable directory. Discovery is non-recursive and rejects
symlinked source files and contract directories.

## PostgreSQL preparation

Provision the target database and role outside Repository 1, then set the full
`DATABASE_*` group. The migration engine may initialize a clean schema or
advance a recognized earlier migration state. It rejects a non-clean schema
without migration metadata, unknown or non-contiguous history, changed checksums,
and incompatible migration metadata.

Repository SQL files under `sql/migrations` are authoritative and immutable.
Use the existing public Python database boundary to connect and apply all
missing migrations through V004:

```powershell
python -c "from sales_data_platform.config.settings import Settings; from sales_data_platform.database import connect_database, apply_migrations; connection = connect_database(Settings()); applied = apply_migrations(connection); print([migration.filename for migration in applied]); connection.close()"
```

An empty printed list means the authoritative migration sequence was already
current and passed its integrity checks. Otherwise, the list names migrations
applied in order. A new pipeline invocation requires V004 and does not apply
migrations itself.

The migration API does not create or drop a PostgreSQL database. Select the
intended database carefully before initialization. The `_test` suffix and
allowlisted cleanup safeguards described later apply to repository PostgreSQL
tests, not to ordinary pipeline invocation.

## Pipeline invocation

Review the exact CLI contract without connecting to PostgreSQL:

```powershell
python -m sales_data_platform.orchestration --help
```

Run one governed source:

```powershell
python -m sales_data_platform.orchestration `
  --contract-id northstar.product_catalog `
  --contract-version 1 `
  --source-path data/raw/product_catalog/v1/products.csv
```

Replace the contract and path with one of the supported pairs above. Paths are
interpreted through the configured ingestion root and must satisfy source
discovery. The optional correlation argument is:

```powershell
--predecessor-execution-id <UUID>
```

This records a relationship to an earlier execution. It does not resume that
execution.

## Successful operation

A successful invocation prints a bounded result containing:

- a new `execution_id`;
- pipeline `state: SUCCEEDED`;
- creation, start, and completion timestamps;
- each of `INGESTION`, `TRANSFORMATION`, and `DATA_QUALITY` with state and
  timestamps;
- `predecessor_execution_id` when supplied.

The process exits `0`. PostgreSQL rows in `pipeline_executions` and
`pipeline_stage_executions` are the authoritative durable execution evidence.
Console logs provide diagnostics. If `LOG_TO_FILE=true`, the same centralized
logging setup also writes `sales_data_platform.log` beneath `LOG_DIRECTORY`.

## Operational evidence and observability

Use evidence in this order:

1. The CLI summary identifies the execution, terminal result, stage outcomes,
   timestamps, and bounded failure classification/code when present.
2. PostgreSQL execution and stage history is authoritative for persisted
   lifecycle state and partial progress.
3. Centralized console or rotating-file logs support diagnosis but do not
   replace durable history.

The pipeline lifecycle is `PENDING` → `RUNNING` → one of `SUCCEEDED`, `BLOCKED`,
or `FAILED`. Each fixed stage uses `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`,
or `SKIPPED`. A later stage is `SKIPPED` when an earlier technical failure
prevented it from starting; already completed stages remain visible.

For an execution ID printed by the CLI, an operator with appropriate read
access can inspect the durable records with parameterized queries equivalent to:

```sql
SELECT pipeline_execution_id, predecessor_execution_id, state,
       created_at, started_at, completed_at,
       failure_category, failure_code
FROM pipeline_executions
WHERE pipeline_execution_id = '<execution-uuid>';

SELECT stage, stage_sequence, state, started_at, completed_at,
       failure_category, failure_code
FROM pipeline_stage_executions
WHERE pipeline_execution_id = '<execution-uuid>'
ORDER BY stage_sequence;
```

Failure metadata and CLI output are deliberately bounded. Do not place secrets,
raw rows, complete canonical records, customer personal data, or payment details
in operational notes or logs.

Runtime metrics are derived from authoritative persisted timestamps. A pipeline
or stage duration exists only when both start and completion timestamps exist;
incomplete and skipped work has no duration. Repository 1 does not provide an
external metrics or monitoring service.

## Terminal outcome semantics

### `SUCCEEDED`

All three stages completed successfully and no governed blocking Data Quality
violation prevented progression. Exit code: `0`.

Operator action: retain the execution ID as the durable traceability key and
confirm downstream handling required by the surrounding local workflow.

### `BLOCKED`

Technical processing and Data Quality evaluation completed successfully, but a
governed `BLOCKING` Data Quality violation prevents progression. The Data
Quality stage is `SUCCEEDED`; the pipeline is `BLOCKED` and carries no technical
failure. Exit code: `3`.

Operator action: inspect the execution and stage history and investigate the
governed source-data issue. Correct source data through an authorized process,
then initiate a new execution if appropriate. Do not classify `BLOCKED` as an
infrastructure failure.

### `FAILED`

A technical, configuration, ingestion, transformation, Data Quality evaluation,
unexpected execution, or persistence failure prevented successful completion.
The failed stage, completed earlier stages, and skipped later stages remain
visible when they were durably recorded. Exit code: `1`.

Operator action: use the printed failure category/code, stage history, and logs
to identify the failing boundary. Correct the external condition or source only
through an authorized change, then start a new execution. The CLI also exits `1`
for controlled configuration, connection, orchestration, or cleanup failures;
argument-usage errors exit `2`.

## Diagnostics and troubleshooting

### Configuration

- If generic startup reports configuration failure, validate accepted enum,
  boolean, path, and port values.
- If database operations report incomplete configuration, supply all five
  `DATABASE_*` values together.
- Process environment values override `.env`; check for stale overrides without
  printing secrets.

### PostgreSQL connectivity and setup

- Confirm PostgreSQL is reachable at the configured host and port and that the
  configured role can connect to the selected database.
- A connection failure is intentionally reported without echoing credentials.
- If orchestration fails before returning an execution, confirm migrations
  through V004 using the supported preparation command.
- Migration-state or checksum errors require reconciliation of the database
  with the immutable repository migration history; do not edit an accepted SQL
  migration to force acceptance.

### Ingestion and input

- Confirm the contract ID/version is one of the three supported pairs.
- Confirm the source exists directly beneath its governed contract directory,
  is a physical eligible `.csv` file, and is within `INGESTION_SOURCE_ROOT`.
- Parsing, header, type, or record validation failures reject the source rather
  than returning a partial validated batch. Use bounded logs; do not copy raw
  customer data into diagnostics.

### Data Quality blocking

- Confirm pipeline `BLOCKED` with technically successful stages in durable
  history.
- Treat the outcome as governed business disposition, not a retryable technical
  outage. Investigate the applicable existing expectation and source data.

### Technical failure

- Identify the `FAILED` stage and its `failure_category` and `failure_code`.
- Preserve truthful partial progress: do not rewrite completed or skipped stage
  history.
- A historical execution left `RUNNING` remains visible and is not
  automatically timed out, failed, or resumed.

## Rerun, replay, and recovery

Reruns are manual and operator-driven. Repeating the same deterministic governed
source creates a new pipeline execution identity and separate durable history.
Stable source/content semantics may remain equivalent, while ingestion run and
pipeline execution identities remain distinct.

When useful, pass the prior execution ID with
`--predecessor-execution-id` to record correlation. The prior execution remains
unchanged. Correlation does not imply continuation, retry, or resume.

Repository 1 provides no automatic retry, automatic resume, or exactly-once
guarantee. Diagnose the prior outcome and correct only the authorized external
condition before manually starting another execution.

## Validation

Run operator-relevant checks from the repository root:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pip check
python -m sales_data_platform
python -m sales_data_platform.orchestration --help
```

`python -m sales_data_platform` is a database-free configuration and logging
startup check. CLI help also does not execute a pipeline.

PostgreSQL-backed validation requires a separately provisioned database whose
configured name ends with `_test`:

```powershell
python -m pytest tests/integration/orchestration/test_pipeline_orchestration_integration.py -v
python -m pytest tests/integration/orchestration -v
```

The existing fixtures verify that `current_database()` exactly equals the
configured `_test` database, restrict destructive cleanup to an explicit
Repository 1 relation allowlist, apply migrations inside the guarded boundary,
and repeat the guard before teardown. These tests never create or drop a
database. A skipped PostgreSQL system test is not successful system validation.

## Known operational limitations

- Execution is a manual, local Repository 1 capability, not a cloud deployment.
- There is no automatic retry or automatic resume.
- There is no exactly-once processing guarantee.
- There is no scheduler or recurring-execution service.
- Pipeline stages execute sequentially; there is no concurrency guarantee.
- There is no Azure or other cloud orchestration implementation.
- There is no external monitoring platform.
- There is no Repository 2 functionality in this repository.
