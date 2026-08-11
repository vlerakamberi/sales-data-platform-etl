# Data Quality architecture

## Purpose

Milestone 5 defines how Repository 1 will evaluate source-valid, successfully
canonicalized governed data against explicit Northstar business-quality
expectations. It addresses business trustworthiness after upstream structural
and canonical validity have been established. This document describes the
approved architecture in ADR-004; it does not claim that production Data
Quality code or production Northstar quality expectations exist.

## Architecture placement

```text
governed source
→ source-contract / ingestion validation
→ canonical transformation
→ Data Quality evaluation
→ later pipeline responsibilities
```

Milestone 3 owns source-contract and ingestion validation. The canonical
transformation boundary governed by ADR-003 owns conversion into valid
canonical Northstar representations. ADR-004 places business Data Quality
evaluation after successful canonical transformation and before later pipeline
responsibilities.

## Upstream assumptions

Data Quality may assume that:

- the source contract succeeded;
- ingestion produced validated governed data and provenance;
- canonical transformation succeeded;
- canonical data satisfies the Milestone 4 contract;
- relevant existing provenance remains available.

Canonical validity establishes conformance to the canonical representation; it
does not itself imply business trustworthiness or satisfaction of a particular
business-quality expectation.

## Conceptual responsibilities

The architecture has these conceptual responsibilities:

- **Quality Expectation Definition** records governed identity, meaning,
  applicability, evaluation, disposition, and evidence semantics.
- **Applicability Determination** decides whether an expectation legitimately
  applies to its governed scope.
- **Quality Evaluation** evaluates the condition when the expectation applies.
- **Outcome Construction** produces one normalized, traceable semantic result.
- **Quality Summary / Aggregation** derives interpretable counts, populations,
  and rates from structured outcomes.
- **Framework Validation** rejects invalid or internally inconsistent
  expectation and framework configuration.

These are responsibility boundaries, not prescribed Python classes, modules,
or a required internal object model.

## Expectation contract

A lightweight governed expectation contract describes:

- stable logical identity;
- explicit semantic version or revision;
- human-readable purpose;
- business rationale;
- governed canonical scope;
- evaluation scope;
- deterministic applicability semantics;
- deterministic evaluation semantics;
- `BLOCKING` or `NON_BLOCKING` disposition;
- minimum necessary evidence semantics.

The contract is explicit and inspectable. It is not a generic rules registry,
plugin system, expression DSL, dynamic discovery mechanism, or
persistence-backed configuration platform.

## Evaluation scopes

The approved conceptual scopes are:

- `record`, for an expectation whose meaning concerns one canonical record;
- `collection`, for an expectation whose meaning concerns a governed
  collection;
- `governed business group`, for an expectation whose meaning concerns an
  explicitly defined business grouping.

A scope is introduced only when justified by business semantics. This
architecture does not claim that each scope already has an implemented
production rule.

## Evaluation states

Every completed evaluation has exactly one semantic state:

- `SATISFIED`: the expectation applied and the condition was met;
- `VIOLATED`: the expectation applied and the business-quality condition was
  not met;
- `NOT APPLICABLE`: the expectation legitimately did not apply and is not a
  pass;
- `EVALUATION ERROR`: required evaluation could not complete reliably, is not
  a business-quality violation, and must never be treated as a pass.

A normal `VIOLATED` outcome is expected business-quality information and does
not inherently require a software exception.

## Applicability

Applicability is evaluated before quality success or failure:

```text
does expectation apply?
no → NOT APPLICABLE
yes → evaluate
  true → SATISFIED
  false → VIOLATED
  cannot reliably evaluate → EVALUATION ERROR
```

This ordering prevents non-applicable data from being counted as satisfied and
keeps unreliable execution distinct from a business-quality violation.

## Blocking and non-blocking disposition

Exactly two governed dispositions exist: `BLOCKING` and `NON_BLOCKING`.
Disposition belongs to the governed versioned expectation because it expresses
business policy, and each result records the disposition used. No severity
hierarchy is part of this architecture.

Milestone 5 reports the structured result and disposition. It does not schedule
work, stop a pipeline, retry processing, or otherwise implement a downstream
workflow reaction.

## Provenance and traceability

Quality traceability connects:

```text
canonical data
↔ existing provenance
↔ quality expectation/version
↔ quality outcome
```

Milestone 5 reuses the existing provenance authority and adds only
quality-specific metadata needed for this connection. It does not copy complete
provenance, reconstruct source lineage, or establish a second provenance
system.

## Deterministic replay

ADR-004 establishes this invariant:

```text
Equivalent governed semantic inputs evaluated under the same governed quality expectation version must produce equivalent semantic quality results.
```

Relevant semantic inputs may include governed canonical data, governed source
or source-contract context retained upstream, transformation context needed for
reproducibility, expectation identity and version, governed applicability
semantics, and explicitly governed reference inputs.

Run identity is traceability-only. Different runs may have different run or
correlation identities without changing semantic outcomes. Unless explicitly
governed as an expectation input, wall-clock time, execution ordering, machine
identity, working directory, incidental environment state, and current
database state must not affect the result.

## Expectation evolution

A logical expectation retains stable identity. A material semantic change
requires a new identifiable semantic version or revision; no particular
version-number syntax is prescribed. Material changes include business
meaning, canonical scope, applicability, evaluation, disposition, and governed
reference-input semantics.

Accepted definitions must not silently mutate. Explicit revisions preserve the
meaning of historical results and make deterministic replay possible while
retaining the continuity of the logical business expectation.

## Metrics and observability

Structured outcomes support interpretable measures such as:

- evaluated population;
- applicable population;
- satisfied count;
- violation count;
- affected population;
- blocking violation count;
- non-blocking violation count;
- not-applicable count;
- evaluation-error count;
- violation rates with explicit denominators.

Rate names and outputs must identify their denominator so that, for example, a
rate over applicable records cannot be confused with a rate over all evaluated
records. The architecture defines no generic composite Data Quality Score and
requires no dashboard.

Observability may communicate safe identities, counts, states, and diagnostic
context. It must preserve the evidence and privacy constraints below.

## Failure taxonomy

The architecture distinguishes:

- a **business-quality violation**, represented by `VIOLATED` when an
  applicable condition is not met;
- a **non-applicable expectation**, represented by `NOT APPLICABLE` and not
  counted as a pass;
- an **evaluation execution failure**, represented by `EVALUATION ERROR` when
  a required evaluation cannot complete reliably and never counted as a pass;
- **invalid framework or expectation configuration**, rejected through
  framework validation rather than reclassified as an ordinary business
  violation.

These categories preserve the difference between governed business outcomes,
legitimate applicability decisions, execution reliability, and invalid system
definitions.

## Privacy and evidence

Results contain only evidence necessary to explain and trace the outcome.
Preferred evidence includes expectation identity and version, governed
identifiers, provenance references, affected scope, and bounded safe
explanations.

Complete raw records, complete canonical records, and sensitive values are not
captured by default. A sensitive value may appear only when genuinely required
by governed evidence semantics and handled appropriately. Secrets and
credentials must never appear in expectation definitions, outcomes, logs, or
diagnostics.

## Persistence boundary

Persistent quality-result storage is not required by the Milestone 5 core Data
Quality evaluation contract. PostgreSQL remains outside the core Data Quality
evaluation contract. Later, separately governed functionality may consume or
persist structured results; this architecture introduces no persistence
design.

## Orchestration boundary

Milestone 5 does not own:

- scheduling;
- retries;
- dependency management;
- workflow coordination;
- pipeline state machines;
- operational or downstream pipeline control;
- broader execution history.

It exposes structured outcomes and governed dispositions that later consumers
may act upon. It does not implement those actions.

## Testing boundary

Milestone 5 must test the capability it introduces, including expectation
semantics, applicability, outcome construction, deterministic replay,
aggregation, framework validation, provenance continuity, and safe evidence as
applicable. This obligation does not absorb or pre-implement the later
dedicated Repository 1 Testing milestone. This architecture-only commit does
not claim that Milestone 5 integration validation has occurred.

## Non-goals

The approved Data Quality architecture does not introduce:

- source-contract redesign;
- duplicated ingestion validation;
- duplicated canonical transformation logic;
- automatic remediation;
- arbitrary thresholds without governed business meaning;
- generic accuracy claims;
- generic timeliness service-level agreements;
- a generic or composite Data Quality score;
- a generic rules engine, registry, plugin system, or expression DSL;
- persistent quality-result storage or persistence-backed rule configuration;
- orchestration, scheduling, retries, or pipeline control;
- Azure services;
- Spark or Databricks;
- distributed Data Quality processing;
- warehouse architecture;
- dashboards;
- Repository 2–4 functionality or other later Repository 1 capabilities.

This document records approved architecture only. It does not claim that
Milestone 5 is implemented, complete, or validated, or that Repository 1 is
complete.
