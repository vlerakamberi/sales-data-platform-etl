"""Tests for explicit transformation business rules."""

from decimal import Decimal

import pytest

from sales_data_platform.transformation.rules import (
    TransformationRuleViolation,
    derive_line_amount,
    require_integral_quantity,
    require_product_monetary_consistency,
)


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (Decimal("1"), 1),
        (Decimal("2.0"), 2),
        (Decimal("3.000"), 3),
    ],
)
def test_integral_decimal_quantities_are_converted_exactly(
    quantity: Decimal, expected: int
) -> None:
    assert require_integral_quantity(quantity) == expected


@pytest.mark.parametrize("quantity", [Decimal("1.5"), Decimal("0.25")])
def test_fractional_quantities_are_rejected_without_rounding(
    quantity: Decimal,
) -> None:
    with pytest.raises(TransformationRuleViolation, match="exact integer"):
        require_integral_quantity(quantity)


@pytest.mark.parametrize(
    ("list_price", "unit_cost", "currency_code"),
    [
        (None, None, None),
        (Decimal("10.123"), None, "USD"),
        (None, Decimal("2.345"), "EUR"),
        (Decimal("10.123"), Decimal("2.345"), "USD"),
    ],
)
def test_valid_product_monetary_combinations_are_accepted(
    list_price: Decimal | None,
    unit_cost: Decimal | None,
    currency_code: str | None,
) -> None:
    require_product_monetary_consistency(list_price, unit_cost, currency_code)


@pytest.mark.parametrize(
    ("list_price", "unit_cost", "currency_code"),
    [
        (None, None, "USD"),
        (Decimal("1.00"), None, None),
        (None, Decimal("1.00"), None),
    ],
)
def test_invalid_product_monetary_combinations_are_rejected(
    list_price: Decimal | None,
    unit_cost: Decimal | None,
    currency_code: str | None,
) -> None:
    with pytest.raises(TransformationRuleViolation, match="currency"):
        require_product_monetary_consistency(list_price, unit_cost, currency_code)


def test_line_amount_uses_exact_decimal_arithmetic_without_quantization() -> None:
    unit_price = Decimal("1.2345")

    result = derive_line_amount(3, unit_price)

    assert result == Decimal("3.7035")
    assert result.as_tuple().exponent == -4
    assert isinstance(result, Decimal)


def test_rules_reject_float_inputs() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        require_integral_quantity(2.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal"):
        derive_line_amount(2, 1.25)  # type: ignore[arg-type]
