import pytest

from sales_data_platform.ingestion.contracts import BUILT_IN_REGISTRY
from sales_data_platform.ingestion.errors import (
    DiscoveryError,
    IngestionError,
    ParseError,
    RecordValidationError,
    SourceContractError,
)


@pytest.mark.parametrize(
    "error_type",
    [DiscoveryError, SourceContractError, ParseError, RecordValidationError],
)
def test_controlled_failures_inherit_ingestion_error(
    error_type: type[IngestionError],
) -> None:
    assert issubclass(error_type, IngestionError)


def test_contract_resolution_uses_source_contract_error() -> None:
    with pytest.raises(SourceContractError):
        BUILT_IN_REGISTRY.resolve("northstar.unknown", 1)


def test_safe_error_context_is_immutable() -> None:
    supplied = {"contract_id": "northstar.unknown", "contract_version": 1}
    error = SourceContractError("Unknown source contract", context=supplied)
    supplied["contract_id"] = "changed"
    assert str(error) == "Unknown source contract"
    assert error.context == {
        "contract_id": "northstar.unknown",
        "contract_version": 1,
    }
    with pytest.raises(TypeError):
        error.context["field_name"] = "customer_email"


def test_arbitrary_programming_errors_remain_uncontrolled() -> None:
    assert not issubclass(ValueError, IngestionError)
    assert not issubclass(RuntimeError, IngestionError)
