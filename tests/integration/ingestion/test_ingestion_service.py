import hashlib
import logging
from pathlib import Path
from uuid import UUID

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.errors import (
    DiscoveryError,
    ParseError,
    RecordValidationError,
    SourceContractError,
)
from sales_data_platform.ingestion.identity import build_source_identity
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RunIdentity,
    ValidatedBatch,
)
from sales_data_platform.ingestion.service import ingest_source_file

CONTRACT_KEY = SourceContractKey("northstar.ecommerce_sales", 1)
CUSTOMER_EMAIL = "private.customer@example.com"


def _settings(root: Path) -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=root)


def _eligible_source(root: Path, content: str, *, name: str = "orders.csv") -> Path:
    source = root / "ecommerce_sales" / "v1" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8", newline="")
    return source


def _valid_csv() -> str:
    return (
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        f"ORDER-1,2026-08-09T18:30:00Z,{CUSTOMER_EMAIL},SKU-1,2,10.50,EUR\n"
    )


def test_real_single_file_chain_returns_batch_with_deterministic_provenance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _eligible_source(tmp_path, _valid_csv())
    settings = _settings(tmp_path)

    with caplog.at_level(logging.INFO):
        batch = ingest_source_file(CONTRACT_KEY, source, settings=settings)

    raw_bytes = source.read_bytes()
    expected_hash = ContentSha256(hashlib.sha256(raw_bytes).hexdigest())
    expected_path = "ecommerce_sales/v1/orders.csv"
    expected_source_id = build_source_identity(
        CONTRACT_KEY, expected_path, expected_hash
    )
    assert type(batch) is ValidatedBatch
    assert batch.contract_key == CONTRACT_KEY
    assert batch.record_count == 1
    assert batch.source_id == expected_source_id
    record = batch.records[0]
    assert record.provenance.contract_key == CONTRACT_KEY
    assert record.provenance.source_identifier == expected_path
    assert record.provenance.content_sha256 == expected_hash
    assert record.provenance.source_id == expected_source_id
    assert record.provenance.run_id == batch.run_id
    assert record.provenance.row_number == 2
    assert "Ingestion succeeded" in caplog.text
    assert CUSTOMER_EMAIL not in caplog.text
    assert "ORDER-1" not in caplog.text


def test_replay_preserves_source_identity_but_generates_distinct_runs(
    tmp_path: Path,
) -> None:
    source = _eligible_source(tmp_path, _valid_csv())
    settings = _settings(tmp_path)

    first = ingest_source_file(CONTRACT_KEY, source, settings=settings)
    second = ingest_source_file(CONTRACT_KEY, source, settings=settings)

    assert first.source_id == second.source_id
    assert first.records[0].provenance.content_sha256 == (
        second.records[0].provenance.content_sha256
    )
    assert first.run_id != second.run_id


def test_supplied_run_identity_is_preserved(tmp_path: Path) -> None:
    source = _eligible_source(tmp_path, _valid_csv())
    supplied = RunIdentity(UUID("12345678-1234-5678-1234-567812345678"))

    batch = ingest_source_file(
        CONTRACT_KEY, source, settings=_settings(tmp_path), run_id=supplied
    )

    assert batch.run_id is supplied
    assert batch.records[0].provenance.run_id is supplied


def test_unknown_contract_fails_without_batch(tmp_path: Path) -> None:
    with pytest.raises(SourceContractError):
        ingest_source_file(
            SourceContractKey("northstar.unknown", 1),
            tmp_path / "orders.csv",
            settings=_settings(tmp_path),
        )


def test_non_eligible_source_fails_without_batch(tmp_path: Path) -> None:
    _eligible_source(tmp_path, _valid_csv())
    outside = tmp_path / "outside.csv"
    outside.write_text(_valid_csv(), encoding="utf-8")

    with pytest.raises(DiscoveryError):
        ingest_source_file(CONTRACT_KEY, outside, settings=_settings(tmp_path))


def test_malformed_csv_fails_without_batch(tmp_path: Path) -> None:
    source = _eligible_source(
        tmp_path,
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,currency_code\n"
        'ORDER-1,"unclosed\n',
    )

    with pytest.raises(ParseError):
        ingest_source_file(CONTRACT_KEY, source, settings=_settings(tmp_path))


def test_contract_invalid_csv_fails_without_batch_and_logs_no_raw_data(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _eligible_source(
        tmp_path,
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        f"ORDER-1,2026-08-09T18:30:00Z,{CUSTOMER_EMAIL},SKU-1,0,10.50,EUR\n",
    )

    with caplog.at_level(logging.INFO), pytest.raises(RecordValidationError):
        ingest_source_file(CONTRACT_KEY, source, settings=_settings(tmp_path))

    assert "Ingestion failed" in caplog.text
    assert CUSTOMER_EMAIL not in caplog.text
    assert "ORDER-1" not in caplog.text
