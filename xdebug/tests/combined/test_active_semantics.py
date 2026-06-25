from __future__ import annotations

import json
import re
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
    artifact_dir = ArtifactWriter(artifact_root).write(
        case_name,
        result,
        extra=extra,
    )
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


def _query(
    cli_runner: CliRunner,
    request: dict[str, Any],
    *,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = cli_runner.run(request, timeout_sec=120)
    return _require_success(
        result,
        case_name=case_name,
        artifact_root=artifact_root,
        extra=extra,
    )


def _marker_lines(source: Path) -> dict[str, int]:
    markers: dict[str, int] = {}
    pattern = re.compile(r"//\s*([A-Z][A-Z0-9_]+)")
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        match = pattern.search(line)
        if match:
            markers[match.group(1)] = line_no
    return markers


@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.synthetic
@pytest.mark.regression
@pytest.mark.slow
def test_active_trace_semantic_branches_and_gates(
    command_runner: CommandRunner,
    cli_runner: CliRunner,
    xdebug_root: Path,
    artifact_root: Path,
) -> None:
    fixture_dir = xdebug_root / "testdata" / "combined" / "active_semantics"
    source = fixture_dir / "active_semantics_tb.sv"
    marker_lines = _marker_lines(source)

    build = command_runner.run(
        ["make", "clean", "fixture"],
        cwd=fixture_dir,
        timeout_sec=600,
        metadata={"suite": "active-semantics"},
    )
    if build.returncode != 0 or build.timed_out:
        _require_success(
            build,
            case_name="active-semantics-build",
            artifact_root=artifact_root,
            extra={"source": source.read_text(encoding="utf-8")},
        )

    daidir = fixture_dir / "out" / "simv.daidir"
    fsdb = fixture_dir / "out" / "waves.fsdb"
    assert daidir.is_dir()
    assert fsdb.is_file() and fsdb.stat().st_size > 0

    open_response = _query(
        cli_runner,
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"daidir": str(daidir), "fsdb": str(fsdb)},
            "args": {"name": "active_semantics"},
        },
        case_name="active_semantics_session_open",
        artifact_root=artifact_root,
    )
    session = open_response.get("session") or open_response["data"]["session"]
    session_id = session["id"]

    def active_driver(
        signal: str,
        requested_time: str,
        *,
        include_trace: bool = True,
        limits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "signal": signal,
            "requested_time": requested_time,
            "include_trace": include_trace,
        }
        if limits is not None:
            args["limits"] = limits
        return _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "trace.active_driver",
                "target": {"session_id": session_id},
                "args": args,
                "output": {"verbosity": "compact"},
            },
            case_name="active-semantics-" + signal.rsplit(".", 1)[-1],
            artifact_root=artifact_root,
            extra={"marker_lines": marker_lines, "args": args},
        )

    def active_driver_chain(
        signal: str,
        requested_time: str,
        *,
        limits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "api_version": "xdebug.v1",
            "action": "trace.active_driver_chain",
            "target": {"session_id": session_id},
            "args": {
                "signal": signal,
                "requested_time": requested_time,
                "clk_period": "10ns",
            },
            "output": {"verbosity": "compact"},
        }
        if limits is not None:
            request["limits"] = limits
        return _query(
            cli_runner,
            request,
            case_name="active-chain-" + signal.rsplit(".", 1)[-1],
            artifact_root=artifact_root,
            extra={"marker_lines": marker_lines, "request": request},
        )

    try:
        mux_b = active_driver("active_semantics_tb.u_dut.mux_y", "26ns")
        assert mux_b["data"]["root_driver"]["line"] == marker_lines["MUX_ACTIVE_B"]
        assert mux_b["data"]["root_driver"]["line"] != marker_lines["MUX_ACTIVE_A"]

        en_hold = active_driver("active_semantics_tb.u_dut.q_en", "26ns")
        assert en_hold["data"]["root_driver"]["line"] == marker_lines["ENABLE_Q_EN_DATA"]
        assert en_hold["summary"]["active_time"] == "15ns"
        assert en_hold["summary"]["evidence_source"] == "fsdb_precise_time_static_trace"
        assert en_hold["data"]["root_driver"]["line"] != marker_lines["HOLD_Q_EN"]

        handshake_hold = active_driver(
            "active_semantics_tb.u_dut.handshake_q", "26ns"
        )
        assert (
            handshake_hold["data"]["root_driver"]["line"]
            == marker_lines["HANDSHAKE_PAYLOAD"]
        )
        assert handshake_hold["summary"]["active_time"] == "15ns"

        handshake_payload = active_driver(
            "active_semantics_tb.u_dut.handshake_q", "36ns"
        )
        assert (
            handshake_payload["data"]["root_driver"]["line"]
            == marker_lines["HANDSHAKE_PAYLOAD"]
        )
        assert handshake_payload["summary"]["active_time"] == "35ns"

        arbiter_winner_1 = active_driver("active_semantics_tb.u_dut.arb_q", "26ns")
        assert (
            arbiter_winner_1["data"]["root_driver"]["line"]
            == marker_lines["ARB_WINNER_1"]
        )
        assert (
            arbiter_winner_1["data"]["root_driver"]["line"]
            != marker_lines["ARB_WINNER_0"]
        )

        arbiter_idle = active_driver("active_semantics_tb.u_dut.arb_q", "36ns")
        assert arbiter_idle["data"]["root_driver"]["line"] == marker_lines["ARB_IDLE"]

        truncated = active_driver(
            "active_semantics_tb.u_dut.q_en",
            "16ns",
            limits={"max_nodes": 1},
        )
        assert truncated["meta"]["truncated"] is True

        chain = active_driver_chain(
            "active_semantics_tb.u_dut.chain_out",
            "26ns",
        )
        nodes = chain["data"]["chain"]["chain"]
        assert chain["summary"]["chain_length"] == 4
        assert chain["summary"]["termination"] == "primary_input"
        assert [node["signal"] for node in nodes] == [
            "active_semantics_tb.u_dut.chain_out",
            "active_semantics_tb.u_dut.chain_mid",
            "active_semantics_tb.u_dut.chain_src",
            "active_semantics_tb.chain_src",
        ]
        assert nodes[0]["line"] == marker_lines["CHAIN_OUT_ASSIGN"]
        assert nodes[1]["line"] == marker_lines["CHAIN_MID_ASSIGN"]
        assert nodes[2]["line"] == marker_lines["CHAIN_SRC_DRIVE"]
        assert nodes[3]["line"] == marker_lines["CHAIN_SRC_DRIVE"]
        assert nodes[0]["hop"] in {"→", "⏱"}
        assert nodes[1]["hop"] == "→"
        assert nodes[2]["hop"] == "→"
        assert nodes[3]["hop"] == "■"

        chain_limited = active_driver_chain(
            "active_semantics_tb.u_dut.chain_out",
            "26ns",
            limits={"max_depth": 8, "max_nodes": 1},
        )
        assert chain_limited["summary"]["termination"] == "limit"
        assert chain_limited["meta"]["truncated"] is True
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "args": {"id": session_id},
            },
            timeout_sec=60,
        )
