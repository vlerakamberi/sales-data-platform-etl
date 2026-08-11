# Pipeline orchestration architecture

## Purpose and status

Milestone 6 defines the approved architecture for coordinating Repository 1's
existing ingestion, canonical transformation, and business Data Quality
capabilities. This document is an architecture reference, not an implementation
plan, and does not claim that Milestone 6 or Repository 1 is complete.

## Orchestration boundary

Milestone 6 owns:

- execution coordination and control;
- pipeline and stage lifecycle state;
- stage coordination;
- interpretation of Data Quality outcomes for pipeline control state;
- durable execution history;
- operational summaries and metrics;
- orchestration-level observability.

It does not own or reimplement:

- source parsing or source contracts;
- ingestion validation;
- canonical mappings or transformation rules;
- Data Quality expectations or evaluation rules;
- migration-engine behavior;
- existing provenance semantics.

## Fixed stage sequence

The sequence is exactly:

```text
Ingestion
→ Canonical Transformation
→ Business Data Quality Evaluation
```

Execution is sequential. There is no configurable DAG, additional stage,
parallel-stage behavior, or Milestone 6 concurrency requirement.

## Execution identity

Every attempt receives a new immutable pipeline execution identity. It is
distinct from source identity, ingestion run identity, record provenance,
transformation ruleset identity, and Data Quality expectation identity.

Pipeline execution identity supplements existing provenance; it does not
replace it. The same deterministic source input may execute again under a new
pipeline execution identity. This is replay with separate traceability, not an
exactly-once processing claim.

## Pipeline lifecycle

Pipeline state is exactly:

```text
PENDING
RUNNING
SUCCEEDED
BLOCKED
FAILED
```

Terminal states are exactly:

```text
SUCCEEDED
BLOCKED
FAILED
```

`PENDING` represents a durably known execution that has not started.
`RUNNING` represents an execution whose work has started. Terminal state is
derived from truthful stage progress and Data Quality control semantics.

## Stage lifecycle

Each of the three fixed stages uses exactly:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
SKIPPED
```

`SKIPPED` means the stage did not start because an earlier technical failure
prevented execution. It is not a synonym for success or business
non-applicability.

## Data Quality control semantics

Data Quality business outcomes and technical completion are distinct:

```text
BLOCKING
→ Data Quality evaluation technically completes
→ Data Quality stage SUCCEEDED
→ pipeline BLOCKED
```

```text
NON_BLOCKING
→ does not independently prevent pipeline SUCCEEDED
```

```text
NOT_APPLICABLE
→ valid non-failure outcome
```

```text
EVALUATION_ERROR
→ Data Quality stage FAILED
→ pipeline FAILED
```

A blocking violation must never be collapsed into a generic technical failure.
`BLOCKING` is governed policy information; it does not itself invoke an
external scheduler, terminate another process, or implement downstream
workflow behavior.

## Technical failure propagation

An upstream technical failure makes the pipeline `FAILED`. Later stages that
have not started become `SKIPPED`, while completed upstream work remains
visible. For example:

```text
INGESTION       SUCCEEDED
TRANSFORMATION  FAILED
DATA_QUALITY    SKIPPED
PIPELINE        FAILED
```

This state records truthful partial progress rather than rolling back or
rewriting already completed stages.

## Durable execution history

PostgreSQL is the authoritative durable store for orchestration history. The
implementation will reuse ADR-001's SQL-first, ordered, immutable migration
architecture. This documentation commit creates no migration or SQL design.

Operational orchestration metadata remains logically separate from canonical
business data. Durable history covers:

- execution-level identity, lifecycle, timestamps, and terminal state;
- stage-level identity, order, lifecycle, and transition history;
- bounded safe technical-failure metadata;
- optional predecessor-execution correlation;
- correlation to existing execution and record provenance where required.

The orchestration store does not become a new source-lineage authority and does
not duplicate canonical records or raw source payloads.

## Persistence boundaries

State transitions are independently durable through bounded orchestration
persistence operations. The pipeline is not one database transaction spanning
all three stages.

Execution-state persistence is part of orchestration correctness. Failure of a
required persistence operation is a technical orchestration failure. If a
success transition cannot be persisted, the orchestrator must not falsely
report that success as durable. Previously committed stage and execution state
remains historically visible.

## Restart and recovery

A restart:

- creates a new pipeline execution identity;
- starts again from ingestion;
- leaves the previous execution unchanged;
- may record an optional predecessor-execution relationship.

There is no automatic retry and no automatic resume.

An interrupted historical execution that remains `RUNNING`:

- remains visible as `RUNNING`;
- is not automatically resumed;
- is not silently converted to `FAILED`;
- is not classified as abandoned through an implicit timeout.

Any future operational reconciliation policy requires separate governance.

## Observability

Three concerns remain separate:

1. PostgreSQL-backed durable execution history is authoritative for execution
   and stage state.
2. Structured execution summaries and runtime metrics support operational
   interpretation.
3. Centralized structured diagnostic logging supports investigation.

Logs are not authoritative execution history. Summaries and logs must not
silently rewrite persisted lifecycle state.

## Security and privacy

Operational state, summaries, and logs must not expose:

- credentials or secrets;
- customer personally identifiable information;
- raw source rows;
- complete canonical records;
- payment details;
- uncontrolled payload contents.

Failure metadata is bounded and safe. Existing upstream privacy and provenance
contracts remain authoritative.

## Provenance and replay

Pipeline execution identity connects orchestration history to existing
provenance without replacing, reconstructing, or mutating it. Source identity,
ingestion run identity, transformation ruleset identity, and Data Quality
expectation identity retain their established meanings.

Equivalent deterministic source input may be processed again under a new
pipeline execution identity. Run and execution identity differences are
traceability differences and do not independently change governed ingestion,
transformation, or quality semantics. No exactly-once guarantee is introduced.

## Startup and invocation

Generic application startup remains database-free. It must not connect to
PostgreSQL merely because orchestration architecture exists.

A future explicit orchestration invocation may require PostgreSQL because
durable execution-state persistence is part of correctness. Manual or local
invocation is conceptually supported, but this architecture does not freeze an
unverified CLI command or syntax.

## Concurrency

Pipeline execution is sequential. Milestone 6 does not require parallel
stages, concurrent workers, queues, distributed locks, or distributed
orchestration.

## Milestone interfaces

The established dependency boundaries remain:

- Milestone 1 provides configuration, paths, logging, and bootstrap.
- Milestone 2 provides PostgreSQL infrastructure and SQL-first migrations.
- Milestone 3 provides ingestion, source contracts, and provenance.
- Milestone 4 provides canonical transformation.
- Milestone 5 provides Data Quality contracts, evaluation, expectations, and
  structured outcomes.
- Milestone 6 provides coordination, lifecycle control, and durable operational
  history only.

Earlier milestones must not depend on orchestration internals. Orchestration
composes their public boundaries.

## Explicit exclusions

Milestone 6 does not introduce:

- a scheduler or cron/recurring scheduling;
- Airflow, Prefect, or Dagster;
- Azure Data Factory, Azure Functions, Logic Apps, or other Azure-managed
  orchestration;
- automatic retry or automatic resume;
- parallel stages or concurrent workers;
- queues or distributed orchestration;
- exactly-once guarantees;
- Spark or Databricks;
- warehouse implementation;
- Repository 2 responsibilities;
- later-milestone implementation.

It also does not introduce a configurable DAG, production CLI syntax, or an
orchestration migration in this architecture-only commit.
