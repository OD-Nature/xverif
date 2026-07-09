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


def _xout(
    cli_runner: CliRunner,
    request: dict[str, Any],
    *,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
) -> str:
    result = cli_runner.run(request, output_format="xout", timeout_sec=120)
    if result.returncode == 0 and not result.timed_out and isinstance(result.response, str):
        return result.response
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
        limits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "signal": signal,
            "time": requested_time,
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
                "time": requested_time,
                "clk_period": "10ns",
            },
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

    def active_driver_xout(signal: str, requested_time: str) -> str:
        request: dict[str, Any] = {
            "api_version": "xdebug.v1",
            "action": "trace.active_driver",
            "target": {"session_id": session_id},
            "args": {
                "signal": signal,
                "time": requested_time,
            },
        }
        return _xout(
            cli_runner,
            request,
            case_name="active-driver-xout-" + signal.rsplit(".", 1)[-1],
            artifact_root=artifact_root,
            extra={"marker_lines": marker_lines, "request": request},
        )

    def active_driver_chain_xout(signal: str, requested_time: str) -> str:
        request: dict[str, Any] = {
            "api_version": "xdebug.v1",
            "action": "trace.active_driver_chain",
            "target": {"session_id": session_id},
            "args": {
                "signal": signal,
                "time": requested_time,
                "clk_period": "10ns",
            },
        }
        return _xout(
            cli_runner,
            request,
            case_name="active-driver-chain-xout-" + signal.rsplit(".", 1)[-1],
            artifact_root=artifact_root,
            extra={"marker_lines": marker_lines, "request": request},
        )

    def _active_lines(item: dict[str, Any]) -> list[int]:
        return [
            row["line"]
            for row in item.get("source_context", [])
            if row.get("active") is True
        ]

    def _path_lines(response: dict[str, Any]) -> set[int]:
        lines: set[int] = set()
        for item in response.get("data", {}).get("paths", []):
            lines.update(_active_lines(item))
        return lines

    def _assert_source_paths(response: dict[str, Any], *, min_count: int = 1) -> None:
        paths = response.get("data", {}).get("paths", [])
        assert isinstance(paths, list)
        assert len(paths) >= min_count
        assert response["summary"]["path_count"] == len(paths)
        for item in paths:
            assert item.get("signal_path")
            assert _active_lines(item)

    def _assert_path_line(response: dict[str, Any], marker: str) -> None:
        _assert_source_paths(response)
        assert marker_lines[marker] in _path_lines(response)

    try:
        mux_b = active_driver("active_semantics_tb.u_dut.mux_y", "26ns")
        _assert_path_line(mux_b, "MUX_ACTIVE_B")
        assert marker_lines["MUX_ACTIVE_A"] not in _path_lines(mux_b)

        en_hold = active_driver("active_semantics_tb.u_dut.q_en", "26ns")
        _assert_path_line(en_hold, "ENABLE_Q_EN_DATA")
        assert en_hold["summary"]["active_time"] == "15ns"
        assert marker_lines["HOLD_Q_EN"] not in _path_lines(en_hold)

        handshake_hold = active_driver(
            "active_semantics_tb.u_dut.handshake_q", "26ns"
        )
        _assert_path_line(handshake_hold, "HANDSHAKE_PAYLOAD")
        assert handshake_hold["summary"]["active_time"] == "15ns"

        handshake_payload = active_driver(
            "active_semantics_tb.u_dut.handshake_q", "36ns"
        )
        _assert_path_line(handshake_payload, "HANDSHAKE_PAYLOAD")
        assert handshake_payload["summary"]["active_time"] == "35ns"

        arbiter_winner_1 = active_driver("active_semantics_tb.u_dut.arb_q", "26ns")
        _assert_path_line(arbiter_winner_1, "ARB_WINNER_1")
        assert marker_lines["ARB_WINNER_0"] not in _path_lines(arbiter_winner_1)

        arbiter_idle = active_driver("active_semantics_tb.u_dut.arb_q", "36ns")
        _assert_path_line(arbiter_idle, "ARB_IDLE")

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
        assert "text" not in chain["data"]
        assert "chain" not in chain["data"]
        assert chain["summary"]["hop_count"] == 4
        assert chain["summary"]["termination"] == "primary_input"
        hops = chain["data"]["hops"]
        assert [hop["index"] for hop in hops] == [0, 1, 2, 3]
        assert [_active_lines(hop)[0] for hop in hops] == [
            marker_lines["CHAIN_OUT_ASSIGN"],
            marker_lines["CHAIN_MID_ASSIGN"],
            marker_lines["CHAIN_SRC_DRIVE"],
            marker_lines["CHAIN_SRC_DRIVE"],
        ]
        for hop in hops:
            assert hop["signal_path"]

        active_xout = active_driver_xout("active_semantics_tb.u_dut.q_en", "16ns")
        assert active_xout.startswith("@xdebug.trace.active_driver.v1")
        assert "\nsummary:\n" in active_xout
        assert "\nsource: " in active_xout
        assert "\nactive_signals:\n" in active_xout
        assert "line  signal_path" in active_xout
        assert "\n>" in active_xout
        for removed_section in ("\ndriver:\n", "\ncontrols:\n", "\nevents:\n", "\nroot_cause:\n"):
            assert removed_section not in active_xout

        chain_xout = active_driver_chain_xout(
            "active_semantics_tb.u_dut.chain_out",
            "26ns",
        )
        assert chain_xout.startswith("@xdebug.trace.active_driver_chain.v1")
        assert "\nsummary:\n" in chain_xout
        assert "\nsource: " in chain_xout
        assert "\nactive_signals:\n" in chain_xout
        assert "hop  line  signal_path" in chain_xout
        assert "\n>" in chain_xout
        for removed_section in ("\nchain:\n", "\nstats:\n", "\nchain_path:\n"):
            assert removed_section not in chain_xout
        assert "\ntarget:\n" not in chain_xout
        assert "text:" not in chain_xout
        for expected_signal in [
            "active_semantics_tb.u_dut.chain_out",
            "active_semantics_tb.u_dut.chain_mid",
            "active_semantics_tb.u_dut.chain_src",
            "active_semantics_tb.chain_src",
        ]:
            assert expected_signal in chain_xout

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
                "target": {"session_id": session_id},
            },
            timeout_sec=60,
        )
