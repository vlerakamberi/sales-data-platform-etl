# ADR-003

## Title

Canonical Transformation Boundary and Versioned Transformation Contracts

---

## Status

Accepted

---

## Context

Milestone 3 produces validated records whose representations retain the exact
meaning of their source contracts. Those source-oriented representations must
remain distinct from both the canonical Northstar business representation and
the PostgreSQL persistence representation established in Milestone 2.

Milestone 4 begins at the validated Milestone 3 ingestion boundary. Supported
source contracts need deterministic interpretation into shared Northstar
business concepts without leaking PostgreSQL surrogate identities, inventing
missing master data, or coupling transformation semantics to a source-contract
version. Every attempted validated record also needs an explicit, explainable
outcome while retaining its Milestone 3 provenance.

## Decision

Repository 1 will use exact source-contract-specific mappers to transform the
supported validated source representations into a small shared canonical
Northstar business model. The validated Milestone 3 source representation,
canonical Northstar business representation, and PostgreSQL persistence
representation remain separate contracts.

Canonical records use governed business keys and references rather than
PostgreSQL surrogate IDs. Shared transformation behavior consists of explicit,
deterministic normalization and business rules; no generalized rules framework
is introduced. Transformation does not use fuzzy or probabilistic identity
matching, fabricate missing master data, or manufacture PostgreSQL surrogate
identities. Direct PostgreSQL persistence is not part of the canonical
transformation core.

Every attempted validated record receives an explicit transformation outcome,
and its Milestone 3 provenance survives transformation. Transformation
semantics have an explicit transformation version identity independent of the
source-contract version. A material change to transformation semantics requires
a new transformation version.

## Alternatives Considered

### Direct Source-to-PostgreSQL Mapping

Map each validated source representation directly into PostgreSQL tables. This
was rejected because it couples source interpretation to persistence structure
and leaks relational and surrogate-identity concerns into transformation.

### Generic Dictionary-Based Canonical Representation

Represent canonical records as generic dictionaries. This was rejected because
it weakens explicit business contracts and makes deterministic transformation
behavior harder to review and test.

### Complete Canonical Clone of All Nine PostgreSQL Entities

Clone the complete Milestone 2 persistence model as the canonical business
representation. This was rejected because the governed sources do not provide
authoritative information for every entity and because a persistence-shaped
clone would blur the canonical and PostgreSQL boundaries.

### Source-Specific Transformed Models Without a Shared Business Representation

Retain a separate transformed model for each source. This was rejected because
Northstar business concepts would remain fragmented and common semantics could
diverge across sources.

### Explicit Source-Specific Mappers Into a Small Shared Canonical Business Model With a Separate Persistence Boundary

Use exact source-contract-specific mappers to produce a small shared canonical
Northstar business model while governing PostgreSQL persistence separately.
This alternative was selected.

## Consequences

### Positive

- Source, canonical, and persistence contracts are cleanly separated.
- Source-contract evolution remains explicit.
- Transformation is deterministic and independently testable.
- PostgreSQL surrogate identity does not leak into canonical records.
- Customer, store, and category identity is not fabricated.
- Milestone 3 provenance remains continuous through transformation.
- Transformation-rule evolution is explicit and explainable.
- Future execution or storage evolution need not redefine Northstar business
  meaning.

### Negative

- An additional canonical representation exists between ingestion and
  persistence.
- Explicit mapping code is required for each supported source contract and
  version.
- PostgreSQL loading requires a separately governed boundary.
- Some source references intentionally remain unresolved where authoritative
  information is unavailable.

## Rationale

Explicit source-specific mapping into a small shared canonical business model
provides the required deterministic interpretation while preserving the frozen
Milestone 1–3 contracts. It gives Northstar business meaning an explicit home
that is neither a volatile source layout nor a PostgreSQL table contract.

Independent transformation versioning makes material semantic evolution
reviewable without conflating it with source-contract evolution. Keeping
surrogate identities, master-data invention, fuzzy matching, and direct loading
outside the transformation core preserves a clear and independently testable
boundary.
