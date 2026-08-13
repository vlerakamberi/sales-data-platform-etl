# Changelog

Meaningful project changes are recorded here. No release version or Git tag has
been assigned.

## Unreleased

### Milestone 8 — Production Readiness & Portfolio Showcase

- Completed the final implementation validation matrix as closure-readiness
  evidence: 4 readiness-contract tests, 44 configuration tests, 103
  orchestration unit tests, and all 16 required PostgreSQL-backed orchestration
  integration scenarios passed without failures or skips.
- Confirmed the full repository suite passes with 607 passed, 4 inherited
  Windows symlink-privilege skips, and 91% total coverage.
- Confirmed Ruff lint and formatting, dependency health, database-free startup,
  orchestration CLI help, and repository-controlled documentation/reference
  integrity checks pass.
- Prepared Milestone 8 implementation and validation evidence for formal
  Governance closure review. Formal Milestone 8 closure and Formal Repository 1
  Final Validation / Closure have not been performed; Repository 1 remains not
  complete.

### Milestone 7 — Testing

- Established the authoritative layered testing strategy and inherited
  regression-evidence baseline.
- Added targeted integrated-system validation for governed Data Quality
  `BLOCKED`, technical `FAILED`, and deterministic replay scenarios.
- Completed successful final repository regression, coverage, quality,
  dependency, startup, orchestration CLI, PostgreSQL safeguard, and Git-hygiene
  validation while Repository 1 remains in active development and is not
  complete.

### Milestone 6 — Pipeline Orchestration

- Completed and validated deterministic local coordination of ingestion,
  canonical transformation, and business Data Quality evaluation.
- Added durable PostgreSQL pipeline and stage execution history with governed
  lifecycle states, controlled failure details, and predecessor correlation.
- Added controlled manual/local invocation with safe operator output and
  distinct successful, blocked, failed, and argument-error outcomes.
- Added immutable pipeline and stage runtime metrics derived only from
  authoritative persisted timestamps.
- Completed guarded real-PostgreSQL orchestration validation and full
  repository regression, quality, dependency, startup, and Git-hygiene checks.
- Completed successful final validation and closed Milestone 6 while Repository
  1 remains in active development and is not complete.

### Milestone 5 — Data Quality Framework

- Completed and validated governed, versioned Data Quality contracts with
  deterministic applicability and evaluation behavior.
- Added structured `SATISFIED`, `VIOLATED`, `NOT_APPLICABLE`, and
  `EVALUATION_ERROR` outcomes and explicit quality summary counts.
- Added the governed Northstar product-SKU uniqueness and transaction-currency
  consistency expectations with `BLOCKING` policy metadata.
- Validated local ingestion → canonical transformation → Data Quality
  composition with continuous authoritative provenance.
- Confirmed equivalent governed semantic inputs under the same expectation
  version produce equivalent semantic quality results while traceability-only
  run identity may differ.
- Confirmed Data Quality evaluation remains database-independent and
  orchestration-independent; persistent results and pipeline control remain
  outside the Milestone 5 framework.
- Completed successful final validation and closed Milestone 5.

### Milestone 4 — Data Transformation Layer

- Completed and validated deterministic canonical transformation for the
  governed product-catalog, ecommerce-sales, and retail-sales `v1` contracts.
- Validated explicit ordered outcomes, provenance continuity, transformation
  ruleset identity, deterministic replay, integral quantities, and exact
  `Decimal` line-amount derivation.
- Confirmed the transformation boundary remains PostgreSQL-independent and
  ends at the persistence-neutral `TransformationBatchResult`.
- Preserved healthy ingestion, guarded PostgreSQL, and application-startup
  regression validation without introducing transformation persistence.

### Milestone 3 — Data Ingestion Layer

- Completed and validated immutable versioned source contracts for product
  catalog, ecommerce sales, and retail sales inputs.
- Added deterministic constrained source discovery, exact raw-byte SHA-256,
  and deterministic `SourceIdentity` calculation.
- Added deterministic structural CSV parsing and source-contract validation
  with record provenance and separate source and run identities.
- Added a file-level atomic ingestion service that returns an immutable
  `ValidatedBatch` only after complete source validation.
- Added safe centralized ingestion observability without logging complete raw
  records by default.
- Validated the PostgreSQL-independent Milestone 3 ingestion core and local
  end-to-end boundary while preserving Milestone 1 and Milestone 2 regression
  contracts.

### Milestone 2 — Database Design & Implementation

- Completed and validated the Repository 1 PostgreSQL database foundation.
- Accepted the SQL-first ordered/versioned immutable migration strategy in
  ADR-001.
- Added validated optional PostgreSQL configuration and explicit Psycopg
  connection infrastructure.
- Added V001 migration metadata, V002 core relational schema, and V003 approved
  indexes with ordered execution, provenance, and SHA-256 integrity checks.
- Added deterministic `ECOMMERCE` and `RETAIL` sales-channel reference data with
  idempotent reconciliation and explicit conflict rejection.
- Added read-only validation of the exact physical schema, explicit indexes,
  and final sales-channel reference-data contract.
- Added guarded real-PostgreSQL coverage for migration regression, schema drift,
  relational integrity, monetary constraints, and optional relationships.
- Completed final Milestone 2 installation, test, coverage, Ruff, dependency,
  startup, security, and Git-hygiene validation.

### Milestone 1 — Project Foundation

- Completed and validated the Repository 1 project foundation.
- Verified clean-clone setup and reproducible development installation using `python -m pip install -e ".[dev]"`.
- Validated centralized path management, application configuration, logging, and application bootstrap contracts.
- Confirmed the full automated test suite, coverage execution, Ruff checks, and dependency integrity checks pass.
- Confirmed repository documentation, Git hygiene, security controls, and generated-artifact handling satisfy the Milestone 1 Definition of Done.

### Added

- Python 3.13 project metadata, dependency declarations, and development tools.
- Centralized repository path management.
- Validated application settings with environment and dotenv support.
- Centralized console and optional rotating-file logging.
- A minimal executable package bootstrap.
- Side-effect-free package boundaries for future pipeline capabilities.
- Unit and integration coverage for the implemented foundation.
- Project-foundation architecture and development documentation.
