"""Explicit pure business rules for canonical transformation."""

from decimal import Decimal


class TransformationRuleViolation(ValueError):
    """A controlled violation of an explicit transformation business rule."""


def require_integral_quantity(quantity: Decimal) -> int:
    """Return an exact integral quantity without rounding or truncation."""

    if not isinstance(quantity, Decimal):
        raise TypeError("Quantity must be a Decimal")
    if not quantity.is_finite() or quantity != quantity.to_integral_value():
        raise TransformationRuleViolation("Quantity must be an exact integer")
    return int(quantity)


def require_product_monetary_consistency(
    list_price: Decimal | None,
    unit_cost: Decimal | None,
    currency_code: str | None,
) -> None:
    """Require currency exactly when at least one product monetary value exists."""

    has_monetary_value = list_price is not None or unit_cost is not None
    has_currency = currency_code is not None
    if has_monetary_value != has_currency:
        raise TransformationRuleViolation(
            "Product currency must be present exactly when a monetary value exists"
        )


def derive_line_amount(quantity: int, unit_price: Decimal) -> Decimal:
    """Derive an exact record-level line amount."""

    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise TypeError("Quantity must be an integer")
    if not isinstance(unit_price, Decimal):
        raise TypeError("Unit price must be a Decimal")
    return Decimal(quantity) * unit_price
