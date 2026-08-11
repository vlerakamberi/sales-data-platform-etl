"""Local integration validation from governed source through Data Quality."""

from pathlib import Path
from uuid import UUID

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import RunIdentity, ValidatedBatch
from sales_data_platform.ingestion.service import ingest_source_file
from sales_data_platform.quality.evaluation import evaluate_quality
from sales_data_platform.quality.expectations import (
    PRODUCT_SKU_UNIQUENESS,
    SALES_TRANSACTION_CURRENCY_CONSISTENCY,
)
from sales_data_platform.quality.models import (
    QualityEvaluationResult,
    QualityOutcomeStatus,
)
from sales_data_platform.quality.summary import QualitySummary, summarize_quality
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalRecord,
    CanonicalSalesLine,
    TransformationBatchResult,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.service import transform_batch

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "ingestion" / "data" / "raw"
)
PRODUCT_KEY = SourceContractKey("northstar.product_catalog", 1)
ECOMMERCE_KEY = SourceContractKey("northstar.ecommerce_sales", 1)


def _settings() -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=FIXTURE_ROOT)


def _ingest_and_transform(
    contract_key: SourceContractKey,
    relative_source: Path,
    *,
    run_id: RunIdentity | None = None,
) -> tuple[ValidatedBatch, TransformationRuleSetKey, TransformationBatchResult]:
    batch = ingest_source_file(
        contract_key,
        FIXTURE_ROOT / relative_source,
        settings=_settings(),
        run_id=run_id,
    )
    ruleset = TransformationRuleSetKey(contract_key, 1)
    result = transform_batch(batch, ruleset=ruleset)
    assert result.failure_count == 0
    assert all(
        outcome.status is TransformationOutcomeStatus.SUCCESS
        for outcome in result.outcomes
    )
    return batch, ruleset, result


def _assert_provenance_continuity(
    batch: ValidatedBatch, canonical_records: tuple[CanonicalRecord, ...]
) -> None:
    assert len(canonical_records) == len(batch.records)
    assert all(
        canonical.provenance is validated.provenance
        for canonical, validated in zip(canonical_records, batch.records, strict=True)
    )


def _quality_semantics(result: QualityEvaluationResult) -> tuple[object, ...]:
    return tuple(
        (
            outcome.expectation_key,
            outcome.status,
            outcome.disposition,
            outcome.affected_scope_reference,
            dict(outcome.evidence),
        )
        for outcome in result.outcomes
    )


def _product_business_values(
    records: tuple[CanonicalProduct, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            record.sku,
            record.product_name,
            record.category_code,
            record.list_price,
            record.unit_cost,
            record.product_currency_code,
        )
        for record in records
    )


def test_product_source_to_quality_and_summary_composition() -> None:
    batch, ruleset, transformed = _ingest_and_transform(
        PRODUCT_KEY, Path("product_catalog/v1/products.csv")
    )
    products = tuple(
        record
        for record in transformed.successful_records
        if isinstance(record, CanonicalProduct)
    )
    assert len(products) == len(transformed.successful_records) == 2
    assert ruleset.transformation_version == 1
    _assert_provenance_continuity(batch, products)

    caller_collection = list(products)
    before_values = tuple(products)
    before_provenance = tuple(product.provenance for product in products)
    quality_result = evaluate_quality(
        caller_collection,
        evaluated_scope_reference="product-catalog:v1",
        expectations=(PRODUCT_SKU_UNIQUENESS,),
    )

    assert caller_collection == list(products)
    assert tuple(caller_collection) == before_values
    assert tuple(product.provenance for product in products) == before_provenance
    _assert_provenance_continuity(batch, products)
    (outcome,) = quality_result.outcomes
    assert outcome.expectation_key.expectation_id == "DQ-PRODUCT-001"
    assert outcome.expectation_key.expectation_version == 1
    assert outcome.status is QualityOutcomeStatus.SATISFIED
    assert outcome.provenance == ()

    assert summarize_quality(quality_result) == QualitySummary(
        total_evaluation_count=1,
        applicable_evaluation_count=1,
        satisfied_count=1,
        violation_count=0,
        blocking_violation_count=0,
        non_blocking_violation_count=0,
        not_applicable_count=0,
        evaluation_error_count=0,
    )


def test_ecommerce_source_to_explicit_transaction_group_quality() -> None:
    batch, ruleset, transformed = _ingest_and_transform(
        ECOMMERCE_KEY, Path("ecommerce_sales/v1/orders.csv")
    )
    sales_lines = tuple(
        record
        for record in transformed.successful_records
        if isinstance(record, CanonicalSalesLine)
    )
    assert len(sales_lines) == len(transformed.successful_records) == 2
    assert ruleset.transformation_version == 1
    _assert_provenance_continuity(batch, sales_lines)

    transaction_identity = ("ECOMMERCE", "WEB-1001")
    transaction_group = [
        line
        for line in sales_lines
        if (line.sales_channel_code, line.source_transaction_number)
        == transaction_identity
    ]
    assert len(transaction_group) == 1
    before_values = tuple(transaction_group)
    before_provenance = tuple(line.provenance for line in transaction_group)
    quality_result = evaluate_quality(
        transaction_group,
        evaluated_scope_reference="transaction:ECOMMERCE:WEB-1001",
        expectations=(SALES_TRANSACTION_CURRENCY_CONSISTENCY,),
    )

    assert tuple(transaction_group) == before_values
    assert transaction_group[0].sales_channel_code == "ECOMMERCE"
    assert transaction_group[0].source_transaction_number == "WEB-1001"
    assert transaction_group[0].currency_code == "EUR"
    assert tuple(line.provenance for line in transaction_group) == before_provenance
    assert transaction_group[0].provenance is batch.records[0].provenance
    (outcome,) = quality_result.outcomes
    assert outcome.expectation_key.expectation_id == "DQ-SALES-001"
    assert outcome.expectation_key.expectation_version == 1
    assert outcome.status is QualityOutcomeStatus.SATISFIED
    assert outcome.provenance == ()


def test_product_cross_layer_replay_has_equivalent_quality_semantics() -> None:
    first_run = RunIdentity(UUID("11111111-1111-1111-1111-111111111111"))
    second_run = RunIdentity(UUID("22222222-2222-2222-2222-222222222222"))
    first_batch, first_ruleset, first_transformed = _ingest_and_transform(
        PRODUCT_KEY,
        Path("product_catalog/v1/products.csv"),
        run_id=first_run,
    )
    second_batch, second_ruleset, second_transformed = _ingest_and_transform(
        PRODUCT_KEY,
        Path("product_catalog/v1/products.csv"),
        run_id=second_run,
    )
    first_products = tuple(
        record
        for record in first_transformed.successful_records
        if isinstance(record, CanonicalProduct)
    )
    second_products = tuple(
        record
        for record in second_transformed.successful_records
        if isinstance(record, CanonicalProduct)
    )

    assert first_batch.contract_key == second_batch.contract_key == PRODUCT_KEY
    assert first_ruleset.transformation_version == second_ruleset.transformation_version
    assert first_batch.source_id == second_batch.source_id
    assert first_batch.run_id != second_batch.run_id
    assert _product_business_values(first_products) == _product_business_values(
        second_products
    )
    _assert_provenance_continuity(first_batch, first_products)
    _assert_provenance_continuity(second_batch, second_products)

    first_quality = evaluate_quality(
        first_products,
        evaluated_scope_reference="product-catalog:v1",
        expectations=(PRODUCT_SKU_UNIQUENESS,),
    )
    second_quality = evaluate_quality(
        second_products,
        evaluated_scope_reference="product-catalog:v1",
        expectations=(PRODUCT_SKU_UNIQUENESS,),
    )

    assert _quality_semantics(first_quality) == _quality_semantics(second_quality)
    assert first_quality.outcomes[0].expectation_key.expectation_version == 1
    assert first_quality.outcomes[0].status is QualityOutcomeStatus.SATISFIED
