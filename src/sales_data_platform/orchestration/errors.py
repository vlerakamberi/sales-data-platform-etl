"""Pipeline orchestration domain exceptions."""


class OrchestrationError(Exception):
    """Base exception for pipeline orchestration."""


class OrchestrationDomainError(OrchestrationError):
    """Base exception for invalid orchestration-domain operations."""


class InvalidLifecycleTransitionError(OrchestrationDomainError):
    """Raised when a requested lifecycle transition is not governed."""


class InvalidOrchestrationResultError(OrchestrationDomainError):
    """Raised when an orchestration result violates its domain invariants."""
