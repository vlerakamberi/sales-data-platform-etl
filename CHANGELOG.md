# Changelog

Meaningful project changes are recorded here. No release version or Git tag has
been assigned.

## Unreleased

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
