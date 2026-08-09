"""Immutable, versioned contracts for approved ingestion sources."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from sales_data_platform.ingestion.errors import SourceContractError


class PrimitiveFieldType(Enum):
    """Primitive types used by the approved source contracts."""

    STRING = "STRING"
    DECIMAL = "DECIMAL"
    TIMESTAMP = "TIMESTAMP"


class FieldConstraint(Enum):
    """Minimal declarative constraints used by approved source fields."""

    NON_NEGATIVE = "NON_NEGATIVE"
    POSITIVE = "POSITIVE"
    UPPERCASE_CURRENCY_CODE = "UPPERCASE_CURRENCY_CODE"
    TIMEZONE_AWARE = "TIMEZONE_AWARE"


@dataclass(frozen=True, slots=True)
class SourceContractKey:
    """The exact identity of a versioned source contract."""

    source_contract_id: str
    source_contract_version: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_contract_id, str)
            or not self.source_contract_id.strip()
        ):
            raise SourceContractError("Source contract ID must be a non-empty string")
        if (
            not isinstance(self.source_contract_version, int)
            or isinstance(self.source_contract_version, bool)
            or self.source_contract_version <= 0
        ):
            raise SourceContractError(
                "Source contract version must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class FieldContract:
    """A declarative external source-field contract."""

    name: str
    field_type: PrimitiveFieldType
    header_required: bool
    nullable: bool
    constraints: tuple[FieldConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SourceContractError("Source field name must be a non-empty string")
        object.__setattr__(self, "constraints", tuple(self.constraints))


@dataclass(frozen=True, slots=True)
class SourceContract:
    """An immutable external source interface."""

    key: SourceContractKey
    fields: tuple[FieldContract, ...]

    def __post_init__(self) -> None:
        fields = tuple(self.fields)
        names = tuple(field.name for field in fields)
        if len(names) != len(set(names)):
            raise SourceContractError(
                "Source contract field names must be unique",
                context={
                    "contract_id": self.key.source_contract_id,
                    "contract_version": self.key.source_contract_version,
                },
            )
        object.__setattr__(self, "fields", fields)


class SourceContractRegistry:
    """An immutable registry resolved only by exact contract identity."""

    __slots__ = ("_contracts",)

    def __init__(self, contracts: Iterable[SourceContract]) -> None:
        indexed: dict[SourceContractKey, SourceContract] = {}
        for contract in contracts:
            if contract.key in indexed:
                raise SourceContractError(
                    "Duplicate source contract key",
                    context={
                        "contract_id": contract.key.source_contract_id,
                        "contract_version": contract.key.source_contract_version,
                    },
                )
            indexed[contract.key] = contract
        self._contracts: Mapping[SourceContractKey, SourceContract] = MappingProxyType(
            indexed
        )

    @property
    def contracts(self) -> tuple[SourceContract, ...]:
        """Return all registered contracts in their declared order."""

        return tuple(self._contracts.values())

    def resolve(
        self, source_contract_id: str, source_contract_version: int
    ) -> SourceContract:
        """Resolve one exact contract ID and version without fallback or coercion."""

        key = SourceContractKey(source_contract_id, source_contract_version)
        contract = self._contracts.get(key)
        if contract is not None:
            return contract

        context = {
            "contract_id": source_contract_id,
            "contract_version": source_contract_version,
        }
        if any(
            registered.source_contract_id == source_contract_id
            for registered in self._contracts
        ):
            raise SourceContractError(
                "Unsupported source contract version", context=context
            )
        raise SourceContractError("Unknown source contract ID", context=context)


def _field(
    name: str,
    field_type: PrimitiveFieldType,
    *,
    nullable: bool = False,
    constraints: tuple[FieldConstraint, ...] = (),
) -> FieldContract:
    return FieldContract(
        name,
        field_type,
        header_required=True,
        nullable=nullable,
        constraints=constraints,
    )


BUILT_IN_CONTRACTS = (
    SourceContract(
        SourceContractKey("northstar.product_catalog", 1),
        (
            _field("sku", PrimitiveFieldType.STRING),
            _field("product_name", PrimitiveFieldType.STRING),
            _field("category_code", PrimitiveFieldType.STRING),
            _field(
                "list_price",
                PrimitiveFieldType.DECIMAL,
                nullable=True,
                constraints=(FieldConstraint.NON_NEGATIVE,),
            ),
            _field(
                "unit_cost",
                PrimitiveFieldType.DECIMAL,
                nullable=True,
                constraints=(FieldConstraint.NON_NEGATIVE,),
            ),
            _field(
                "currency_code",
                PrimitiveFieldType.STRING,
                nullable=True,
                constraints=(FieldConstraint.UPPERCASE_CURRENCY_CODE,),
            ),
        ),
    ),
    SourceContract(
        SourceContractKey("northstar.ecommerce_sales", 1),
        (
            _field("order_number", PrimitiveFieldType.STRING),
            _field(
                "order_timestamp",
                PrimitiveFieldType.TIMESTAMP,
                constraints=(FieldConstraint.TIMEZONE_AWARE,),
            ),
            _field("customer_email", PrimitiveFieldType.STRING, nullable=True),
            _field("sku", PrimitiveFieldType.STRING),
            _field(
                "quantity",
                PrimitiveFieldType.DECIMAL,
                constraints=(FieldConstraint.POSITIVE,),
            ),
            _field(
                "unit_price",
                PrimitiveFieldType.DECIMAL,
                constraints=(FieldConstraint.NON_NEGATIVE,),
            ),
            _field(
                "currency_code",
                PrimitiveFieldType.STRING,
                constraints=(FieldConstraint.UPPERCASE_CURRENCY_CODE,),
            ),
        ),
    ),
    SourceContract(
        SourceContractKey("northstar.retail_sales", 1),
        (
            _field("receipt_number", PrimitiveFieldType.STRING),
            _field(
                "transaction_timestamp",
                PrimitiveFieldType.TIMESTAMP,
                constraints=(FieldConstraint.TIMEZONE_AWARE,),
            ),
            _field("store_code", PrimitiveFieldType.STRING),
            _field("terminal_id", PrimitiveFieldType.STRING),
            _field("sku", PrimitiveFieldType.STRING),
            _field(
                "quantity",
                PrimitiveFieldType.DECIMAL,
                constraints=(FieldConstraint.POSITIVE,),
            ),
            _field(
                "unit_price",
                PrimitiveFieldType.DECIMAL,
                constraints=(FieldConstraint.NON_NEGATIVE,),
            ),
            _field(
                "currency_code",
                PrimitiveFieldType.STRING,
                constraints=(FieldConstraint.UPPERCASE_CURRENCY_CODE,),
            ),
        ),
    ),
)

BUILT_IN_REGISTRY = SourceContractRegistry(BUILT_IN_CONTRACTS)
