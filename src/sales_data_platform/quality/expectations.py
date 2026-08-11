"""Explicit governed Northstar business-quality expectations."""

from collections import Counter

from sales_data_platform.quality.evaluation import (
    CanonicalQualityScope,
    QualityConditionDecision,
    QualityEvaluationUnavailable,
    QualityExpectationExecution,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationScope,
    QualityExpectationDefinition,
    QualityExpectationKey,
)
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
)

INCOHERENT_TRANSACTION_GROUP = "INCOHERENT_TRANSACTION_GROUP"

PRODUCT_SKU_UNIQUENESS_DEFINITION = QualityExpectationDefinition(
    key=QualityExpectationKey("DQ-PRODUCT-001", 1),
    description="Canonical product SKUs are unique within the governed collection",
    business_rationale="Each canonical SKU must identify only one product record",
    canonical_scope="CanonicalProduct",
    evaluation_scope=QualityEvaluationScope.COLLECTION,
    violation_disposition=QualityDisposition.BLOCKING,
)

SALES_TRANSACTION_CURRENCY_DEFINITION = QualityExpectationDefinition(
    key=QualityExpectationKey("DQ-SALES-001", 1),
    description="Canonical sales lines in one transaction use one currency",
    business_rationale="A transaction with mixed currencies is incoherent",
    canonical_scope="CanonicalSalesLine",
    evaluation_scope=QualityEvaluationScope.GROUP,
    violation_disposition=QualityDisposition.BLOCKING,
)


def _product_collection_applies(scope: CanonicalQualityScope) -> bool:
    _require_product_collection(scope)
    return True


def _evaluate_product_sku_uniqueness(
    scope: CanonicalQualityScope,
) -> QualityConditionDecision:
    products = _require_product_collection(scope)
    sku_counts = Counter(product.sku for product in products)
    duplicate_skus = {sku for sku, count in sku_counts.items() if count > 1}
    if not duplicate_skus:
        return QualityConditionDecision(True)

    first_duplicate_sku = next(
        product.sku for product in products if product.sku in duplicate_skus
    )
    affected_products = tuple(
        product for product in products if product.sku in duplicate_skus
    )
    return QualityConditionDecision(
        False,
        affected_scope_reference=f"product-sku:{first_duplicate_sku}",
        provenance=tuple(product.provenance for product in affected_products),
        evidence={
            "issue_code": "DUPLICATE_SKU",
            "duplicate_sku": first_duplicate_sku,
            "affected_count": len(affected_products),
        },
    )


def _sales_group_applies(scope: CanonicalQualityScope) -> bool:
    _require_sales_group(scope)
    return True


def _evaluate_sales_transaction_currency(
    scope: CanonicalQualityScope,
) -> QualityConditionDecision:
    lines = _require_sales_group(scope)
    if not lines:
        raise QualityEvaluationUnavailable(INCOHERENT_TRANSACTION_GROUP)

    transaction_identity = (
        lines[0].sales_channel_code,
        lines[0].source_transaction_number,
    )
    if any(
        (line.sales_channel_code, line.source_transaction_number)
        != transaction_identity
        for line in lines[1:]
    ):
        raise QualityEvaluationUnavailable(INCOHERENT_TRANSACTION_GROUP)

    if all(line.currency_code == lines[0].currency_code for line in lines[1:]):
        return QualityConditionDecision(True)

    channel, transaction_number = transaction_identity
    return QualityConditionDecision(
        False,
        affected_scope_reference=f"transaction:{channel}:{transaction_number}",
        provenance=tuple(line.provenance for line in lines),
        evidence={
            "issue_code": "MIXED_TRANSACTION_CURRENCY",
            "affected_count": len(lines),
        },
    )


def _require_product_collection(
    scope: CanonicalQualityScope,
) -> tuple[CanonicalProduct, ...]:
    if not isinstance(scope, tuple) or not all(
        isinstance(record, CanonicalProduct) for record in scope
    ):
        raise TypeError("DQ-PRODUCT-001 requires a CanonicalProduct collection")
    return scope


def _require_sales_group(
    scope: CanonicalQualityScope,
) -> tuple[CanonicalSalesLine, ...]:
    if not isinstance(scope, tuple) or not all(
        isinstance(record, CanonicalSalesLine) for record in scope
    ):
        raise TypeError("DQ-SALES-001 requires a CanonicalSalesLine group")
    return scope


PRODUCT_SKU_UNIQUENESS = QualityExpectationExecution(
    definition=PRODUCT_SKU_UNIQUENESS_DEFINITION,
    applicability=_product_collection_applies,
    condition=_evaluate_product_sku_uniqueness,
)

SALES_TRANSACTION_CURRENCY_CONSISTENCY = QualityExpectationExecution(
    definition=SALES_TRANSACTION_CURRENCY_DEFINITION,
    applicability=_sales_group_applies,
    condition=_evaluate_sales_transaction_currency,
)
