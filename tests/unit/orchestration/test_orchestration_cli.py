"""Unit tests for the manual orchestration command boundary."""

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.orchestration import __main__ as cli
from sales_data_platform.orchestration.errors import OrchestrationPersistenceError
from sales_data_platform.orchestration.models import (
    FailureClassification,
    FailureDetail,
    PipelineExecutionId,
    PipelineLifecycleState,
    StageIdentity,
    StageLifecycleState,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)
PREDECESSOR = UUID("86d39a49-1aee-46e1-8496-786283d2309d")
REQUIRED_ARGUMENTS = [
    "--contract-id",
    "northstar.product_catalog",
    "--contract-version",
    "1",
    "--source-path",
    "product_catalog/v1/products.csv",
]


class Connection:
    def __init__(self, close_error: Exception | None = None) -> None:
        self.closed = False
        self.close_calls = 0
        self.close_error = close_error

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


def _result(
    state: PipelineLifecycleState = PipelineLifecycleState.SUCCEEDED,
    *,
    predecessor: PipelineExecutionId | None = None,
    failure: FailureDetail | None = None,
):
    stage_failure = failure if state is PipelineLifecycleState.FAILED else None
    stage_state = (
        StageLifecycleState.FAILED
        if stage_failure is not None
        else StageLifecycleState.SUCCEEDED
    )
    stage = SimpleNamespace(
        stage=StageIdentity.INGESTION,
        state=stage_state,
        started_at=NOW,
        completed_at=NOW,
        failure=stage_failure,
    )
    return SimpleNamespace(
        execution_id=PipelineExecutionId(UUID("98b73798-e320-4618-819f-badb9fc17751")),
        state=state,
        stages=(stage,),
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        predecessor_execution_id=predecessor,
        failure=failure,
    )


def _wire(monkeypatch: pytest.MonkeyPatch, result=None):
    settings = object()
    connection = Connection()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda received: calls.append(("logging", received)),
    )
    monkeypatch.setattr(
        cli,
        "connect_database",
        lambda received: calls.append(("connect", received)) or connection,
    )

    def run(received_connection, **kwargs):
        calls.append(("run", received_connection, kwargs))
        return result or _result()

    monkeypatch.setattr(cli, "run_pipeline", run)
    return settings, connection, calls


def test_valid_required_arguments_bind_exact_service_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, connection, calls = _wire(monkeypatch)

    assert cli.main(REQUIRED_ARGUMENTS) == 0

    assert calls[:2] == [("logging", settings), ("connect", settings)]
    _, received_connection, keyword_arguments = calls[2]
    assert received_connection is connection
    assert keyword_arguments == {
        "contract_key": SourceContractKey("northstar.product_catalog", 1),
        "source_path": Path("product_catalog/v1/products.csv"),
        "settings": settings,
        "predecessor_execution_id": None,
    }
    assert isinstance(keyword_arguments["contract_key"].source_contract_version, int)
    assert isinstance(keyword_arguments["source_path"], Path)
    assert connection.closed
    assert connection.close_calls == 1


def test_valid_predecessor_is_constructed_as_pipeline_execution_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, calls = _wire(monkeypatch)

    assert (
        cli.main(
            [
                *REQUIRED_ARGUMENTS,
                "--predecessor-execution-id",
                str(PREDECESSOR),
            ]
        )
        == 0
    )

    assert calls[2][2]["predecessor_execution_id"] == PipelineExecutionId(PREDECESSOR)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (PipelineLifecycleState.SUCCEEDED, 0),
        (PipelineLifecycleState.BLOCKED, 3),
        (PipelineLifecycleState.FAILED, 1),
    ],
)
def test_terminal_state_controls_exit_code(monkeypatch, state, expected) -> None:
    _wire(monkeypatch, _result(state))
    assert cli.main(REQUIRED_ARGUMENTS) == expected


@pytest.mark.parametrize(
    "arguments",
    [
        [*REQUIRED_ARGUMENTS, "--predecessor-execution-id", "not-a-uuid"],
        [
            "--contract-id",
            "northstar.product_catalog",
            "--contract-version",
            "one",
            "--source-path",
            "products.csv",
        ],
    ],
)
def test_invalid_typed_argument_exits_two_before_execution(
    monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    invoked = False

    def run(*args, **kwargs):
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(cli, "run_pipeline", run)

    with pytest.raises(SystemExit) as raised:
        cli.main(arguments)

    assert raised.value.code == 2
    assert not invoked


@pytest.mark.parametrize("boundary", ["settings", "logging"])
def test_configuration_failure_is_controlled_and_safe(
    monkeypatch: pytest.MonkeyPatch, capsys, boundary
) -> None:
    secret = "raw-secret-value"
    if boundary == "settings":
        monkeypatch.setattr(
            cli,
            "Settings",
            lambda: (_ for _ in ()).throw(ValueError(secret)),
        )
    else:
        monkeypatch.setattr(cli, "Settings", object)
        monkeypatch.setattr(
            cli,
            "configure_logging",
            lambda *_: (_ for _ in ()).throw(ValueError(secret)),
        )

    assert cli.main(REQUIRED_ARGUMENTS) == 1
    output = capsys.readouterr()
    assert "Orchestration configuration failed." in output.err
    assert secret not in output.out + output.err


def test_database_connection_failure_is_controlled_and_safe(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    secret = "postgresql://username:password@host/database"
    unestablished_connection = Connection()
    monkeypatch.setattr(cli, "Settings", object)
    monkeypatch.setattr(cli, "configure_logging", lambda *_: None)
    monkeypatch.setattr(
        cli,
        "connect_database",
        lambda *_: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert cli.main(REQUIRED_ARGUMENTS) == 1
    output = capsys.readouterr()
    assert "Database connection failed." in output.err
    assert secret not in output.out + output.err
    assert unestablished_connection.close_calls == 0


@pytest.mark.parametrize(
    "error",
    [RuntimeError("raw payload"), OrchestrationPersistenceError("database detail")],
)
def test_orchestration_or_persistence_failure_is_safe_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch, capsys, error: Exception
) -> None:
    _, connection, _ = _wire(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *_a, **_k: (_ for _ in ()).throw(error),
    )

    assert cli.main(REQUIRED_ARGUMENTS) == 1
    output = capsys.readouterr()
    assert output.err.strip() == "Pipeline orchestration failed."
    assert str(error) not in output.out + output.err
    assert connection.closed
    assert connection.close_calls == 1


@pytest.mark.parametrize(
    "state",
    [PipelineLifecycleState.SUCCEEDED, PipelineLifecycleState.BLOCKED],
)
def test_close_failure_overrides_successful_or_blocked_local_exit_only(
    monkeypatch: pytest.MonkeyPatch, capsys, state: PipelineLifecycleState
) -> None:
    result = _result(state)
    settings, _, calls = _wire(monkeypatch, result)
    close_detail = "database credentials and connection detail"
    connection = Connection(RuntimeError(close_detail))
    monkeypatch.setattr(
        cli,
        "connect_database",
        lambda received: calls.append(("connect", received)) or connection,
    )

    assert cli.main(REQUIRED_ARGUMENTS) == 1

    output = capsys.readouterr()
    assert output.err.strip() == "Database connection cleanup failed."
    assert close_detail not in output.out + output.err
    assert "Traceback" not in output.out + output.err
    assert connection.close_calls == 1
    assert result.state is state
    assert [call[0] for call in calls].count("run") == 1


def test_execution_and_close_failure_preserves_primary_controlled_failure(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    execution_detail = "raw execution detail"
    cleanup_detail = "secondary database detail"
    _, connection, _ = _wire(monkeypatch)
    connection.close_error = RuntimeError(cleanup_detail)
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(execution_detail)),
    )

    assert cli.main(REQUIRED_ARGUMENTS) == 1

    output = capsys.readouterr()
    assert output.err.strip() == "Pipeline orchestration failed."
    assert execution_detail not in output.out + output.err
    assert cleanup_detail not in output.out + output.err
    assert "Traceback" not in output.out + output.err
    assert connection.close_calls == 1


def test_successful_result_renders_only_structured_operator_fields(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    predecessor = PipelineExecutionId(PREDECESSOR)
    _wire(monkeypatch, _result(predecessor=predecessor))

    assert cli.main(REQUIRED_ARGUMENTS) == 0

    output = capsys.readouterr().out
    assert "execution_id: 98b73798-e320-4618-819f-badb9fc17751" in output
    assert "state: SUCCEEDED" in output
    assert f"predecessor_execution_id: {PREDECESSOR}" in output
    assert "stage: INGESTION" in output
    assert "source-path" not in output


def test_failed_result_renders_only_controlled_failure_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    failure = FailureDetail(
        FailureClassification.INGESTION_FAILURE,
        "INGESTION_ERROR",
    )
    _wire(monkeypatch, _result(PipelineLifecycleState.FAILED, failure=failure))

    assert cli.main(REQUIRED_ARGUMENTS) == 1

    output = capsys.readouterr().out
    assert "failure_category: INGESTION_FAILURE" in output
    assert "failure_code: INGESTION_ERROR" in output
    assert "raw source" not in output


def test_import_has_no_operational_side_effect_and_cli_has_no_migration_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sales_data_platform.database.connection as database_connection
    import sales_data_platform.orchestration.service as orchestration_service

    monkeypatch.setattr(
        database_connection,
        "connect_database",
        lambda *_: (_ for _ in ()).throw(AssertionError("database access")),
    )
    monkeypatch.setattr(
        orchestration_service,
        "run_pipeline",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("pipeline execution")),
    )
    sys.modules.pop("sales_data_platform.orchestration.__main__", None)

    imported = importlib.import_module("sales_data_platform.orchestration.__main__")

    assert callable(imported.main)
    assert not hasattr(imported, "apply_migrations")
