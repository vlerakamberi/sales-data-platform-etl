from pathlib import Path

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.discovery import (
    CONTRACT_DIRECTORIES,
    discover_source_files,
)
from sales_data_platform.ingestion.errors import DiscoveryError, SourceContractError
from sales_data_platform.ingestion.identity import normalize_relative_source_path


def _settings(source_root: Path) -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=source_root)


def _mapped_directory(source_root: Path, contract_key: SourceContractKey) -> Path:
    directory = source_root / CONTRACT_DIRECTORIES[contract_key]
    directory.mkdir(parents=True)
    return directory


def _create_symlink(link: Path, target: Path, *, target_is_directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as error:
        pytest.skip(f"environment cannot create symlinks: {error}")


def test_exactly_three_contract_directory_mappings_exist() -> None:
    assert dict(CONTRACT_DIRECTORIES) == {
        SourceContractKey("northstar.product_catalog", 1): Path("product_catalog/v1"),
        SourceContractKey("northstar.ecommerce_sales", 1): Path("ecommerce_sales/v1"),
        SourceContractKey("northstar.retail_sales", 1): Path("retail_sales/v1"),
    }
    with pytest.raises(TypeError):
        CONTRACT_DIRECTORIES[SourceContractKey("northstar.other", 1)] = Path("other")


@pytest.mark.parametrize(
    "contract_key",
    [
        SourceContractKey("northstar.product_catalog", 1),
        SourceContractKey("northstar.ecommerce_sales", 1),
        SourceContractKey("northstar.retail_sales", 1),
    ],
)
def test_each_known_contract_discovers_from_its_exact_directory(
    tmp_path: Path, contract_key: SourceContractKey
) -> None:
    directory = _mapped_directory(tmp_path, contract_key)
    source = directory / "source.csv"
    source.touch()

    assert discover_source_files(contract_key, _settings(tmp_path)) == (source,)


def test_unknown_contract_and_unsupported_version_remain_contract_errors(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(SourceContractError, match="Unknown"):
        discover_source_files(SourceContractKey("northstar.unknown", 1), settings)
    with pytest.raises(SourceContractError, match="Unsupported"):
        discover_source_files(
            SourceContractKey("northstar.product_catalog", 2), settings
        )


def test_discovery_is_non_recursive_filtered_and_deterministically_sorted(
    tmp_path: Path,
) -> None:
    key = SourceContractKey("northstar.ecommerce_sales", 1)
    directory = _mapped_directory(tmp_path, key)
    for name in (
        "z-last.csv",
        "a-first.csv",
        "orders.CSV",
        "orders.txt",
        "notes.json",
        ".hidden.csv",
        "~orders.csv",
        "#draft.csv",
        "working.tmp",
        "working.temp",
    ):
        (directory / name).touch()
    archive = directory / "archive"
    archive.mkdir()
    (archive / "nested.csv").touch()

    result = discover_source_files(key, _settings(tmp_path))

    assert isinstance(result, tuple)
    assert all(isinstance(path, Path) for path in result)
    assert tuple(path.name for path in result) == ("a-first.csv", "z-last.csv")
    relative_paths = tuple(
        normalize_relative_source_path(path, tmp_path) for path in result
    )
    assert relative_paths == tuple(sorted(relative_paths))


def test_filesystem_creation_order_does_not_control_results(tmp_path: Path) -> None:
    key = SourceContractKey("northstar.product_catalog", 1)
    directory = _mapped_directory(tmp_path, key)
    for name in ("third.csv", "first.csv", "second.csv"):
        (directory / name).touch()

    assert tuple(
        path.name for path in discover_source_files(key, _settings(tmp_path))
    ) == ("first.csv", "second.csv", "third.csv")


def test_missing_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="root does not exist"):
        discover_source_files(
            SourceContractKey("northstar.product_catalog", 1),
            _settings(tmp_path / "missing"),
        )


def test_root_as_file_is_rejected(tmp_path: Path) -> None:
    root_file = tmp_path / "root"
    root_file.touch()
    with pytest.raises(DiscoveryError, match="root is not a directory"):
        discover_source_files(
            SourceContractKey("northstar.product_catalog", 1), _settings(root_file)
        )


def test_missing_mapped_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="source directory does not exist"):
        discover_source_files(
            SourceContractKey("northstar.product_catalog", 1), _settings(tmp_path)
        )


def test_mapped_path_as_file_is_rejected(tmp_path: Path) -> None:
    mapped_path = tmp_path / "product_catalog" / "v1"
    mapped_path.parent.mkdir()
    mapped_path.touch()
    with pytest.raises(DiscoveryError, match="source path is not a directory"):
        discover_source_files(
            SourceContractKey("northstar.product_catalog", 1), _settings(tmp_path)
        )


def test_valid_empty_directory_returns_empty_tuple(tmp_path: Path) -> None:
    key = SourceContractKey("northstar.retail_sales", 1)
    _mapped_directory(tmp_path, key)
    assert discover_source_files(key, _settings(tmp_path)) == ()


def test_symlinked_eligible_csv_is_rejected(tmp_path: Path) -> None:
    key = SourceContractKey("northstar.product_catalog", 1)
    directory = _mapped_directory(tmp_path, key)
    target = tmp_path / "target.csv"
    target.touch()
    _create_symlink(directory / "linked.csv", target, target_is_directory=False)

    with pytest.raises(DiscoveryError, match="file must not be a symlink"):
        discover_source_files(key, _settings(tmp_path))


def test_symlinked_mapped_directory_is_rejected(tmp_path: Path) -> None:
    key = SourceContractKey("northstar.retail_sales", 1)
    target = tmp_path / "real"
    target.mkdir()
    mapped = tmp_path / "retail_sales" / "v1"
    mapped.parent.mkdir()
    _create_symlink(mapped, target, target_is_directory=True)

    with pytest.raises(DiscoveryError, match="directory must not be a symlink"):
        discover_source_files(key, _settings(tmp_path))


def test_source_outside_root_cannot_be_accepted(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.touch()
    with pytest.raises(ValueError, match="inside"):
        normalize_relative_source_path(outside, root)


def test_unrelated_symlink_is_not_followed(tmp_path: Path) -> None:
    key = SourceContractKey("northstar.product_catalog", 1)
    directory = _mapped_directory(tmp_path, key)
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    (outside_directory / "nested.csv").touch()
    _create_symlink(
        directory / "unrelated-directory",
        outside_directory,
        target_is_directory=True,
    )

    assert discover_source_files(key, _settings(tmp_path)) == ()
