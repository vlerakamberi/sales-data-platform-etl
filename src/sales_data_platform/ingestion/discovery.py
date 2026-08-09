"""Deterministic discovery of approved physical CSV source files."""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import (
    BUILT_IN_REGISTRY,
    SourceContractKey,
)
from sales_data_platform.ingestion.errors import DiscoveryError
from sales_data_platform.ingestion.identity import normalize_relative_source_path

CONTRACT_DIRECTORIES: Mapping[SourceContractKey, Path] = MappingProxyType(
    {
        SourceContractKey("northstar.product_catalog", 1): Path("product_catalog/v1"),
        SourceContractKey("northstar.ecommerce_sales", 1): Path("ecommerce_sales/v1"),
        SourceContractKey("northstar.retail_sales", 1): Path("retail_sales/v1"),
    }
)


def _is_eligible_name(path: Path) -> bool:
    name = path.name
    return (
        path.suffix == ".csv"
        and not name.startswith((".", "~", "#"))
        and not name.endswith("~")
    )


def discover_source_files(
    contract_key: SourceContractKey, settings: Settings
) -> tuple[Path, ...]:
    """Discover direct physical CSV files for one exact approved contract."""

    contract = BUILT_IN_REGISTRY.resolve(
        contract_key.source_contract_id,
        contract_key.source_contract_version,
    )
    relative_directory = CONTRACT_DIRECTORIES[contract.key]
    source_root = settings.ingestion_source_root

    try:
        if not source_root.exists():
            raise DiscoveryError("Ingestion source root does not exist")
        if source_root.is_symlink():
            raise DiscoveryError("Ingestion source root must not be a symlink")
        if not source_root.is_dir():
            raise DiscoveryError("Ingestion source root is not a directory")

        resolved_root = source_root.resolve(strict=True)
        contract_directory = source_root / relative_directory
        if not contract_directory.exists():
            raise DiscoveryError("Required contract source directory does not exist")
        current_directory = source_root
        for component in relative_directory.parts:
            current_directory /= component
            if current_directory.is_symlink():
                raise DiscoveryError(
                    "Required contract source directory must not be a symlink"
                )
        if not contract_directory.is_dir():
            raise DiscoveryError("Required contract source path is not a directory")

        resolved_directory = contract_directory.resolve(strict=True)
        try:
            resolved_directory.relative_to(resolved_root)
        except ValueError as error:
            raise DiscoveryError(
                "Required contract source directory escapes the ingestion source root"
            ) from error

        eligible: list[tuple[str, Path]] = []
        for candidate in contract_directory.iterdir():
            if not _is_eligible_name(candidate):
                continue
            if candidate.is_symlink():
                raise DiscoveryError("Eligible source file must not be a symlink")
            if not candidate.is_file():
                continue
            relative_path = normalize_relative_source_path(candidate, source_root)
            eligible.append((relative_path, candidate))
    except DiscoveryError:
        raise
    except OSError as error:
        raise DiscoveryError("Unable to access ingestion source files") from error

    eligible.sort(key=lambda item: item[0])
    return tuple(path for _, path in eligible)
