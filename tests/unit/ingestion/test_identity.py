import hashlib
import inspect
import json
from pathlib import Path

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.identity import (
    build_source_identity,
    calculate_content_sha256,
    normalize_relative_source_path,
)
from sales_data_platform.ingestion.models import ContentSha256, SourceIdentity


def test_content_sha256_hashes_known_exact_raw_bytes(tmp_path: Path) -> None:
    content = b"\xef\xbb\xbfsku,name\r\nA-1, Widget \r\n"
    source = tmp_path / "catalog.csv"
    source.write_bytes(content)

    result = calculate_content_sha256(source)

    assert type(result) is ContentSha256
    assert result.value == hashlib.sha256(content).hexdigest()


def test_lf_and_crlf_bytes_produce_different_hashes(tmp_path: Path) -> None:
    lf_source = tmp_path / "lf.csv"
    crlf_source = tmp_path / "crlf.csv"
    lf_source.write_bytes(b"sku\nA-1\n")
    crlf_source.write_bytes(b"sku\r\nA-1\r\n")

    assert calculate_content_sha256(lf_source) != calculate_content_sha256(crlf_source)


def test_chunked_hashing_handles_nontrivial_content(tmp_path: Path) -> None:
    content = bytes(range(256)) * 1025
    source = tmp_path / "large.csv"
    source.write_bytes(content)

    assert calculate_content_sha256(source).value == hashlib.sha256(content).hexdigest()


def test_source_identity_matches_independently_calculated_canonical_payload() -> None:
    contract_key = SourceContractKey("northstar.ecommerce_sales", 1)
    content_sha256 = ContentSha256("a" * 64)
    payload = {
        "contract_id": "northstar.ecommerce_sales",
        "contract_version": 1,
        "source_path": "ecommerce_sales/v1/orders.csv",
        "content_sha256": "a" * 64,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    result = build_source_identity(
        contract_key, "ecommerce_sales/v1/orders.csv", content_sha256
    )

    assert type(result) is SourceIdentity
    assert result.value == hashlib.sha256(canonical).hexdigest()
    assert result == build_source_identity(
        contract_key, "ecommerce_sales/v1/orders.csv", content_sha256
    )


@pytest.mark.parametrize(
    ("contract_key", "relative_path", "content_sha256"),
    [
        (
            SourceContractKey("northstar.retail_sales", 1),
            "ecommerce_sales/v1/orders.csv",
            ContentSha256("a" * 64),
        ),
        (
            SourceContractKey("northstar.ecommerce_sales", 2),
            "ecommerce_sales/v1/orders.csv",
            ContentSha256("a" * 64),
        ),
        (
            SourceContractKey("northstar.ecommerce_sales", 1),
            "ecommerce_sales/v1/other.csv",
            ContentSha256("a" * 64),
        ),
        (
            SourceContractKey("northstar.ecommerce_sales", 1),
            "ecommerce_sales/v1/orders.csv",
            ContentSha256("b" * 64),
        ),
    ],
)
def test_each_canonical_input_changes_source_identity(
    contract_key: SourceContractKey,
    relative_path: str,
    content_sha256: ContentSha256,
) -> None:
    baseline = build_source_identity(
        SourceContractKey("northstar.ecommerce_sales", 1),
        "ecommerce_sales/v1/orders.csv",
        ContentSha256("a" * 64),
    )
    assert (
        build_source_identity(contract_key, relative_path, content_sha256) != baseline
    )


def test_source_identity_has_no_run_or_absolute_root_input(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_source = first_root / "retail_sales" / "v1" / "sales.csv"
    second_source = second_root / "retail_sales" / "v1" / "sales.csv"
    first_source.parent.mkdir(parents=True)
    second_source.parent.mkdir(parents=True)
    first_source.write_bytes(b"same")
    second_source.write_bytes(b"same")

    first_relative = normalize_relative_source_path(first_source, first_root)
    second_relative = normalize_relative_source_path(second_source, second_root)
    digest = calculate_content_sha256(first_source)

    assert first_relative == second_relative == "retail_sales/v1/sales.csv"
    assert build_source_identity(
        SourceContractKey("northstar.retail_sales", 1), first_relative, digest
    ) == build_source_identity(
        SourceContractKey("northstar.retail_sales", 1), second_relative, digest
    )
    assert "run_id" not in inspect.signature(build_source_identity).parameters


def test_normalized_relative_path_uses_posix_separators_and_preserves_case(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Product_Catalog" / "v1" / "Items.Case.csv"
    source.parent.mkdir(parents=True)
    source.touch()

    normalized = normalize_relative_source_path(source, tmp_path)

    assert normalized == "Product_Catalog/v1/Items.Case.csv"
    assert "\\" not in normalized


def test_equivalent_windows_and_posix_physical_paths_normalize_identically(
    tmp_path: Path,
) -> None:
    source = tmp_path / "retail_sales" / "v1" / "sales.csv"
    source.parent.mkdir(parents=True)
    source.touch()
    posix_spelling = Path(str(source).replace("\\", "/"))

    assert normalize_relative_source_path(source, tmp_path) == (
        normalize_relative_source_path(posix_spelling, tmp_path)
    )


def test_out_of_root_and_traversal_paths_are_rejected(tmp_path: Path) -> None:
    source_root = tmp_path / "root"
    source_root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.touch()

    with pytest.raises(ValueError, match="inside"):
        normalize_relative_source_path(source_root / ".." / "outside.csv", source_root)
    with pytest.raises(ValueError, match="normalized POSIX"):
        build_source_identity(
            SourceContractKey("northstar.product_catalog", 1),
            "product_catalog/../outside.csv",
            ContentSha256("a" * 64),
        )


@pytest.mark.parametrize(
    "relative_source_path",
    [".", "C:/data/orders.csv", "c:/data/orders.csv"],
)
def test_source_identity_rejects_non_relative_or_drive_qualified_paths(
    relative_source_path: str,
) -> None:
    with pytest.raises(ValueError, match="normalized POSIX"):
        build_source_identity(
            SourceContractKey("northstar.ecommerce_sales", 1),
            relative_source_path,
            ContentSha256("a" * 64),
        )
