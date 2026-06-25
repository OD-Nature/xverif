from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CliRunner, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = result.response
    if (
        result.returncode == 0
        and not result.timed_out
        and isinstance(response, dict)
        and response.get("ok") is True
    ):
        return response
    artifact_dir = ArtifactWriter(artifact_root).write(case_name, result, extra=extra)
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout:\n%s\nstderr:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


@pytest.fixture
def active_zero_evidence_fixture(
    command_runner: CommandRunner,
    xdebug_root: Path,
    artifact_root: Path,
) -> tuple[Path, Path]:
    fixture_dir = xdebug_root / "testdata" / "combined" / "active_zero_evidence"
    build = command_runner.run(
        ["make", "clean", "fixture"],
        cwd=fixture_dir,
        timeout_sec=600,
        metadata={"suite": "active-zero-evidence"},
    )
    if build.returncode != 0 or build.timed_out:
        _require_success(
            build,
            case_name="active-zero-evidence-build",
            artifact_root=artifact_root,
            extra={
                "source": (fixture_dir / "active_zero_evidence_tb.v").read_text(
                    encoding="utf-8"
                )
            },
        )

    daidir = fixture_dir / "out" / "simv.daidir"
    fsdb = fixture_dir / "out" / "waves.fsdb"
    assert daidir.is_dir()
    assert fsdb.is_file() and fsdb.stat().st_size > 0
    return daidir, fsdb


@pytest.fixture
def active_zero_evidence_session(
    cli_runner: CliRunner,
    active_zero_evidence_fixture: tuple[Path, Path],
    artifact_root: Path,
) -> str:
    daidir, fsdb = active_zero_evidence_fixture
    response = _require_success(
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.open",
                "target": {"daidir": str(daidir), "fsdb": str(fsdb)},
                "args": {"name": "active_zero_evidence"},
            },
            timeout_sec=120,
        ),
        case_name="active-zero-evidence-session-open",
        artifact_root=artifact_root,
    )
    session = response.get("session") or response["data"]["session"]
    session_id = session.get("session_id") or session.get("id")
    assert isinstance(session_id, str) and session_id
    try:
        yield session_id
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "target": {"session_id": session_id},
            },
            timeout_sec=60,
        )


def _query(
    cli_runner: CliRunner,
    session_id: str,
    action: str,
    signal: str,
    requested_time: str,
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "signal": signal,
        "requested_time": requested_time,
        "include_trace": True,
        "clk_period": "10ns",
    }
    return _require_success(
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": action,
                "target": {"session_id": session_id},
                "args": args,
                "output": {"verbosity": "compact"},
            },
            timeout_sec=120,
        ),
        case_name=f"{action}-{signal.rsplit('.', 1)[-1]}-{requested_time}",
        artifact_root=artifact_root,
        extra={"args": args},
    )


def _simple_query(
    cli_runner: CliRunner,
    session_id: str,
    action: str,
    args: dict[str, Any] | None,
    *,
    artifact_root: Path,
    output_format: str = "json",
) -> dict[str, Any] | str:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": action,
            "target": {"session_id": session_id},
            "args": args or {},
        },
        output_format=output_format,
        timeout_sec=120,
    )
    if output_format == "xout":
        if result.returncode == 0 and not result.timed_out and isinstance(result.response, str):
            return result.response
        artifact_dir = ArtifactWriter(artifact_root).write(
            f"{action}-xout", result, extra={"args": args or {}}
        )
        pytest.fail(f"{action} xout failed; artifacts={artifact_dir}")
    return _require_success(
        result,
        case_name=action,
        artifact_root=artifact_root,
        extra={"args": args or {}},
    )


@pytest.mark.combined
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_scope_roots_discovers_combined_top(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _simple_query(
        cli_runner,
        active_zero_evidence_session,
        "scope.roots",
        {"source": "auto"},
        artifact_root=artifact_root,
    )

    assert isinstance(response, dict)
    assert response["summary"]["recommended_root"] == "active_zero_evidence_tb"
    assert response["summary"]["matched_count"] == 1
    roots = response["data"]["roots"]
    root = next(item for item in roots if item["path"] == "active_zero_evidence_tb")
    assert root["status"] == "matched"
    assert root["sources"] == ["design", "wave"]
    assert root["wave"]["queryable"] is True
    assert root["design"]["traceable"] is True

    scope_response = _simple_query(
        cli_runner,
        active_zero_evidence_session,
        "scope.list",
        {"path": response["summary"]["recommended_root"], "recursive": False},
        artifact_root=artifact_root,
    )
    assert isinstance(scope_response, dict)
    assert scope_response["summary"]["signal_count"] > 0


@pytest.mark.combined
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_scope_roots_supports_source_filters_and_xout(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    wave = _simple_query(
        cli_runner,
        active_zero_evidence_session,
        "scope.roots",
        {"source": "wave"},
        artifact_root=artifact_root,
    )
    design = _simple_query(
        cli_runner,
        active_zero_evidence_session,
        "scope.roots",
        {"source": "design"},
        artifact_root=artifact_root,
    )
    xout = _simple_query(
        cli_runner,
        active_zero_evidence_session,
        "scope.roots",
        {"source": "auto"},
        artifact_root=artifact_root,
        output_format="xout",
    )

    assert isinstance(wave, dict)
    assert wave["summary"]["wave_count"] == 1
    assert wave["summary"]["design_count"] == 0
    assert wave["summary"]["recommended_root"] == "active_zero_evidence_tb"
    assert wave["data"]["roots"][0]["status"] == "wave_only"

    assert isinstance(design, dict)
    assert design["summary"]["design_count"] == 1
    assert design["summary"]["wave_count"] == 0
    assert design["summary"]["recommended_root"] == "active_zero_evidence_tb"
    assert design["data"]["roots"][0]["status"] == "design_only"

    assert isinstance(xout, str)
    assert "@xdebug.scope.roots.v1" in xout
    assert "recommended: active_zero_evidence_tb" in xout
    assert "path status sources wave design" in xout
    assert "active_zero_evidence_tb matched design,wave" in xout
    assert "limitations:" not in xout


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_reports_precise_active_time_for_delayed_query(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver",
        "active_zero_evidence_tb.u_reduction_10ns.sample_flag",
        "15ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["driver_status"] == "resolved"
    assert response["summary"]["active_time"] == "10ns"
    assert response["summary"]["evidence_source"] == "fsdb_precise_time_static_trace"
    driver = response["data"]["driver"]
    assert driver["line"] == 77
    assert driver["signals"] == [
        "active_zero_evidence_tb.u_reduction_10ns.sample_flag_expr"
    ]
    assert "sample_flag <= sample_flag_expr" in driver["text"]
    assert any(
        node["kind"] == "if_else" and node["line"] == 74
        for node in response["data"]["trace"]["nodes"]
    )
    assert any(
        node["kind"] == "assignment"
        and node["line"] == 50
        and node["signals"]
        == ["active_zero_evidence_tb.u_reduction_10ns.sample_vec_q"]
        and "|sample_vec_q" in node["text"]
        for node in response["data"]["trace"]["nodes"]
    )


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_uses_precise_fsdb_time_for_us_scale_reduction_output(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver",
        "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag",
        "10000ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["driver_status"] == "resolved"
    assert response["summary"]["active_time"] == "9995ns"
    assert response["summary"]["evidence_source"] == "fsdb_precise_time_static_trace"
    assert response["summary"]["static_candidate_count"] > 0
    assert response["summary"]["active_check_count"] > 0

    driver = response["data"]["driver"]
    assert driver["line"] == 167
    assert driver["signals"] == [
        "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag_expr"
    ]
    assert "sample_flag <= sample_flag_expr" in driver["text"]

    assert response["data"]["root_driver"]["line"] == 142
    assert any(
        node["kind"] == "assignment"
        and node["line"] == 142
        and node["signals"]
        == ["active_zero_evidence_tb.u_reduction_us_pulse.sample_vec_q"]
        and "|sample_vec_q" in node["text"]
        for node in response["data"]["trace"]["nodes"]
    )


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_uses_precise_fsdb_time_for_us_scale_reduction_output(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver_chain",
        "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag",
        "10000ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["termination"] != "unresolved"
    assert response["summary"]["termination"] != "ambiguous"
    assert response["data"]["chain"]["evidence_source"] == "fsdb_precise_time_static_trace"

    nodes = response["data"]["chain"]["chain"]
    assert len(nodes) >= 3
    assert nodes[0]["signal"] == "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag"
    assert nodes[0]["active_time"] == "9995ns"
    assert nodes[0]["line"] == 167
    assert nodes[0]["next"] == "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag_expr"
    assert nodes[1]["signal"] == "active_zero_evidence_tb.u_reduction_us_pulse.sample_flag_expr"
    assert nodes[1]["line"] == 142
    assert nodes[1]["next"] == (
        "active_zero_evidence_tb.u_reduction_us_pulse.sample_vec_q"
    )


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_reduction_output_zero_evidence_is_unresolved(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver",
        "active_zero_evidence_tb.u_reduction.sample_flag",
        "16ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["driver_status"] == "unresolved"
    assert response["data"]["driver"] is None
    assert response["data"]["root_driver"] is None
    assert response["data"]["trace"]["termination"] == "unresolved"
    assert any(
        "active trace returned no driver evidence" in item
        for item in response["data"]["limitations"]
    )


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_reduction_output_zero_evidence_is_unresolved(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver_chain",
        "active_zero_evidence_tb.u_reduction.sample_flag",
        "16ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["termination"] == "unresolved"
    nodes = response["data"]["chain"]["chain"]
    assert len(nodes) == 1
    assert nodes[0]["driver_kind"] == "unresolved"
    assert nodes[0]["driver"] == "(no driver)"


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_primitive_output_uses_real_evidence_not_fake_primary(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver_chain",
        "active_zero_evidence_tb.u_primitive.out_bufif",
        "16ns",
        artifact_root=artifact_root,
    )

    nodes = response["data"]["chain"]["chain"]
    assert not (
        response["summary"]["termination"] == "primary_input"
        and len(nodes) == 1
        and nodes[0]["driver"] == "(no driver)"
    )
    assert nodes[0]["driver_kind"] != "unresolved"


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_direct_module_input_follows_parent_connection(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver",
        "active_zero_evidence_tb.u_input_child.data_i",
        "16ns",
        artifact_root=artifact_root,
    )

    nodes = response["data"]["trace"]["nodes"]
    assert response["summary"]["driver_status"] == "resolved"
    assert response["data"]["root_driver"] is not None
    assert response["data"]["root_driver"]["kind"] != "primary_input"
    assert nodes[0]["signal"] == "active_zero_evidence_tb.u_input_child.data_i"
    assert nodes[0]["next_signal"] == "active_zero_evidence_tb.parent_src"
    assert any(node["signal"] == "active_zero_evidence_tb.parent_src" for node in nodes)
    assert not (
        response["data"]["trace"]["termination"] == "primary_input" and len(nodes) == 1
    )


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_direct_module_input_follows_parent_connection(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver_chain",
        "active_zero_evidence_tb.u_input_child.data_i",
        "16ns",
        artifact_root=artifact_root,
    )

    nodes = response["data"]["chain"]["chain"]
    assert len(nodes) >= 2
    assert nodes[0]["signal"] == "active_zero_evidence_tb.u_input_child.data_i"
    assert nodes[0]["next"] == "active_zero_evidence_tb.parent_src"
    assert nodes[0]["hop"] != "■"
    assert nodes[1]["signal"] == "active_zero_evidence_tb.parent_src"
    assert not (response["summary"]["termination"] == "primary_input" and len(nodes) == 1)


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_top_input_without_parent_connection_is_primary_input(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver",
        "active_zero_evidence_tb.top_input_i",
        "16ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["driver_status"] == "resolved"
    assert response["data"]["root_driver"]["kind"] == "primary_input"
    assert response["data"]["trace"]["termination"] == "primary_input"


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_top_input_without_parent_connection_is_primary_input(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    response = _query(
        cli_runner,
        active_zero_evidence_session,
        "trace.active_driver_chain",
        "active_zero_evidence_tb.top_input_i",
        "16ns",
        artifact_root=artifact_root,
    )

    assert response["summary"]["termination"] == "primary_input"
    nodes = response["data"]["chain"]["chain"]
    assert len(nodes) == 1
    assert nodes[0]["signal"] == "active_zero_evidence_tb.top_input_i"
    assert nodes[0]["hop"] == "■"


EXPR_ZERO_EVIDENCE_OUTPUTS = [
    "q_reduce_or",
    "q_reduce_and",
    "q_reduce_xor",
    "q_bit_or_ne0",
    "q_bit_and_ne0",
    "q_xor_reduce_mask",
    "q_logic_and",
    "q_logic_or",
    "q_reduce_and_enable",
    "q_ternary_reduce",
    "q_compare_ne0",
    "q_compare_eq_const",
    "q_compare_gt",
    "q_bit_select",
    "q_const_part_reduce",
    "q_indexed_part_reduce",
    "q_concat_reduce",
    "q_nested_mix",
]


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_expr_output_zero_evidence_is_unresolved(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    failures: list[str] = []
    for output_name in EXPR_ZERO_EVIDENCE_OUTPUTS:
        response = _query(
            cli_runner,
            active_zero_evidence_session,
            "trace.active_driver",
            f"active_zero_evidence_tb.u_expr.{output_name}",
            "16ns",
            artifact_root=artifact_root,
        )
        checks = [
            response["summary"]["driver_status"] == "unresolved",
            response["data"]["driver"] is None,
            response["data"]["root_driver"] is None,
            response["data"]["trace"]["termination"] == "unresolved",
            any(
                "active trace returned no driver evidence" in item
                for item in response["data"]["limitations"]
            ),
        ]
        if not all(checks):
            failures.append(
                "%s: status=%s driver=%s root=%s termination=%s limitations=%s"
                % (
                    output_name,
                    response["summary"]["driver_status"],
                    response["data"]["driver"],
                    response["data"]["root_driver"],
                    response["data"]["trace"]["termination"],
                    response["data"]["limitations"],
                )
            )
    assert not failures, "\n".join(failures)


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_driver_chain_expr_output_zero_evidence_is_unresolved(
    cli_runner: CliRunner,
    active_zero_evidence_session: str,
    artifact_root: Path,
) -> None:
    failures: list[str] = []
    for output_name in EXPR_ZERO_EVIDENCE_OUTPUTS:
        response = _query(
            cli_runner,
            active_zero_evidence_session,
            "trace.active_driver_chain",
            f"active_zero_evidence_tb.u_expr.{output_name}",
            "16ns",
            artifact_root=artifact_root,
        )
        nodes = response["data"]["chain"]["chain"]
        first = nodes[0] if nodes else {}
        checks = [
            response["summary"]["termination"] == "unresolved",
            len(nodes) == 1,
            first.get("driver_kind") == "unresolved",
            first.get("driver") == "(no driver)",
        ]
        if not all(checks):
            failures.append(
                "%s: termination=%s nodes=%s"
                % (output_name, response["summary"]["termination"], nodes[:1])
            )
    assert not failures, "\n".join(failures)
