"""Atomic composition of the single-file ingestion boundaries."""

import logging
from pathlib import Path
from uuid import uuid4

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import (
    BUILT_IN_REGISTRY,
    SourceContractKey,
)
from sales_data_platform.ingestion.csv_reader import parse_csv
from sales_data_platform.ingestion.discovery import discover_source_files
from sales_data_platform.ingestion.errors import DiscoveryError, IngestionError
from sales_data_platform.ingestion.identity import (
    build_source_identity,
    calculate_content_sha256,
    normalize_relative_source_path,
)
from sales_data_platform.ingestion.models import RunIdentity, ValidatedBatch
from sales_data_platform.ingestion.validation import (
    ValidationProvenance,
    validate_document,
)

logger = logging.getLogger(__name__)


def _select_discovered_source(
    source_path: Path, eligible_sources: tuple[Path, ...]
) -> Path:
    if source_path.is_symlink():
        raise DiscoveryError(
            "Supplied source file must not be a symlink",
            context={
                "source_name": source_path.name,
                "failure_category": "source_selection",
            },
        )
    try:
        resolved_source = source_path.resolve(strict=True)
        matches = tuple(
            candidate
            for candidate in eligible_sources
            if candidate.resolve(strict=True) == resolved_source
        )
    except OSError as error:
        raise DiscoveryError(
            "Supplied source file cannot be accessed",
            context={
                "source_name": source_path.name,
                "failure_category": "source_selection",
            },
        ) from error
    if len(matches) != 1:
        raise DiscoveryError(
            "Supplied source file is not an eligible discovered artifact",
            context={
                "source_name": source_path.name,
                "failure_category": "source_selection",
            },
        )
    return matches[0]


def _log_controlled_failure(
    error: IngestionError, base_context: dict[str, object]
) -> None:
    context = dict(base_context)
    failure_category = error.context.get("failure_category")
    row_number = error.context.get("row_number")
    if isinstance(failure_category, str):
        context["failure_category"] = failure_category
    if isinstance(row_number, int):
        context["row_number"] = row_number
    logger.warning("Ingestion failed", extra=context)


def ingest_source_file(
    contract_key: SourceContractKey,
    source_path: Path,
    *,
    settings: Settings,
    run_id: RunIdentity | None = None,
) -> ValidatedBatch:
    """Ingest exactly one eligible source file into a validated source batch."""

    log_context: dict[str, object] = {
        "contract_id": contract_key.source_contract_id,
        "contract_version": contract_key.source_contract_version,
    }
    logger.info("Ingestion started", extra=log_context)

    try:
        contract = BUILT_IN_REGISTRY.resolve(
            contract_key.source_contract_id,
            contract_key.source_contract_version,
        )
        eligible_sources = discover_source_files(contract.key, settings)
        selected_source = _select_discovered_source(source_path, eligible_sources)
        source_identifier = normalize_relative_source_path(
            selected_source, settings.ingestion_source_root
        )
        log_context["source_identifier"] = source_identifier
        logger.info("Source selected", extra=log_context)

        content_sha256 = calculate_content_sha256(selected_source)
        source_id = build_source_identity(
            contract.key, source_identifier, content_sha256
        )
        log_context["source_id"] = source_id.value
        logger.info("Source identity established", extra=log_context)

        effective_run_id = run_id or RunIdentity(uuid4())
        log_context["run_id"] = str(effective_run_id.value)
        document = parse_csv(selected_source)
        logger.info("Parsing completed", extra=log_context)

        provenance = ValidationProvenance(
            contract_key=contract.key,
            source_identifier=source_identifier,
            content_sha256=content_sha256,
            source_id=source_id,
            run_id=effective_run_id,
        )
        records = validate_document(contract, document, provenance)
        log_context["record_count"] = len(records)
        logger.info("Validation completed", extra=log_context)

        batch = ValidatedBatch(
            contract_key=contract.key,
            source_id=source_id,
            run_id=effective_run_id,
            records=records,
        )
        logger.info("Ingestion succeeded", extra=log_context)
        return batch
    except IngestionError as error:
        _log_controlled_failure(error, log_context)
        raise
