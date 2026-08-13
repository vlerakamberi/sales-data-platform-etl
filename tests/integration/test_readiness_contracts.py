"""Readiness checks connecting operator documentation to stable contracts."""

import re
from pathlib import Path

from sales_data_platform.common.paths import PROJECT_ROOT, RAW_DATA_DIR
from sales_data_platform.config.settings import Settings
from sales_data_platform.orchestration.models import PIPELINE_TERMINAL_STATES

README = PROJECT_ROOT / "README.md"
RUNBOOK = PROJECT_ROOT / "docs" / "operations" / "runbook.md"
CONFIGURATION_GUIDE = PROJECT_ROOT / "docs" / "development" / "configuration-guide.md"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+]\((?P<target>[^)]+)\)")

CANONICAL_READINESS_ARTIFACTS = (
    README,
    RUNBOOK,
    CONFIGURATION_GUIDE,
    PROJECT_ROOT / "docs" / "architecture" / "architecture-overview.md",
    PROJECT_ROOT / "docs" / "architecture" / "database-design.md",
    PROJECT_ROOT / "docs" / "architecture" / "data-ingestion.md",
    PROJECT_ROOT / "docs" / "architecture" / "data-transformation.md",
    PROJECT_ROOT / "docs" / "architecture" / "data-quality.md",
    PROJECT_ROOT / "docs" / "architecture" / "pipeline-orchestration.md",
    PROJECT_ROOT / "docs" / "architecture" / "testing.md",
    *tuple(sorted((PROJECT_ROOT / "docs" / "adr").glob("ADR-*.md"))),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _heading_anchors(markdown: str) -> set[str]:
    anchors: set[str] = set()
    for line in markdown.splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip().lower()
        anchor = re.sub(r"[^\w\s-]", "", heading)
        anchors.add(re.sub(r"[\s-]+", "-", anchor).strip("-"))
    return anchors


def _local_links(document: Path) -> tuple[tuple[Path, str | None], ...]:
    links: list[tuple[Path, str | None]] = []
    for match in MARKDOWN_LINK.finditer(_read(document)):
        target = match.group("target")
        if "://" in target or target.startswith("mailto:"):
            continue
        path_text, separator, fragment = target.partition("#")
        target_path = document if not path_text else document.parent / path_text
        links.append((target_path.resolve(), fragment if separator else None))
    return tuple(links)


def _example_values() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in _read(ENV_EXAMPLE).splitlines()
        if line and not line.startswith("#")
    )


def test_canonical_readiness_artifacts_are_present_and_nonempty() -> None:
    assert all(
        path.is_file() and path.stat().st_size > 0
        for path in CANONICAL_READINESS_ARTIFACTS
    )


def test_readme_and_runbook_local_navigation_resolves() -> None:
    resolved_link_count = 0
    for document in (README, RUNBOOK):
        links = _local_links(document)
        resolved_link_count += len(links)
        for target, fragment in links:
            assert target.is_file(), f"Broken local link in {document}: {target}"
            if fragment is not None:
                assert fragment in _heading_anchors(_read(target)), (
                    f"Broken heading link in {document}: {target}#{fragment}"
                )
    assert resolved_link_count > 0


def test_configuration_names_and_safe_example_match_documentation() -> None:
    aliases = {
        field.validation_alias
        for field in Settings.model_fields.values()
        if isinstance(field.validation_alias, str)
    }
    example = _example_values()
    material_names = {
        "INGESTION_SOURCE_ROOT",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
    }

    assert set(example) == aliases
    assert material_names <= aliases
    assert "DATABASE_USER" not in aliases
    assert "DATABASE_USER" not in example
    for document in (RUNBOOK, CONFIGURATION_GUIDE):
        text = _read(document)
        assert material_names <= {name for name in material_names if name in text}
        assert "`DATABASE_USER`" not in text

    readme = _read(README)
    assert "`DATABASE_*`" in readme
    assert "`.env.example`" in readme
    assert "`DATABASE_USER`" not in readme

    assert example["DATABASE_PASSWORD"] == "replace-with-local-password"
    settings = Settings(_env_file=None)
    assert settings.ingestion_source_root == RAW_DATA_DIR


def test_documented_outcomes_and_limitations_match_runtime_boundary() -> None:
    readme = _read(README)
    runbook = _read(RUNBOOK)
    documented = f"{readme}\n{runbook}"
    terminal_states = {state.value for state in PIPELINE_TERMINAL_STATES}

    assert terminal_states == {"SUCCEEDED", "BLOCKED", "FAILED"}
    assert all(
        f"`{state}`" in readme and f"`{state}`" in runbook for state in terminal_states
    )

    normalized = " ".join(documented.lower().split())
    for limitation in (
        "no automatic retry",
        "no exactly-once",
        "no scheduler",
        "no azure",
        "no repository 2 functionality",
    ):
        assert limitation in normalized
    assert re.search(r"no automatic retry (?:or|and) automatic resume", normalized)
