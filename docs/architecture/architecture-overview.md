# Architecture overview

## Current scope

The implemented architecture is the Repository 1 application foundation built
through Commits 3–6. It provides path management, validated configuration,
logging, and a minimal executable bootstrap. It contains no implemented ETL or
database workflow.

## Dependency direction

```text
sales_data_platform.common.paths
                ↓
sales_data_platform.config.settings
                ↓
sales_data_platform.logging.setup
                ↓
sales_data_platform.__main__
```

Dependencies move in one direction:

1. `common.paths` derives `PROJECT_ROOT` from its module location and owns all
   canonical repository path semantics.
2. `config.settings` consumes `PROJECT_ROOT` and `LOGS_DIR`. It owns environment
   precedence, validation, types, and `LOG_DIRECTORY` resolution.
3. `logging.setup` consumes `CONFIG_DIR` and validated `Settings`. It owns YAML
   discovery, logging topology validation, runtime levels, handlers, rotation,
   idempotency, and logging failures.
4. `__main__.py` composes `Settings` and `configure_logging`, obtains a named
   logger, emits the startup event, and returns success.

Higher layers do not rediscover paths or reinterpret lower-layer values.
Imports do not initialize logging or create directories.

## Configuration and logging topology

The repository-root `config/logging.yaml` is the single declarative logging
topology. Runtime level and optional file destination enter through validated
settings. Console output is always configured after successful initialization.
File output, when enabled, uses a bounded rotating handler.

Failures in settings or logging initialization propagate and prevent successful
startup. There is no `basicConfig` or other fallback path.

## Package boundaries

The following packages currently contain only minimal `__init__.py` boundaries:

- `sales_data_platform.ingestion`
- `sales_data_platform.transformation`
- `sales_data_platform.quality`
- `sales_data_platform.orchestration`

They reserve architectural responsibilities for later approved milestones.
They contain no ingestion, transformation, quality, orchestration, scheduling,
retry, monitoring, or execution-history behavior.

## Planned evolution

Database access and pipeline stages may be introduced in later Repository 1
milestones while preserving this dependency direction. Downstream integration
with Repository 2 is future portfolio work. Neither capability is implemented
in the current architecture.
