# Configuration guide

Configuration is owned by `sales_data_platform.config.settings.Settings`, built
with Pydantic and pydantic-settings.

## Active environment variables

| Variable | Type and accepted values | Safe default |
| --- | --- | --- |
| `APPLICATION_ENV` | `development`, `test`, or `production` | `development` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` | `INFO` |
| `LOG_TO_FILE` | Boolean | `false` |
| `LOG_DIRECTORY` | `pathlib.Path` | Centralized `LOGS_DIR` |
| `INGESTION_SOURCE_ROOT` | `pathlib.Path` | Centralized `RAW_DATA_DIR` |
| `DATABASE_HOST` | Non-empty string or omitted | Not configured |
| `DATABASE_PORT` | Integer from `1` through `65535` or omitted | Not configured |
| `DATABASE_NAME` | Non-empty string or omitted | Not configured |
| `DATABASE_USERNAME` | Non-empty string or omitted | Not configured |
| `DATABASE_PASSWORD` | Non-empty secret string or omitted | Not configured |

The five `DATABASE_*` values are one optional group. Database operations require
all five; supplying only part of the group is rejected. Generic application
startup may omit the entire group. Keep real credentials only in the ignored
`.env` or process environment and never commit them.

## Precedence

Settings use this precedence, from highest to lowest:

```text
process environment
        >
repository-root .env
        >
safe defaults
```

The real `.env` is local and ignored. `.env.example` contains only safe active
settings.

## `LOG_DIRECTORY` contract

- The Python type is `pathlib.Path`.
- The default is centralized `LOGS_DIR` from `common.paths`.
- A relative override resolves against centralized `PROJECT_ROOT`.
- An absolute override remains absolute.
- `Path.cwd()` has no effect on its meaning.
- Normalization occurs inside the settings layer.
- Settings loading does not create the directory.
- Consumers receive the already-resolved path and must not reinterpret it.

The logging layer creates the directory only when file logging is enabled and
initialization requires it.

## `INGESTION_SOURCE_ROOT` contract

- It is the root used to discover governed ingestion source directories and
  files.
- The Python type is `pathlib.Path`.
- The default is centralized `RAW_DATA_DIR` (`data/raw`).
- A relative override resolves against centralized `PROJECT_ROOT`.
- An absolute override remains absolute.
- `Path.cwd()` has no effect on its meaning.
- Settings loading does not require or create the directory.

Set `INGESTION_SOURCE_ROOT` through the process environment or local `.env` when
source data is stored outside the safe repository default. For example:

```text
INGESTION_SOURCE_ROOT=data/raw
```
