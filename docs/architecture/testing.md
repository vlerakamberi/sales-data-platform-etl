# Testing architecture

## Purpose and scope

Milestone 7 hardens and validates Repository 1 as an integrated local ETL
system. Testing established in Milestones 1–6 is inherited as authoritative
regression evidence. Milestone 7 does not exist to introduce the repository's
first tests or to inflate test counts.

This document records the approved testing strategy. It does not redesign
Repository 1, introduce a new architecture decision, or represent future
Milestone 7 tests as implemented. Repository 1 remains **NOT COMPLETE**.

## Inherited validation baseline

The inherited Milestone 6 regression results are:

| Validation | Inherited result |
| --- | --- |
| Orchestration unit | 103 passed |
| Orchestration integration | 13 passed |
| Runtime metrics | 13 passed |
| Real PostgreSQL orchestration | 1 passed — **NOT SKIPPED** |
| Full unit | 475 passed, 4 skipped |
| Full integration | 125 passed |
| Full repository | 600 passed, 4 skipped |
| Coverage | 91% |
| Ruff | PASS |
| Formatting | PASS |
| `pip check` | PASS |
| Generic database-free startup | PASS |
| Orchestration CLI help | PASS |
| `git diff --check` | PASS |

These results are inherited Milestone 6 regression evidence. They are not
Milestone 7 completion results, future required test counts, test-count targets,
or proof that Milestone 7 has already completed validation.

## Layered testing architecture

The conceptual testing hierarchy is:

```text
Unit / Contract
→ Component Integration
→ Cross-Layer Integration
→ PostgreSQL-Backed System
→ Local E2E / Operator Boundary
```

The governing principle is: **“Use the lowest test layer that can reliably
prove the contract.”** Higher-cost layers are used only when they provide
meaningful evidence unavailable at a lower layer. Test-count inflation for its
own sake is rejected.

## Inherited coverage and genuine Milestone 7 gaps

Inherited testing already provides substantial evidence for:

- unit and domain contracts;
- ingestion;
- transformation;
- Data Quality;
- orchestration;
- durable PostgreSQL history;
- lifecycle transitions;
- failure classifications;
- runtime metrics;
- CLI and operator-facing contracts;
- successful assembled PostgreSQL execution.

Milestone 7 does not duplicate already sufficient successful-path evidence.
The three approved future integrated-system evidence gaps are:

1. governed Data Quality `BLOCKED`;
2. technical `FAILED`;
3. deterministic replay.

These gaps are future Commit 2 responsibilities. They are recorded here and
are not implemented by Commit 1.

### Governed Data Quality `BLOCKED`

The expected integrated lifecycle is:

```text
INGESTION       = SUCCEEDED
TRANSFORMATION  = SUCCEEDED
DATA_QUALITY    = SUCCEEDED
PIPELINE        = BLOCKED
```

`BLOCKED` represents successful technical processing whose governed Data
Quality disposition prevents progression. It is not a technical execution
failure. The Data Quality stage therefore remains `SUCCEEDED` while the
pipeline records the governed `BLOCKED` outcome.

### Technical `FAILED`

A deterministic technical execution failure must result in:

```text
PIPELINE = FAILED
```

The future integrated test must protect correct stage failure attribution,
correct partial-progress history, correct durable PostgreSQL history, and the
absence of an incorrect `BLOCKED` classification.

### Deterministic replay

Repeated execution of the same deterministic governed source must preserve:

- distinct pipeline execution identities;
- stable deterministic source and content semantics where applicable;
- contract-consistent outcomes;
- separate durable histories;
- no automatic resume implication;
- no exactly-once guarantee;
- no reuse of the previous pipeline execution identity.

Source identity, run identity, and pipeline execution identity remain distinct.
Source identity describes deterministic governed source content, run identity
identifies a particular ingestion execution, and pipeline execution identity
identifies one orchestration attempt. Replay preserves those boundaries rather
than collapsing their meanings.

## PostgreSQL-backed testing and safety

Existing dedicated test-database safeguards require that:

- the configured database name ends with `_test`;
- the actual `current_database()` equals the configured database name;
- destructive cleanup is restricted to an explicit Repository 1 allowlist;
- required migrations are applied inside the guarded test boundary;
- teardown is protected by the same database safety guard.

Fixture reuse is the approved default. Commit 1 neither modifies fixtures nor
proposes fixture refactoring.

## Durable lifecycle and history

Where persistence semantics are under test, system-level evidence must compare
returned execution results with durable PostgreSQL execution and stage history.
Tests preserve existing lifecycle semantics, including truthful partial-progress
visibility when later work fails or is skipped. This strategy introduces no
retry or resume semantics.

## Fixture and test-data principles

Milestone 7 test data should be:

- deterministic;
- minimal;
- repository-owned;
- synthetic;
- privacy-safe;
- traceable to a specific governed scenario.

Existing fixtures should be reused where they can express the required scenario
clearly.

## Failure injection

Deterministic technical failure injection should use existing Python testing
mechanisms and existing architectural seams. It must not require production-only
fault-injection hooks. Broad mocking that bypasses the contract under test is
not acceptable evidence.

## Regression, coverage, and quality gates

Milestones 1–6 remain the protected regression baseline. The inherited
approximately 91% coverage value is a regression reference, not a target for
artificial test creation.

Final Milestone 7 closure is expected to require:

- approved Milestone 7 targeted tests passing;
- required PostgreSQL integration and system tests passing;
- the inherited regression suite passing;
- no unexplained material coverage regression;
- Ruff check PASS;
- Ruff format check PASS;
- `pip check` PASS;
- generic database-free startup PASS;
- orchestration CLI help PASS;
- `git diff --check` PASS;
- dedicated `_test` PostgreSQL safeguard verification.

An increase in test count is not an acceptance criterion.

## Explicit non-goals

Milestone 7 does not introduce:

- production feature development;
- new source contracts;
- new transformation semantics;
- new Data Quality expectations merely for testing;
- production-code changes;
- SQL or migration changes;
- automatic retry;
- automatic resume;
- exactly-once guarantees;
- scheduler functionality;
- concurrency requirements;
- Azure or cloud orchestration;
- deployment or release functionality;
- production fault-injection hooks;
- new testing frameworks;
- Repository 2 functionality;
- a declaration that Repository 1 is complete.

Repository 1 remains **NOT COMPLETE**.
