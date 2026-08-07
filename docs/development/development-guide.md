# Development guide

Repository work follows the frozen Development Workflow Standard. This guide
summarizes its application here; it does not redefine or supersede governance.

## Engineering practices

- Agree architecture and dependency direction before implementation.
- Keep every change inside its approved scope; stop when a material decision is
  unresolved.
- Prefer validated configuration and centralized paths over hard-coded values.
- Preserve package responsibilities and one-way dependency boundaries.
- Reuse `common.paths`, `config.settings`, and `logging.setup`; future modules
  must not duplicate those services.
- Test externally observable success, failure, side-effect, and portability
  behavior appropriate to each change.
- Run Ruff lint and format checks and the complete Pytest suite before review.
- Update documentation when an approved change alters developer-facing truth.

## Git and commit discipline

- Start from the approved baseline and a clean working tree.
- Keep commits atomic, reviewable, and named with the approved message.
- Inspect staged paths and staged content before committing.
- Do not mix future milestone work into the current commit.
- Do not push until the commit has received explicit approval.

## Repository safety

Never commit passwords, tokens, credentials, connection strings, personal
paths, or a real `.env`. Do not commit generated data, log files, caches,
coverage files, virtual environments, or machine-specific artifacts. Use
isolated temporary paths in tests that write files.

Ingestion, transformation, data quality, orchestration, database access, and
monitoring remain unimplemented. Their future implementations must consume the
existing foundation rather than bypassing or reinterpreting it.
