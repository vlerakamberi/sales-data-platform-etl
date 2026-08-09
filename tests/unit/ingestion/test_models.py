from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
    ValidatedBatch,
    ValidatedRecord,
)

SHA256 = "a" * 64
RUN_UUID = UUID("12345678-1234-5678-1234-567812345678")


def _provenance(
    *,
    row_number: int = 2,
    contract_key: SourceContractKey | None = None,
    source_id: SourceIdentity | None = None,
    run_id: RunIdentity | None = None,
) -> RecordProvenance:
    return RecordProvenance(
        contract_key=contract_key or SourceContractKey("northstar.product_catalog", 1),
        source_identifier="northstar/product_catalog/catalog.csv",
        content_sha256=ContentSha256(SHA256),
        source_id=source_id or SourceIdentity("source-identity-value"),
        run_id=run_id or RunIdentity(RUN_UUID),
        row_number=row_number,
    )


def test_provenance_values_are_immutable_and_identities_are_distinct() -> None:
    provenance = _provenance()
    assert type(provenance.source_id) is SourceIdentity
    assert type(provenance.run_id) is RunIdentity
    assert provenance.source_identifier == "northstar/product_catalog/catalog.csv"
    with pytest.raises(FrozenInstanceError):
        provenance.row_number = 3  # type: ignore[misc]


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_malformed_sha256_text_is_rejected(digest: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ContentSha256(digest)


def test_valid_sha256_text_and_positive_row_number_are_accepted() -> None:
    provenance = _provenance(row_number=1)
    assert provenance.content_sha256.value == SHA256
    assert provenance.row_number == 1


@pytest.mark.parametrize("row_number", [0, -1])
def test_non_positive_row_number_is_rejected(row_number: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _provenance(row_number=row_number)


def test_validated_record_contains_immutable_source_values_and_provenance() -> None:
    source_values = {"sku": "SKU-1", "list_price": Decimal("10.50")}
    record = ValidatedRecord(source_values, _provenance())
    source_values["sku"] = "changed"
    assert record.values == {"sku": "SKU-1", "list_price": Decimal("10.50")}
    assert record.provenance.row_number == 2
    with pytest.raises(TypeError):
        record.values["sku"] = "changed"
    with pytest.raises(FrozenInstanceError):
        record.provenance = _provenance()  # type: ignore[misc]


def test_validated_batch_is_immutable_success_only_model() -> None:
    record = ValidatedRecord({"sku": "SKU-1"}, _provenance())
    source_records = [record]
    batch = ValidatedBatch(
        contract_key=SourceContractKey("northstar.product_catalog", 1),
        source_id=record.provenance.source_id,
        run_id=record.provenance.run_id,
        records=source_records,  # type: ignore[arg-type]
    )
    source_records.clear()
    assert batch.records == (record,)
    assert batch.record_count == 1
    assert not hasattr(batch, "rejected_records")
    assert not hasattr(batch, "partial_success")
    with pytest.raises(FrozenInstanceError):
        batch.source_id = SourceIdentity("changed")  # type: ignore[misc]
    with pytest.raises(TypeError):
        batch.records[0] = record  # type: ignore[index]


@pytest.mark.parametrize(
    ("provenance_overrides", "message"),
    [
        (
            {"contract_key": SourceContractKey("northstar.ecommerce_sales", 1)},
            "contract identities",
        ),
        ({"source_id": SourceIdentity("different-source")}, "source identities"),
        (
            {"run_id": RunIdentity(UUID("87654321-4321-8765-4321-876543218765"))},
            "run identities",
        ),
    ],
)
def test_validated_batch_rejects_incoherent_record_provenance(
    provenance_overrides: dict[str, object], message: str
) -> None:
    coherent = _provenance()
    record = ValidatedRecord({"sku": "SKU-1"}, _provenance(**provenance_overrides))
    with pytest.raises(ValueError, match=message):
        ValidatedBatch(
            contract_key=coherent.contract_key,
            source_id=coherent.source_id,
            run_id=coherent.run_id,
            records=(record,),
        )


def test_empty_validated_batch_remains_available() -> None:
    batch = ValidatedBatch(
        contract_key=SourceContractKey("northstar.product_catalog", 1),
        source_id=SourceIdentity("source-identity-value"),
        run_id=RunIdentity(RUN_UUID),
        records=(),
    )
    assert batch.record_count == 0


def test_domain_models_have_no_postgresql_concepts() -> None:
    record = ValidatedRecord({"sku": "SKU-1"}, _provenance())
    assert not hasattr(record, "database_id")
    assert not hasattr(record.provenance, "table_name")
