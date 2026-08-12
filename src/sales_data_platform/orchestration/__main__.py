"""Manual local entry point for deterministic pipeline orchestration."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.logging import configure_logging
from sales_data_platform.orchestration.models import (
    PipelineExecutionId,
    PipelineLifecycleState,
    PipelineResult,
)
from sales_data_platform.orchestration.service import run_pipeline


def _predecessor(value: str) -> PipelineExecutionId:
    try:
        return PipelineExecutionId(UUID(value))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            "predecessor execution ID must be a valid UUID"
        ) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one governed local pipeline execution."
    )
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--contract-version", required=True, type=int)
    parser.add_argument("--source-path", required=True, type=Path)
    parser.add_argument(
        "--predecessor-execution-id",
        type=_predecessor,
        default=None,
    )
    return parser


def _timestamp(value: object) -> str:
    return "-" if value is None else value.isoformat()


def _render_result(result: PipelineResult) -> None:
    print(f"execution_id: {result.execution_id.value}")
    print(f"state: {result.state.value}")
    if result.predecessor_execution_id is not None:
        print(f"predecessor_execution_id: {result.predecessor_execution_id.value}")
    print(f"created_at: {_timestamp(result.created_at)}")
    print(f"started_at: {_timestamp(result.started_at)}")
    print(f"completed_at: {_timestamp(result.completed_at)}")
    for stage in result.stages:
        print(f"stage: {stage.stage.name}")
        print(f"  state: {stage.state.value}")
        print(f"  started_at: {_timestamp(stage.started_at)}")
        print(f"  completed_at: {_timestamp(stage.completed_at)}")
        if stage.failure is not None:
            print(f"  failure_category: {stage.failure.category.value}")
            if stage.failure.code is not None:
                print(f"  failure_code: {stage.failure.code}")
    if result.failure is not None:
        print(f"failure_category: {result.failure.category.value}")
        if result.failure.code is not None:
            print(f"failure_code: {result.failure.code}")


def _exit_code(state: PipelineLifecycleState) -> int:
    if state is PipelineLifecycleState.SUCCEEDED:
        return 0
    if state is PipelineLifecycleState.BLOCKED:
        return 3
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one invocation, execute it, and render its durable result."""
    arguments = _parser().parse_args(argv)
    try:
        settings = Settings()
        configure_logging(settings)
    except Exception:
        print("Orchestration configuration failed.", file=sys.stderr)
        return 1

    try:
        connection = connect_database(settings)
    except Exception:
        print("Database connection failed.", file=sys.stderr)
        return 1

    result = None
    execution_failed = False
    try:
        result = run_pipeline(
            connection,
            contract_key=SourceContractKey(
                arguments.contract_id,
                arguments.contract_version,
            ),
            source_path=arguments.source_path,
            settings=settings,
            predecessor_execution_id=arguments.predecessor_execution_id,
        )
    except Exception:
        print("Pipeline orchestration failed.", file=sys.stderr)
        execution_failed = True

    try:
        connection.close()
    except Exception:
        if not execution_failed:
            print("Database connection cleanup failed.", file=sys.stderr)
        return 1

    if execution_failed:
        return 1

    _render_result(result)
    return _exit_code(result.state)


if __name__ == "__main__":
    raise SystemExit(main())
