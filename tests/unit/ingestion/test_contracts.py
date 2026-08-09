from dataclasses import FrozenInstanceError

import pytest

from sales_data_platform.ingestion.contracts import (
    BUILT_IN_CONTRACTS,
    BUILT_IN_REGISTRY,
    FieldConstraint,
    FieldContract,
    PrimitiveFieldType,
    SourceContract,
    SourceContractKey,
    SourceContractRegistry,
)
from sales_data_platform.ingestion.errors import SourceContractError

EXPECTED_FIELDS = {
    "northstar.product_catalog": (
        "sku",
        "product_name",
        "category_code",
        "list_price",
        "unit_cost",
        "currency_code",
    ),
    "northstar.ecommerce_sales": (
        "order_number",
        "order_timestamp",
        "customer_email",
        "sku",
        "quantity",
        "unit_price",
        "currency_code",
    ),
    "northstar.retail_sales": (
        "receipt_number",
        "transaction_timestamp",
        "store_code",
        "terminal_id",
        "sku",
        "quantity",
        "unit_price",
        "currency_code",
    ),
}


def _fields(contract_id: str) -> dict[str, FieldContract]:
    contract = BUILT_IN_REGISTRY.resolve(contract_id, 1)
    return {field.name: field for field in contract.fields}


def test_registry_contains_exactly_the_three_approved_v1_contracts() -> None:
    assert tuple(
        contract.key.source_contract_id for contract in BUILT_IN_CONTRACTS
    ) == (
        "northstar.product_catalog",
        "northstar.ecommerce_sales",
        "northstar.retail_sales",
    )
    assert all(
        contract.key.source_contract_version == 1 for contract in BUILT_IN_CONTRACTS
    )
    assert len(BUILT_IN_REGISTRY.contracts) == 3


@pytest.mark.parametrize(("contract_id", "expected"), EXPECTED_FIELDS.items())
def test_contracts_declare_exact_external_field_sets(
    contract_id: str, expected: tuple[str, ...]
) -> None:
    contract = BUILT_IN_REGISTRY.resolve(contract_id, 1)
    assert tuple(field.name for field in contract.fields) == expected
    assert not hasattr(contract, "table_name")
    assert all(not hasattr(field, "column_name") for field in contract.fields)


def test_product_catalog_field_semantics() -> None:
    fields = _fields("northstar.product_catalog")
    assert all(field.header_required for field in fields.values())
    assert all(
        not fields[name].nullable for name in ("sku", "product_name", "category_code")
    )
    assert all(
        fields[name].nullable for name in ("list_price", "unit_cost", "currency_code")
    )
    assert fields["list_price"].constraints == (FieldConstraint.NON_NEGATIVE,)
    assert fields["unit_cost"].constraints == (FieldConstraint.NON_NEGATIVE,)
    assert fields["currency_code"].constraints == (
        FieldConstraint.UPPERCASE_CURRENCY_CODE,
    )


@pytest.mark.parametrize(
    "contract_id,timestamp_name,optional_name",
    [
        ("northstar.ecommerce_sales", "order_timestamp", "customer_email"),
        ("northstar.retail_sales", "transaction_timestamp", None),
    ],
)
def test_sales_contract_field_semantics(
    contract_id: str, timestamp_name: str, optional_name: str | None
) -> None:
    fields = _fields(contract_id)
    assert all(field.header_required for field in fields.values())
    assert fields[timestamp_name].field_type is PrimitiveFieldType.TIMESTAMP
    assert fields[timestamp_name].constraints == (FieldConstraint.TIMEZONE_AWARE,)
    assert fields["quantity"].constraints == (FieldConstraint.POSITIVE,)
    assert fields["unit_price"].constraints == (FieldConstraint.NON_NEGATIVE,)
    assert fields["currency_code"].constraints == (
        FieldConstraint.UPPERCASE_CURRENCY_CODE,
    )
    assert not fields["currency_code"].nullable
    if optional_name is not None:
        assert fields[optional_name].nullable
    assert all(
        not field.nullable for name, field in fields.items() if name != optional_name
    )


def test_registry_resolves_only_an_exact_known_pair() -> None:
    contract = BUILT_IN_REGISTRY.resolve("northstar.product_catalog", 1)
    assert contract is BUILT_IN_CONTRACTS[0]


def test_unknown_contract_id_is_rejected() -> None:
    with pytest.raises(SourceContractError, match="Unknown source contract ID"):
        BUILT_IN_REGISTRY.resolve("northstar.unknown", 1)


def test_unsupported_contract_version_is_rejected() -> None:
    with pytest.raises(
        SourceContractError, match="Unsupported source contract version"
    ):
        BUILT_IN_REGISTRY.resolve("northstar.product_catalog", 2)


def test_duplicate_registry_key_is_rejected() -> None:
    contract = BUILT_IN_CONTRACTS[0]
    with pytest.raises(SourceContractError, match="Duplicate source contract key"):
        SourceContractRegistry((contract, contract))


def test_contract_and_field_collections_are_immutable() -> None:
    contract = BUILT_IN_CONTRACTS[0]
    with pytest.raises(FrozenInstanceError):
        contract.key = SourceContractKey("changed", 1)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        contract.fields[0].nullable = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        contract.fields[0] = contract.fields[0]  # type: ignore[index]


def test_duplicate_field_names_are_rejected() -> None:
    field = FieldContract(
        "sku", PrimitiveFieldType.STRING, header_required=True, nullable=False
    )
    with pytest.raises(SourceContractError, match="field names must be unique"):
        SourceContract(SourceContractKey("northstar.duplicate", 1), (field, field))


@pytest.mark.parametrize("contract_id", ["", "   "])
def test_empty_contract_id_is_rejected(contract_id: str) -> None:
    with pytest.raises(SourceContractError, match="non-empty"):
        SourceContractKey(contract_id, 1)


@pytest.mark.parametrize("version", [0, -1])
def test_non_positive_contract_version_is_rejected(version: int) -> None:
    with pytest.raises(SourceContractError, match="positive integer"):
        SourceContractKey("northstar.product_catalog", version)
