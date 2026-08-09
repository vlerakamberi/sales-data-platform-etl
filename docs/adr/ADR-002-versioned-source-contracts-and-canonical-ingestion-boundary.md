# ADR-002

## Title

Versioned Source Contracts and Canonical Ingestion Boundary

---

## Status

Accepted

---

## Context

Northstar Retail Group receives external data whose layouts and semantics vary
by source. Those external interfaces must evolve without becoming aliases for
the canonical PostgreSQL persistence contract established in Milestone 2.
Milestone 3 therefore requires a controlled, deterministic boundary that can
identify, parse, and validate supported source data before later canonical
transformation and persistence.

External schemas are source-specific interfaces. Each supported source type
needs an explicit logical contract identifier and immutable version so that a
source file can be interpreted against a known contract. Incompatible source
schema evolution cannot silently change an accepted contract; it requires a
new version.

The ingestion boundary must preserve validated source data and sufficient
provenance for deterministic replay while keeping source identity distinct from
execution or run identity. It must remain independently testable without
PostgreSQL and must not perform relational resolution, surrogate-key
assignment, database-dependent canonicalization, business enrichment,
canonical persistence mapping, or derived business metrics.

The governing flow is:

```text
External source-specific schema
→ Explicit versioned source contract
→ Common ingestion boundary
→ Canonical downstream processing
→ Downstream PostgreSQL persistence
```

## Decision

Repository 1 will use explicit, immutable, versioned source contracts that feed
a common ingestion boundary.

Every supported source type will have a logical source-contract identifier and
an explicit version. A contract version is immutable after acceptance.
Incompatible external schema evolution requires a new contract version;
unknown contracts and versions fail explicitly.

Discovery will be deterministic and constrained to approved source locations
and supported source files. Parsing will be deterministic. Parsing and
source-conformance validation occur before any canonical transformation.
Validation remains source-local and may establish structural conformance,
required fields, primitive parsing and types, and approved source-local value
rules.

Successful ingestion preserves the validated source interpretation together
with provenance. Deterministic replay means that the same supported source
contract and the same immutable source content produce an equivalent validated
interpretation and stable source identity. Source identity and execution/run
identity remain distinct.

Source identity is conceptually based on the contract identifier, contract
version, normalized approved source identifier, and source-content SHA-256.
Provenance may additionally include row or source position and a run or
correlation identifier. Provenance is ingestion metadata and does not require
changes to the nine approved Milestone 2 business tables.

File-level ingestion is atomic: a contract-breaking error invalidates the
complete file-level ingestion batch. Partial-row success, quarantine, and
dead-letter handling are not part of this decision. File-level atomicity does
not imply exactly-once persistence or a database transaction.

Ingestion will use a controlled failure taxonomy covering discovery failures,
source-contract failures, parse failures, and record-validation failures.
Unexpected system and programming failures remain distinct. Observability will
reuse centralized logging and provide useful source, contract, run, provenance,
and error context without logging raw complete records by default or exposing
source data unnecessarily.

The ingestion boundary performs no cross-entity relational resolution,
PostgreSQL lookup, surrogate-key assignment, database-dependent
canonicalization, business enrichment, canonical persistence mapping,
aggregation, or derived business metric. PostgreSQL persistence remains a
downstream concern, and ingestion core tests remain PostgreSQL-independent.

## Alternatives Considered

### Direct Source-to-Database-Schema Mapping

Map each external field directly to the Milestone 2 PostgreSQL schema.

Positive consequences include an apparently short path to persistence and
fewer visible intermediate concepts for a single stable source. Negative
consequences are tight coupling between volatile external layouts and canonical
persistence, premature relational resolution and surrogate-key concerns,
reduced replay clarity, and pressure to change canonical tables when sources
evolve. This alternative was rejected.

### Generic Schema-Less Ingestion

Accept arbitrary source records without explicit versioned contracts.

Positive consequences include low initial onboarding effort and flexibility to
retain unfamiliar fields. Negative consequences include ambiguous semantics,
late and inconsistent failures, weak deterministic replay, poor source
conformance guarantees, and difficulty distinguishing supported evolution from
accidental drift. This alternative was rejected.

### Explicit Versioned Source Contracts Feeding a Common Ingestion Boundary

Define source-specific immutable contract versions and converge their validated
outputs at one conceptual ingestion boundary.

Positive consequences include explicit compatibility, deterministic parsing
and replay, controlled evolution, source-local validation, strong provenance,
and separation from PostgreSQL persistence. Negative consequences include the
need to govern contract versions, maintain source-specific definitions, and
reject previously unseen layouts until they are explicitly approved. This
alternative was selected.

## Consequences

### Positive

- External interfaces and canonical persistence remain decoupled.
- Supported schema evolution is explicit, immutable, and auditable.
- Parsing, discovery, validation, identity, and replay have deterministic
  meanings.
- File-level failures cannot yield misleading partial-row success.
- Provenance survives without modifying the approved business tables.
- Controlled failure categories and safe observability improve diagnosis.
- Multiple source types can feed one downstream boundary without pretending to
  share an external layout.
- Ingestion and its core tests remain independent of PostgreSQL.

### Negative

- Each supported source and incompatible evolution requires explicit contract
  governance.
- Strict source conformance rejects unexpected headers, layouts, and versions
  rather than accepting them opportunistically.
- Relational resolution, canonical mapping, enrichment, and persistence must
  occur in later downstream stages.
- File-level atomicity deliberately provides no partial success, quarantine,
  dead-letter, or exactly-once persistence behavior.

## Rationale

Explicit versioned source contracts feeding a common ingestion boundary best
satisfy Milestone 3 because they make external compatibility visible and
testable while preserving a stable separation from canonical persistence.
They support deterministic discovery, parsing, source identity, provenance,
replay, and controlled failure without requiring PostgreSQL lookups or changes
to the Milestone 2 schema.

The selected architecture keeps validation at the source boundary and defers
canonical transformation, relational resolution, surrogate keys, business
enrichment, and persistence to their proper downstream responsibilities. It
therefore provides the required ingestion control without coupling volatile
source layouts to PostgreSQL or prematurely implementing later milestones.
