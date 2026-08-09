"""Controlled database infrastructure exceptions."""


class DatabaseInfrastructureError(RuntimeError):
    """Base error for PostgreSQL infrastructure failures."""


class DatabaseConfigurationError(DatabaseInfrastructureError):
    """Raised when a database operation lacks complete configuration."""


class DatabaseConnectionError(DatabaseInfrastructureError):
    """Raised when PostgreSQL connection establishment fails."""


class MigrationError(DatabaseInfrastructureError):
    """Base error for migration discovery, integrity, and execution failures."""


class MigrationDiscoveryError(MigrationError):
    """Raised when repository migration artifacts are invalid."""


class MigrationStateError(MigrationError):
    """Raised when database migration state is unknown or incompatible."""


class MigrationExecutionError(MigrationError):
    """Raised when an approved migration cannot be applied transactionally."""


class ReferenceDataConflictError(DatabaseInfrastructureError):
    """Raised when authoritative reference data conflicts with existing state."""


class ReferenceDataExecutionError(DatabaseInfrastructureError):
    """Raised when approved reference data cannot be applied transactionally."""


class DatabaseContractError(DatabaseInfrastructureError):
    """Raised when the Milestone 2 physical database contract has drifted."""
