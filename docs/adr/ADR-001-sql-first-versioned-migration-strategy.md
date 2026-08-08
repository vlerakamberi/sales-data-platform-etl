# ADR-001

## Title

SQL-First Versioned Migration Strategy for Repository 1

---

## Status

Accepted

---

## Context

Repository 1, `sales-data-platform-etl`, requires a deterministic and auditable mechanism for creating and evolving its PostgreSQL relational schema.

Milestone 2 — Database Design & Implementation establishes PostgreSQL as the Repository 1 persistence platform and SQL as the authoritative relational contract.

The database must support:

- reproducible creation from a clean PostgreSQL database;
- controlled evolution as later Repository 1 milestones introduce approved schema changes;
- traceability of schema history;
- deterministic migration ordering;
- detection of modified previously applied migrations;
- rejection of unknown or incompatible migration states;
- explicit schema-drift detection;
- deterministic reference-data initialization;
- idempotent re-execution without silently accepting an incompatible database state.

The migration mechanism must preserve the Milestone 1 configuration, path-management, logging, error-handling, and application-bootstrap contracts.

Repository 1 also needs to demonstrate explicit SQL and relational database engineering rather than hiding schema ownership behind an ORM or migration framework without a demonstrated requirement.

The schema-evolution strategy is an architectural decision because it determines the authoritative source of database state and governs how all subsequent Repository 1 schema changes are represented.

---

## Decision

Repository 1 will use **SQL-first ordered/versioned migrations** as its authoritative PostgreSQL schema-evolution strategy.

Version-controlled SQL migration artifacts are the authoritative source of schema history and database state.

Migrations will be:

- explicitly ordered;
- versioned;
- deterministic;
- stored in source control;
- applied sequentially;
- immutable after they have been accepted into an authoritative repository baseline.

A clean PostgreSQL database will reach the expected schema state by applying the complete authoritative migration sequence in order.

An existing database at a recognized earlier migration state will advance by applying only the valid outstanding migrations in order.

An existing database already at the expected state will require no schema mutation after its migration provenance and integrity have been successfully validated.

Repository 1 will maintain migration metadata sufficient to determine which migrations have been applied and to verify the integrity of previously applied migration artifacts.

If a previously applied migration no longer matches its authoritative repository artifact, migration validation will fail.

If the database contains an unknown or otherwise incompatible migration state, migration validation will fail.

Physical schema validation will supplement migration provenance so that incompatible schema drift is not silently accepted merely because expected database objects or migration identifiers exist.

Idempotency therefore means that repeated setup against an already-correct database confirms the exact expected state without destructive or duplicate mutation. It does not mean suppressing DDL errors or indiscriminately using constructs such as `IF NOT EXISTS`.

`IF NOT EXISTS` or equivalent conditional DDL may only be used where its behavior cannot conceal an incompatible schema state.

Deterministic reference data will be version controlled and managed consistently with the schema-evolution contract. Reapplying already-correct reference data must be safe, while conflicting reference values must fail validation rather than being silently overwritten.

SQL remains authoritative for:

- tables;
- columns;
- primary keys;
- foreign keys;
- uniqueness constraints;
- check constraints;
- indexes;
- schema evolution.

Python may provide infrastructure-only support for:

- reading validated database configuration;
- establishing PostgreSQL connections;
- executing ordered migrations;
- managing supported transactional boundaries;
- reading and validating migration metadata;
- validating migration integrity;
- performing schema verification;
- emitting centralized logs;
- handling infrastructure-level failures.

Python classes, ORM metadata, or generalized persistence abstractions will not become an alternative source of schema truth.

Later Repository 1 schema changes must be represented through new approved migrations rather than modification of previously accepted migrations.

---

## Alternatives Considered

### Declarative Recreate-from-DDL

Maintain a current declarative schema definition and recreate the database from that definition when required.

This approach provides simple clean-database initialization and makes the current desired schema easy to inspect.

It was not selected as the authoritative schema-evolution strategy because it does not provide a sufficiently strong historical upgrade path once Repository 1 begins evolving persisted database state. It can encourage destructive recreation, weakens visibility into how the schema changed over time, and becomes less suitable as subsequent milestones introduce approved schema changes.

A current-state schema representation may be used in the future for documentation or validation if justified, but it must not replace the authoritative migration history.

### Migration Framework Such as Alembic

Use a dedicated migration framework to manage migration versions, execution, and database-state tracking.

This provides mature migration tooling and can be particularly valuable when SQLAlchemy or another ORM owns the application data model.

It was not selected because Repository 1 has no approved requirement for ORM-first schema ownership. Introducing Alembic at this stage would add framework and dependency complexity without a demonstrated architectural need and could create ambiguity between SQL and ORM metadata as the authoritative relational contract.

A migration framework may be reconsidered only through a future approved architectural decision if Repository 1 requirements materially outgrow the selected SQL-first strategy.

### Ordered/Versioned SQL Migrations

Maintain explicit, ordered, version-controlled SQL migrations and validate their execution history and integrity.

This approach was selected because it preserves SQL as the visible relational contract, provides an auditable schema history, supports deterministic creation and forward evolution, avoids unnecessary framework coupling, and aligns with the scope and complexity of Repository 1.

---

## Consequences

### Positive

- SQL remains explicit and recruiter-visible.
- The repository contains a complete and auditable history of database evolution.
- Clean database creation is deterministic.
- Existing valid databases can advance through controlled forward migrations.
- Previously accepted schema history is protected from silent modification.
- Migration provenance can be validated.
- Schema drift can be detected and rejected.
- Database idempotency has an explicit and testable meaning.
- Reference-data initialization follows deterministic semantics.
- The approach avoids unnecessary ORM and migration-framework complexity.
- Future Repository 1 milestones receive a controlled mechanism for approved schema changes.
- The strategy integrates with the existing Milestone 1 configuration, logging, path-management, testing, and error-handling foundations.

### Negative

- Repository 1 must implement and maintain disciplined migration execution and validation behavior.
- Migration authors must understand forward-only schema evolution.
- Migration metadata and integrity verification must be maintained explicitly.
- Complex future schema changes may require more manually authored SQL than a dedicated migration framework.
- Incorrectly designed accepted migrations cannot simply be edited after the fact; corrections require subsequent migrations.
- The project must test both migration provenance and resulting physical schema state to provide adequate drift protection.

---

## Rationale

SQL-first ordered/versioned migrations provide the best balance of correctness, transparency, reproducibility, maintainability, and scope discipline for Repository 1.

Repository 1 is specifically intended to demonstrate professional local ETL and PostgreSQL engineering. Keeping SQL authoritative makes relational design decisions directly inspectable and prevents an unnecessary ORM or migration framework from obscuring the database contract.

The approach supports both clean initialization and controlled forward evolution while preserving an auditable history of architectural database changes.

It also establishes stronger semantics than a recreate-from-DDL model for future Repository 1 milestones because an existing database can be validated and advanced without assuming that destructive recreation is acceptable.

Migration provenance and integrity verification prevent previously applied migrations from being silently rewritten, while physical schema validation protects against database state that diverges from the approved contract.

The strategy satisfies the portfolio engineering principles of reproducibility, idempotency, explicit configuration, testing, observability, error handling, and architecture-before-implementation without introducing infrastructure that Repository 1 does not currently require.

For these reasons, SQL-first ordered/versioned immutable migrations are the approved Repository 1 schema-evolution strategy.
