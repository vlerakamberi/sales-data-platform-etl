"""Source-contract validation for structurally parsed CSV documents."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sales_data_platform.ingestion.contracts import (
    FieldConstraint,
    FieldContract,
    PrimitiveFieldType,
    SourceContract,
    SourceContractKey,
)
from sales_data_platform.ingestion.csv_reader import ParsedCsvDocument, ParsedCsvRow
from sales_data_platform.ingestion.errors import RecordValidationError
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
    ValidatedRecord,
)

_DECIMAL_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}\Z")
_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


@dataclass(frozen=True, slots=True)
class ValidationProvenance:
    """Already-established file and run context used for validated records."""

    contract_key: SourceContractKey
    source_identifier: str
    content_sha256: ContentSha256
    source_id: SourceIdentity
    run_id: RunIdentity


def _error_context(
    contract: SourceContract,
    provenance: ValidationProvenance,
    failure_category: str,
    *,
    row_number: int | None = None,
    field_name: str | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "contract_id": contract.key.source_contract_id,
        "contract_version": contract.key.source_contract_version,
        "source_identifier": provenance.source_identifier,
        "failure_category": failure_category,
    }
    if row_number is not None:
        context["row_number"] = row_number
    if field_name is not None:
        context["field_name"] = field_name
    return context


def _parse_decimal(
    source_value: str,
    field: FieldContract,
    row: ParsedCsvRow,
    contract: SourceContract,
    provenance: ValidationProvenance,
) -> Decimal:
    if not _DECIMAL_PATTERN.fullmatch(source_value):
        raise RecordValidationError(
            "Source field is not a valid finite decimal",
            context=_error_context(
                contract,
                provenance,
                "invalid_decimal",
                row_number=row.row_number,
                field_name=field.name,
            ),
        )
    try:
        value = Decimal(source_value)
    except InvalidOperation as error:
        raise RecordValidationError(
            "Source field is not a valid finite decimal",
            context=_error_context(
                contract,
                provenance,
                "invalid_decimal",
                row_number=row.row_number,
                field_name=field.name,
            ),
        ) from error
    if not value.is_finite():
        raise RecordValidationError(
            "Source field is not a finite decimal",
            context=_error_context(
                contract,
                provenance,
                "non_finite_decimal",
                row_number=row.row_number,
                field_name=field.name,
            ),
        )
    return value


def _parse_timestamp(
    source_value: str,
    field: FieldContract,
    row: ParsedCsvRow,
    contract: SourceContract,
    provenance: ValidationProvenance,
) -> datetime:
    if not _TIMESTAMP_PATTERN.fullmatch(source_value):
        raise RecordValidationError(
            "Source field is not a valid ISO 8601 timestamp",
            context=_error_context(
                contract,
                provenance,
                "invalid_timestamp",
                row_number=row.row_number,
                field_name=field.name,
            ),
        )
    try:
        return datetime.fromisoformat(source_value)
    except ValueError as error:
        raise RecordValidationError(
            "Source field is not a valid ISO 8601 timestamp",
            context=_error_context(
                contract,
                provenance,
                "invalid_timestamp",
                row_number=row.row_number,
                field_name=field.name,
            ),
        ) from error


def _apply_constraints(
    value: str | Decimal | datetime,
    field: FieldContract,
    row: ParsedCsvRow,
    contract: SourceContract,
    provenance: ValidationProvenance,
) -> None:
    for constraint in field.constraints:
        valid = True
        if constraint is FieldConstraint.NON_NEGATIVE:
            valid = isinstance(value, Decimal) and value >= Decimal("0")
        elif constraint is FieldConstraint.POSITIVE:
            valid = isinstance(value, Decimal) and value > Decimal("0")
        elif constraint is FieldConstraint.UPPERCASE_CURRENCY_CODE:
            valid = isinstance(value, str) and bool(_CURRENCY_PATTERN.fullmatch(value))
        elif constraint is FieldConstraint.TIMEZONE_AWARE:
            valid = (
                isinstance(value, datetime)
                and value.tzinfo is not None
                and value.utcoffset() is not None
            )
        if not valid:
            raise RecordValidationError(
                "Source field violates its declared constraint",
                context=_error_context(
                    contract,
                    provenance,
                    constraint.value.lower(),
                    row_number=row.row_number,
                    field_name=field.name,
                ),
            )


def _validate_field(
    source_value: str,
    field: FieldContract,
    row: ParsedCsvRow,
    contract: SourceContract,
    provenance: ValidationProvenance,
) -> str | Decimal | datetime | None:
    if source_value == "":
        if field.nullable:
            return None
        raise RecordValidationError(
            "Non-nullable source field is empty",
            context=_error_context(
                contract,
                provenance,
                "non_nullable_empty",
                row_number=row.row_number,
                field_name=field.name,
            ),
        )

    if field.field_type is PrimitiveFieldType.STRING:
        value: str | Decimal | datetime = source_value
    elif field.field_type is PrimitiveFieldType.DECIMAL:
        value = _parse_decimal(source_value, field, row, contract, provenance)
    elif field.field_type is PrimitiveFieldType.TIMESTAMP:
        value = _parse_timestamp(source_value, field, row, contract, provenance)
    else:
        raise ValueError("Unsupported primitive field type")

    _apply_constraints(value, field, row, contract, provenance)
    return value


def validate_document(
    contract: SourceContract,
    document: ParsedCsvDocument,
    provenance: ValidationProvenance,
) -> tuple[ValidatedRecord, ...]:
    """Validate one parsed document against one already-resolved source contract."""

    if provenance.contract_key != contract.key:
        raise ValueError(
            "Validation provenance contract identity must match the contract"
        )

    declared_headers = {field.name for field in contract.fields}
    parsed_headers = set(document.headers)
    missing_headers = declared_headers - parsed_headers
    unexpected_headers = parsed_headers - declared_headers
    if missing_headers or unexpected_headers:
        context = _error_context(contract, provenance, "header_mismatch")
        context["missing_headers"] = tuple(sorted(missing_headers))
        context["unexpected_headers"] = tuple(sorted(unexpected_headers))
        raise RecordValidationError(
            "Parsed CSV headers do not match the source contract", context=context
        )

    if not document.rows:
        raise RecordValidationError(
            "Source document contains no data records",
            context=_error_context(contract, provenance, "no_data_records"),
        )

    header_positions = {name: index for index, name in enumerate(document.headers)}
    validated_records: list[ValidatedRecord] = []
    for row in document.rows:
        values = {
            field.name: _validate_field(
                row.values[header_positions[field.name]],
                field,
                row,
                contract,
                provenance,
            )
            for field in contract.fields
        }
        record_provenance = RecordProvenance(
            contract_key=provenance.contract_key,
            source_identifier=provenance.source_identifier,
            content_sha256=provenance.content_sha256,
            source_id=provenance.source_id,
            run_id=provenance.run_id,
            row_number=row.row_number,
        )
        validated_records.append(ValidatedRecord(values, record_provenance))

    return tuple(validated_records)
