"""Deterministic content and source identity helpers."""

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import ContentSha256, SourceIdentity

_HASH_CHUNK_SIZE = 64 * 1024


def calculate_content_sha256(path: Path) -> ContentSha256:
    """Hash the exact physical bytes of a source file incrementally."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return ContentSha256(digest.hexdigest())


def normalize_relative_source_path(path: Path, source_root: Path) -> str:
    """Return a contained physical source path as a POSIX relative identifier."""

    resolved_root = source_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    try:
        relative_path = resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            "Source path must remain inside the ingestion source root"
        ) from error

    normalized = relative_path.as_posix()
    parts = PurePosixPath(normalized).parts
    if (
        not normalized
        or normalized == "."
        or any(part in {".", ".."} for part in parts)
    ):
        raise ValueError("Source path must be a normalized relative path")
    return normalized


def build_source_identity(
    contract_key: SourceContractKey,
    relative_source_path: str,
    content_sha256: ContentSha256,
) -> SourceIdentity:
    """Build identity from the exact canonical source-identity payload."""

    posix_path = PurePosixPath(relative_source_path)
    windows_path = PureWindowsPath(relative_source_path)
    if (
        not relative_source_path
        or relative_source_path == "."
        or posix_path.is_absolute()
        or bool(windows_path.drive)
        or "\\" in relative_source_path
        or relative_source_path != posix_path.as_posix()
        or any(part in {".", ".."} for part in posix_path.parts)
    ):
        raise ValueError("Source path must be a normalized POSIX relative path")

    payload = {
        "contract_id": contract_key.source_contract_id,
        "contract_version": contract_key.source_contract_version,
        "source_path": relative_source_path,
        "content_sha256": content_sha256.value,
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SourceIdentity(hashlib.sha256(canonical_payload).hexdigest())
