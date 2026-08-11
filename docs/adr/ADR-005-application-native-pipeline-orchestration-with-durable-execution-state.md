# ADR-005

## Title

Application-Native Pipeline Orchestration with Durable Execution State

---

## Status

Accepted

---

## Context

Repository 1 has established independently governed capabilities for source
ingestion, canonical transformation, and business Data Quality evaluation.
Milestone 6 must coordinate those capabilities into one truthful pipeline
execution without reimplementing their domain behavior or introducing an
external orchestration dependency.

The fixed processing flow is:

```text
Ingestion
→ Canonical Transformation
→ Business Data Quality Evaluation
```

Operational coordination requires identity and state that are distinct from
source identity, ingestion run identity, record provenance, transformation
ruleset identity, and Data Quality expectation identity. Logs alone cannot
provide authoritative execution history, especially when a process is
interrupted or state persistence partially succeeds.

The orchestration design must preserve the semantic distinction between a
business-quality policy outcome and a technical failure. In particular, a
blocking quality violation means Data Quality evaluation completed
successfully, while an evaluation error means the Data Quality stage could not
complete reliably.

Repository 1 also needs durable partial-progress history, explicit recovery
semantics, safe observability, and continued separation between operational
metadata and canonical business data. These requirements must fit the existing
SQL-first migration architecture without making generic application startup
depend on PostgreSQL.

## Decision

Repository 1 will use application-native Python orchestration for a fixed,
sequential pipeline. No third-party or local orchestration framework is part of
Milestone 6, and no configurable DAG is introduced.

Every execution attempt receives a new immutable pipeline execution identity.
That identity is distinct from all source, ingestion-run, provenance,
transformation, and Data Quality identities. It supplements existing
traceability and may optionally correlate to a predecessor execution, but it
does not replace or mutate earlier identities.

Pipeline executions use exactly these lifecycle states:

```text
PENDING
RUNNING
SUCCEEDED
BLOCKED
FAILED
```

`SUCCEEDED`, `BLOCKED`, and `FAILED` are terminal pipeline states.

Each fixed stage uses exactly these lifecycle states:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
SKIPPED
```

The orchestration control semantics are:

- A normal non-blocking Data Quality result does not independently prevent the
  pipeline from becoming `SUCCEEDED`.
- A `BLOCKING` Data Quality violation means the Data Quality stage technically
  completes as `SUCCEEDED`, while the pipeline becomes `BLOCKED`.
- A Data Quality `EVALUATION_ERROR` means the Data Quality stage becomes
  `FAILED` and the pipeline becomes `FAILED`.
- An upstream technical failure makes the pipeline `FAILED`; downstream stages
  that never started become `SKIPPED`.
- Completed upstream stages remain durably visible rather than being rolled
  back or rewritten.

PostgreSQL will be the authoritative store for durable orchestration execution
history. Repository 1 will reuse the SQL-first, ordered, immutable migration
architecture accepted in ADR-001. Orchestration operational metadata remains
logically separate from canonical business data and records execution-level
history, stage-level history, safe failure metadata, and correlation to
existing provenance where required.

Orchestration state persistence is part of correctness. State transitions use
bounded persistence operations; the complete cross-stage pipeline is not
wrapped in one database transaction. A failure of required state persistence
is a technical orchestration failure. If a successful transition cannot be
persisted, orchestration must not falsely report that transition as durably
successful.

Durable history preserves partial progress. An interrupted historical
execution left in `RUNNING` remains visibly `RUNNING`. Milestone 6 neither
automatically resumes it nor silently rewrites it as `FAILED`, and it does not
infer abandonment from an implicit timeout.

A restart creates a new pipeline execution identity and begins again from
ingestion. The prior execution remains immutable. The new execution may carry
an optional predecessor correlation, but there is no automatic retry and no
automatic resume.

Execution is sequential. Milestone 6 has no concurrency, parallel-stage,
distributed-worker, or queue requirement.

The orchestrator reuses the established Milestone 1 configuration, paths,
logging, and bootstrap; Milestone 2 PostgreSQL and migration architecture;
Milestone 3 ingestion and provenance; Milestone 4 canonical transformation;
and Milestone 5 Data Quality contracts and outcomes. Earlier milestone layers
do not depend on orchestration internals.

Generic application startup remains database-free. A future explicit
orchestration invocation may require PostgreSQL because durable state is part
of orchestration correctness. Repository 1 introduces no Repository 2 or Azure
orchestration dependency.

## Alternatives Considered

### Airflow, Prefect, Dagster, or Another Third-Party Local Framework

Adopt a general-purpose local orchestration framework for stage execution,
state, retries, and observability. This was rejected because the approved flow
is fixed and sequential, and framework installation, runtime services,
abstractions, and dependency surface would exceed the demonstrated need.

### Azure-Managed Orchestration

Use Azure Data Factory, Azure Functions, Logic Apps, or another managed Azure
service. This was rejected because Milestone 6 is a local Repository 1
capability and must not introduce Repository 2 or cloud-runtime dependencies.

### Log-Only Authoritative Execution History

Treat diagnostic logs as the source of truth for pipeline and stage state.
This was rejected because logs do not provide a controlled durable state model,
cannot reliably enforce transitions, and can leave completion or interruption
ambiguous.

### File-Based Authoritative Execution History

Persist orchestration state in local JSON, YAML, or other files. This was
rejected because concurrent or interrupted writes, integrity, querying, and
transactional state transitions would require a separate persistence design
while Repository 1 already has an approved PostgreSQL architecture.

### Retry/Resume-Oriented Orchestration

Automatically retry failed stages or resume incomplete executions. This was
rejected because it complicates identity, replay, idempotency, and state
semantics beyond the approved milestone. Recovery instead creates a new
execution from ingestion with optional predecessor correlation.

### One Database Transaction Spanning the Complete Pipeline

Wrap ingestion, transformation, Data Quality, and all state transitions in one
database transaction. This was rejected because the stages are independent
capabilities, the pipeline may be long-running, and durable partial progress
must survive technical failure or interruption.

## Consequences

### Positive

- The fixed pipeline remains explicit, inspectable, and application-native.
- Pipeline and stage lifecycles have normalized, durable meanings.
- Partial execution progress remains historically truthful after failures.
- Business-quality blocking remains distinct from technical failure.
- PostgreSQL provides authoritative state without creating a second migration
  architecture.
- New execution identity and optional predecessor correlation make restarts
  traceable without rewriting history.
- Sequential execution avoids premature concurrency and distributed-systems
  complexity.
- Existing Milestones 1–5 remain authoritative for their own behavior.
- Generic application startup remains database-free.

### Negative

- Repository 1 must implement and maintain orchestration state transitions and
  bounded persistence operations directly.
- Explicit orchestration execution requires PostgreSQL availability.
- Required state-persistence failures become orchestration failures even when
  domain processing may already have completed in memory.
- Interrupted `RUNNING` executions require explicit operational interpretation
  because they are not automatically finalized or resumed.
- Restarting repeats work from ingestion and provides no automatic retry or
  stage-level resume efficiency.
- The selected approach deliberately lacks framework schedulers, dashboards,
  retry policies, concurrency, and distributed execution features.

## Rationale

Application-native orchestration is the smallest design that can coordinate
Repository 1's fixed local pipeline while making execution state durable and
truthful. A third-party framework or Azure-managed service would add a larger
operational model than the approved sequential flow requires, while log-only or
file-based history would be too weak for authoritative state.

PostgreSQL-backed execution history aligns with ADR-001 and makes partial
progress, failure propagation, and restart correlation explicit. Bounded state
transactions preserve durable progress without pretending that the complete
pipeline is one atomic database operation. New execution identity on restart
protects historical truth and deterministic domain semantics without claiming
exactly-once processing.

This approach accepts direct implementation responsibility and deliberately
defers scheduling, retry, resume, concurrency, distributed orchestration, and
cloud integration. It therefore provides the required control and durability
without broadening Milestone 6 beyond Repository 1's established architecture.
