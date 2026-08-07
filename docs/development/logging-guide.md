# Logging guide

Logging behavior is owned by `sales_data_platform.logging.setup` and the
declarative topology in `config/logging.yaml`. Applications initialize it only
through:

```python
configure_logging(settings)
```

Callers pass validated `Settings`; the logging layer does not read environment
variables, dotenv, or reinterpret `LOG_DIRECTORY`.

## Console and named loggers

Console logging is configured after every successful initialization. Its format
contains timestamp, severity, logger name, and message. Application modules
should use named loggers:

```python
import logging

logger = logging.getLogger(__name__)
```

Approved runtime levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
The level comes from `settings.log_level`.

## Optional rotating-file logging

When `LOG_TO_FILE=false`, initialization configures only console logging. It
does not create the log directory or log file and attaches no file handler.

When `LOG_TO_FILE=true`, initialization creates `settings.log_directory` only
if required and writes to `sales_data_platform.log` using this contract:

| Property | Value |
| --- | --- |
| Handler | `logging.handlers.RotatingFileHandler` |
| Filename | `sales_data_platform.log` |
| `maxBytes` | `5242880` |
| `backupCount` | `3` |
| Encoding | `utf-8` |

This is a bounded local-development baseline. It is not a production retention
or compliance policy.

## Initialization and failure behavior

Repeated calls to `configure_logging(settings)` replace the configured topology
without accumulating handlers or duplicating messages. Imports alone do not
initialize logging or mutate the filesystem.

Missing or malformed YAML, missing required topology, invalid file-handler
configuration, directory-creation failure, or `dictConfig` failure raises a
clear logging setup error. There is no silent `basicConfig` or partial fallback.

## Safe logging

Log concise operational events. Never log secrets, passwords, tokens,
credentials, connection strings, complete settings objects, or full source-data
rows. Generated logs are local artifacts and must not be committed.
