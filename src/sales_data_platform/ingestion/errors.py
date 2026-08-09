"""Controlled ingestion-domain failures."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


class IngestionError(Exception):
    """Base class for expected, controlled ingestion failures."""

    def __init__(
        self, message: str, *, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.context = MappingProxyType(dict(context or {}))


class DiscoveryError(IngestionError):
    """A controlled source-discovery failure."""


class SourceContractError(IngestionError):
    """A controlled source-contract definition or resolution failure."""


class ParseError(IngestionError):
    """A controlled source-parsing failure."""


class RecordValidationError(IngestionError):
    """A controlled source-record validation failure."""
