"""Immutable ingestion-domain values and successful validated batches."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sales_data_platform.ingestion.contracts import SourceContractKey

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class ContentSha256:
    """A supplied lowercase hexadecimal SHA-256 digest."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256_PATTERN.fullmatch(self.value):
            raise ValueError(
                "Content SHA-256 must be 64 lowercase hexadecimal characters"
            )


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """A supplied deterministic identity for an immutable source artifact."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("Source identity must be a non-empty string")


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """A supplied correlation identity for one ingestion run."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("Run identity must be a UUID")


@dataclass(frozen=True, slots=True)
class RecordProvenance:
    """Source-oriented provenance supplied for a validated record."""

    contract_key: SourceContractKey
    source_identifier: str
    content_sha256: ContentSha256
    source_id: SourceIdentity
    run_id: RunIdentity
    row_number: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_identifier, str)
            or not self.source_identifier.strip()
        ):
            raise ValueError("Source identifier must be a non-empty string")
        if (
            not isinstance(self.row_number, int)
            or isinstance(self.row_number, bool)
            or self.row_number <= 0
        ):
            raise ValueError("Row number must be a positive integer")


@dataclass(frozen=True, slots=True)
class ValidatedRecord:
    """Immutable source-oriented typed values with record provenance."""

    values: Mapping[str, Any]
    provenance: RecordProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class ValidatedBatch:
    """An immutable, successful-only file-level batch."""

    contract_key: SourceContractKey
    source_id: SourceIdentity
    run_id: RunIdentity
    records: tuple[ValidatedRecord, ...]

    def __post_init__(self) -> None:
        records = tuple(self.records)
        for record in records:
            if record.provenance.contract_key != self.contract_key:
                raise ValueError("Batch and record contract identities must match")
            if record.provenance.source_id != self.source_id:
                raise ValueError("Batch and record source identities must match")
            if record.provenance.run_id != self.run_id:
                raise ValueError("Batch and record run identities must match")
        object.__setattr__(self, "records", records)

    @property
    def record_count(self) -> int:
        """Return the number of validated records in this batch."""

        return len(self.records)
