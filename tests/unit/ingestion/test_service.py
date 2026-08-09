import importlib
import logging
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import (
    BUILT_IN_REGISTRY,
    SourceContractKey,
)
from sales_data_platform.ingestion.csv_reader import ParsedCsvDocument
from sales_data_platform.ingestion.errors import (
    DiscoveryError,
    ParseError,
    SourceContractError,
)
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
    ValidatedBatch,
    ValidatedRecord,
)
from sales_data_platform.ingestion.service import ingest_source_file
from sales_data_platform.ingestion.validation import ValidationProvenance

service_module = importlib.import_module("sales_data_platform.ingestion.service")

CONTRACT_KEY = SourceContractKey("northstar.ecommerce_sales", 1)
CONTENT_HASH = ContentSha256("a" * 64)
SOURCE_ID = SourceIdentity("source-id")
RUN_ID = RunIdentity(UUID("12345678-1234-5678-1234-567812345678"))


def _settings(root: Path) -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=root)


def _record(provenance: ValidationProvenance) -> ValidatedRecord:
    return ValidatedRecord(
        {"customer_email": "sensitive@example.com"},
        RecordProvenance(
            contract_key=provenance.contract_key,
            source_identifier=provenance.source_identifier,
            content_sha256=provenance.content_sha256,
            source_id=provenance.source_id,
            run_id=provenance.run_id,
            row_number=2,
        ),
    )


def _patch_success_chain(
    monkeypatch: pytest.MonkeyPatch, source: Path, calls: list[object]
) -> None:
    contract = BUILT_IN_REGISTRY.resolve(
        CONTRACT_KEY.source_contract_id, CONTRACT_KEY.source_contract_version
    )

    class Registry:
        def resolve(self, contract_id: str, version: int):
            calls.append(("resolve", contract_id, version))
            return contract

    monkeypatch.setattr(service_module, "BUILT_IN_REGISTRY", Registry())
    monkeypatch.setattr(
        service_module,
        "discover_source_files",
        lambda key, settings: calls.append(("discover", key, settings)) or (source,),
    )
    monkeypatch.setattr(
        service_module,
        "normalize_relative_source_path",
        lambda path, root: (
            calls.append(("normalize", path, root)) or "ecommerce_sales/v1/orders.csv"
        ),
    )
    monkeypatch.setattr(
        service_module,
        "calculate_content_sha256",
        lambda path: calls.append(("hash", path)) or CONTENT_HASH,
    )
    monkeypatch.setattr(
        service_module,
        "build_source_identity",
        lambda key, relative, digest: (
            calls.append(("identity", key, relative, digest)) or SOURCE_ID
        ),
    )
    document = ParsedCsvDocument(("header",), ())
    monkeypatch.setattr(
        service_module,
        "parse_csv",
        lambda path: calls.append(("parse", path)) or document,
    )

    def validate(resolved_contract, parsed_document, provenance):
        calls.append(("validate", resolved_contract, parsed_document, provenance))
        return (_record(provenance),)

    monkeypatch.setattr(service_module, "validate_document", validate)


def test_service_delegates_in_required_order_and_builds_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "orders.csv"
    source.touch()
    calls: list[object] = []
    _patch_success_chain(monkeypatch, source, calls)

    batch = ingest_source_file(
        CONTRACT_KEY, source, settings=_settings(tmp_path), run_id=RUN_ID
    )

    assert type(batch) is ValidatedBatch
    assert batch.contract_key == CONTRACT_KEY
    assert batch.source_id is SOURCE_ID
    assert batch.run_id is RUN_ID
    assert batch.record_count == 1
    assert [call[0] for call in calls] == [
        "resolve",
        "discover",
        "normalize",
        "hash",
        "identity",
        "parse",
        "validate",
    ]
    validation_call = calls[-1]
    provenance = validation_call[3]
    assert provenance == ValidationProvenance(
        contract_key=CONTRACT_KEY,
        source_identifier="ecommerce_sales/v1/orders.csv",
        content_sha256=CONTENT_HASH,
        source_id=SOURCE_ID,
        run_id=RUN_ID,
    )


def test_omitted_run_identity_generates_uuid4_backed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "orders.csv"
    source.touch()
    calls: list[object] = []
    _patch_success_chain(monkeypatch, source, calls)
    generated_uuid = UUID("87654321-4321-8765-4321-876543218765")
    monkeypatch.setattr(service_module, "uuid4", lambda: generated_uuid)

    batch = ingest_source_file(CONTRACT_KEY, source, settings=_settings(tmp_path))

    assert batch.run_id == RunIdentity(generated_uuid)
    assert batch.source_id is SOURCE_ID


@pytest.mark.parametrize(
    "contract_key",
    [
        SourceContractKey("northstar.unknown", 1),
        SourceContractKey("northstar.ecommerce_sales", 2),
    ],
)
def test_contract_resolution_errors_propagate_unchanged(
    tmp_path: Path, contract_key: SourceContractKey
) -> None:
    with pytest.raises(SourceContractError) as captured:
        ingest_source_file(
            contract_key, tmp_path / "source.csv", settings=_settings(tmp_path)
        )

    expected = captured.value
    assert type(expected) is SourceContractError


def test_non_discovered_source_is_rejected_before_lower_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supplied = tmp_path / "supplied.csv"
    eligible = tmp_path / "eligible.csv"
    supplied.touch()
    eligible.touch()
    monkeypatch.setattr(
        service_module,
        "discover_source_files",
        lambda key, settings: (eligible,),
    )

    with pytest.raises(DiscoveryError, match="not an eligible"):
        ingest_source_file(CONTRACT_KEY, supplied, settings=_settings(tmp_path))


def test_caller_symlink_is_rejected_before_downstream_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller_alias = tmp_path / "alias.csv"
    eligible = tmp_path / "eligible.csv"
    eligible.touch()
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == caller_alias)
    monkeypatch.setattr(
        service_module,
        "discover_source_files",
        lambda key, settings: (eligible,),
    )
    downstream = {
        name: Mock(side_effect=AssertionError(f"{name} must not be called"))
        for name in (
            "normalize_relative_source_path",
            "calculate_content_sha256",
            "build_source_identity",
            "parse_csv",
            "validate_document",
        )
    }
    for name, function in downstream.items():
        monkeypatch.setattr(service_module, name, function)

    with pytest.raises(DiscoveryError, match="must not be a symlink"):
        ingest_source_file(CONTRACT_KEY, caller_alias, settings=_settings(tmp_path))

    assert all(function.call_count == 0 for function in downstream.values())


def test_physical_caller_symlink_alias_is_rejected_when_supported(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ecommerce_sales" / "v1" / "orders.csv"
    source.parent.mkdir(parents=True)
    source.write_text(
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        "ORDER-1,2026-08-09T18:30:00Z,,SKU-1,1,10.00,EUR\n",
        encoding="utf-8",
    )
    caller_alias = tmp_path / "alias.csv"
    try:
        caller_alias.symlink_to(source)
    except OSError as error:
        pytest.skip(f"environment cannot create symlinks: {error}")

    with pytest.raises(DiscoveryError, match="must not be a symlink"):
        ingest_source_file(CONTRACT_KEY, caller_alias, settings=_settings(tmp_path))


def test_controlled_failure_is_logged_safely_and_reraised_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "orders.csv"
    source.touch()
    calls: list[object] = []
    _patch_success_chain(monkeypatch, source, calls)
    failure = ParseError(
        "Malformed CSV",
        context={
            "failure_category": "malformed_csv",
            "raw_value": "sensitive@example.com",
        },
    )
    monkeypatch.setattr(
        service_module,
        "parse_csv",
        lambda path: (_ for _ in ()).throw(failure),
    )

    with caplog.at_level(logging.INFO), pytest.raises(ParseError) as captured:
        ingest_source_file(CONTRACT_KEY, source, settings=_settings(tmp_path))

    assert captured.value is failure
    assert "Ingestion failed" in caplog.text
    assert "sensitive@example.com" not in caplog.text


def test_success_lifecycle_logs_are_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "orders.csv"
    source.touch()
    calls: list[object] = []
    _patch_success_chain(monkeypatch, source, calls)

    with caplog.at_level(logging.INFO):
        ingest_source_file(
            CONTRACT_KEY, source, settings=_settings(tmp_path), run_id=RUN_ID
        )

    for message in (
        "Ingestion started",
        "Source selected",
        "Source identity established",
        "Parsing completed",
        "Validation completed",
        "Ingestion succeeded",
    ):
        assert message in caplog.text
    assert "sensitive@example.com" not in caplog.text


def test_unexpected_programming_error_is_not_relabelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "orders.csv"
    source.touch()
    monkeypatch.setattr(
        service_module,
        "discover_source_files",
        lambda key, settings: (_ for _ in ()).throw(RuntimeError("bug")),
    )

    with pytest.raises(RuntimeError, match="bug"):
        ingest_source_file(CONTRACT_KEY, source, settings=_settings(tmp_path))
