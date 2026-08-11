# ADR-004

## Title

Governed Versioned Data Quality Expectations and Structured Outcomes

---

## Status

Accepted

---

## Context

Repository 1 processes governed data through distinct responsibility boundaries:

```text
source-contract / ingestion validation
→ canonical transformation
→ business Data Quality evaluation
→ later pipeline responsibilities
```

Milestone 3 owns failures of source-contract conformance, parsing, and ingestion
validation. Milestone 4 owns failures to produce a valid canonical Northstar
representation. Neither boundary answers the separate business question of
whether source-valid and canonically valid data satisfies an explicit
business-quality expectation.

Milestone 5 requires that distinct post-transformation capability. It must make
quality meaning governed, reproducible, traceable, and safe to consume without
embedding checks in transformation or expanding into a generic enterprise
rules platform. It must also remain independent of PostgreSQL persistence and
of later orchestration responsibilities.

## Decision

Repository 1 will implement Data Quality as a separate post-transformation
capability based on lightweight governed business-quality expectation
contracts.

Each expectation contract defines:

- a stable logical identity;
- an explicit semantic version or revision, without prescribing a particular
  version-number syntax;
- a human-readable business description and rationale;
- its governed canonical scope and evaluation scope;
- deterministic applicability semantics;
- deterministic evaluation semantics;
- exactly one governed disposition, `BLOCKING` or `NON_BLOCKING`;
- minimum necessary evidence semantics.

The approved conceptual evaluation scopes are `record`, `collection`, and
`governed business group`. A scope is used only where justified by the
business-quality semantics; this decision does not require a production
expectation at every scope.

Applicability is determined before the quality condition is evaluated. Every
evaluation produces exactly one of these semantic states:

- `SATISFIED`: the expectation applied and its condition was met;
- `VIOLATED`: the expectation applied and its business-quality condition was
  not met;
- `NOT APPLICABLE`: the expectation legitimately did not apply; this is not a
  pass;
- `EVALUATION ERROR`: the required evaluation could not complete reliably;
  this is not a business-quality violation and must never be treated as a
  pass.

A normal `VIOLATED` result is an expected business-quality outcome and does not
inherently require software-exception semantics. Invalid expectation or
framework configuration remains distinct from these normalized evaluation
states.

Exactly two violation dispositions exist: `BLOCKING` and `NON_BLOCKING`.
Disposition belongs to the versioned expectation because it expresses
governed business policy. The result records the disposition used. No
`critical`, `high`, `medium`, `low`, or other severity hierarchy is introduced.
Milestone 5 communicates disposition but does not implement downstream
workflow action.

A logical expectation retains stable identity across its evolution. A material
change requires a new identifiable semantic version or revision. Material
changes include changes to business meaning, applicable canonical scope,
applicability semantics, evaluation semantics, blocking or non-blocking
disposition, or governed reference-input semantics. An accepted definition
must not silently mutate historical meaning.

Deterministic replay follows this invariant:

```text
Equivalent governed semantic inputs evaluated under the same governed quality expectation version must produce equivalent semantic quality results.
```

Relevant semantic inputs may include governed canonical data, governed source
or source-contract context preserved upstream, transformation context required
for reproducibility, expectation identity and version, governed applicability
semantics, and explicitly governed reference inputs. Run identity is
traceability-only and may differ without changing the semantic result.
Uncontrolled wall-clock time, execution ordering, machine identity, working
directory, incidental environment state, and current database state must not
affect semantic outcomes unless an input is explicitly governed as part of the
expectation.

Milestone 5 reuses existing provenance and adds only the quality-specific
traceability metadata required to connect:

```text
canonical data
↔ existing provenance
↔ quality expectation/version
↔ quality outcome
```

It does not duplicate complete provenance, reconstruct source lineage, or
create a second provenance authority.

Results use minimum necessary evidence. Governed identifiers, provenance
references, affected scope, and safe explanatory evidence are preferred where
sufficient. Complete raw or canonical records and sensitive values are not
included by default. Secrets and credentials must never appear in expectation
definitions, results, or diagnostics.

Structured outcomes may support interpretable metrics including evaluated and
applicable populations; satisfied, violation, affected, blocking-violation,
non-blocking-violation, not-applicable, and evaluation-error counts; and
violation rates with explicit denominators. This decision does not define a
generic composite Data Quality Score.

Persistent quality-result storage is not required by the Milestone 5 core Data
Quality evaluation contract. PostgreSQL remains outside that core contract;
separately governed downstream functionality may persist outcomes later.

Milestone 5 does not own scheduling, retries, dependency management, workflow
coordination, operational pipeline control, or broader execution history. It
exposes structured outcomes that later consumers may act upon.

The selected design does not introduce a generic enterprise rules registry,
plugin system, expression DSL, dynamic rule discovery, persistence-backed rule
configuration, or persistence-backed rules platform.

## Alternatives Considered

### Embedded Quality Checks in Transformation

Place business-quality checks directly inside canonical transformation. This
was rejected because source interpretation, canonical validity, and business
quality are separate concerns with different outcomes and evolution. Embedding
checks would couple expectation policy to transformation and obscure whether a
record failed canonicalization or violated a quality expectation.

### Separate Post-Transformation Data Quality Capability

Evaluate governed canonical data after successful transformation through a
distinct Data Quality boundary. This was selected because it preserves clear
failure ownership, allows explicit applicability and outcome semantics, and
keeps quality policy independently governed and testable.

### Generic Enterprise Rules Engine

Introduce a generic registry, plugin framework, expression language, or
persistence-backed rules platform. This was rejected because it adds broad
runtime and governance complexity not required by the approved Repository 1
business-quality scope.

### Lightweight Governed Expectation Contracts

Represent each approved business-quality expectation through a small explicit
contract. This was selected because it makes identity, meaning, applicability,
evaluation, disposition, evidence, and evolution inspectable without creating
a generalized rules platform.

### Mutable Expectation Definitions

Allow an expectation definition to change in place. This was rejected because
historical results and replay could silently acquire different meanings.

### Unrelated New Identity for Every Semantic Change

Assign a wholly unrelated logical identity whenever semantics change. This was
rejected as the primary model because it loses continuity of the logical
business expectation and makes its evolution harder to trace.

### Stable Identity With Explicit Immutable Semantic Version or Revision

Retain logical identity while issuing a new identifiable semantic version or
revision for material changes. This was selected because it preserves both
continuity and historical meaning.

### Boolean Pass/Fail Outcomes

Return only pass or fail. This was rejected because it conflates legitimate
non-applicability and unreliable evaluation with quality success or violation.

### Exception-Only Outcomes

Represent unsuccessful quality evaluations only through software exceptions.
This was rejected because a normal business-quality violation is an expected,
structured result rather than inherently an execution fault.

### Structured Normalized Outcomes

Use `SATISFIED`, `VIOLATED`, `NOT APPLICABLE`, and `EVALUATION ERROR`. This was
selected because the states preserve business meaning and support reliable
downstream interpretation and metrics.

### Duplicated Provenance or a Quality-Specific Lineage System

Copy complete upstream provenance or reconstruct lineage within Data Quality.
These alternatives were rejected because they create duplication, drift, and a
competing provenance authority.

### Existing Provenance With Quality-Specific Traceability

Reference existing provenance and add only the metadata needed to connect the
expectation version and outcome. This was selected because it preserves one
provenance authority while making quality results traceable.

### Runtime or Downstream Blocking Determination

Allow runtime code or a downstream consumer to reinterpret whether a violation
is blocking. This was rejected because blocking disposition is business policy
and must be reproducible as part of the governed expectation version.

### Expectation-Governed Disposition

Store `BLOCKING` or `NON_BLOCKING` in the versioned expectation and record the
used value in its result. This was selected because outcome interpretation then
remains explicit, governed, and replayable.

## Consequences

### Positive

- Source-contract, transformation, and business-quality failures remain
  distinguishable.
- Expectation identity and semantic evolution are explicit and auditable.
- Applicability, evaluation, and outcome semantics are deterministic.
- Non-applicability and evaluation errors cannot be misreported as passes.
- Blocking policy is governed with the expectation rather than inferred later.
- Existing provenance remains authoritative while quality outcomes are
  traceable.
- Minimum-evidence behavior reduces unnecessary exposure of governed data.
- Structured results support interpretable metrics with explicit denominators.
- Core evaluation remains independently testable without PostgreSQL or
  orchestration.
- The design meets the approved need without a generic rules platform.

### Negative

- Every expectation and material semantic revision requires explicit
  governance and maintenance.
- Authors must specify applicability, evidence, disposition, and evaluation
  semantics precisely.
- Consumers must handle four outcome states instead of a simple Boolean.
- Reproducibility requires disciplined control of semantic reference inputs.
- Collection and governed business-group evaluation may require more context
  than record evaluation.
- Persistence and operational reactions remain work for separately governed
  downstream capabilities.
- The lightweight model deliberately does not provide the flexibility or
  administration features of a generic enterprise rules engine.

## Rationale

A separate, lightweight governed Data Quality capability is the appropriate
middle ground for Repository 1. Embedding checks in transformation would blur
canonical correctness with business trustworthiness and couple evolving
quality policy to Milestone 4. Building a generic enterprise rules platform
would add registries, dynamic behavior, persistence, and operational complexity
without an approved need.

Stable versioned expectation contracts and normalized outcomes provide the
necessary governance, reproducibility, traceability, privacy, and downstream
interpretability while preserving the established ingestion, transformation,
persistence, and orchestration boundaries. This design records the approved
architecture without introducing new business-quality requirements or claiming
that Milestone 5 production implementation exists.
