from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def test_rc_generate_preserves_struct_members_and_expression_aliases(
    cli_runner,
    xverif_fixture,
    tmp_path: Path,
) -> None:
    resources = xverif_fixture("xdebug.xif_event")
    fsdb = resources / "out/waves/xif_event_multi_if_test.fsdb"
    opened = cli_runner.run({
        "api_version": "xdebug.v1", "action": "session.open",
        "target": {"fsdb": str(fsdb)}, "args": {"name": "rc_struct_contract"},
    }, output_format="json")
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    target = {"session_id": opened.response["session"]["session_id"]}
    config_path, rc_path = tmp_path / "members.json", tmp_path / "members.rc"
    config = {"groups": [{
        "name": "Signals",
        "signals": ["xif_event_top.clk", "xif_event_top.if_rdy.pd",
                    "xif_event_top.if_rdy.pd.opcode", "xif_event_top.if_rdy.pd.opcode[3:0]"],
        "subgroups": [{"name": "Expressions", "expr_signals": [{
            "name": "opcode_expr", "bit_size": 8, "expr": "$opcode",
            "signals": {"opcode": "xif_event_top.if_rdy.pd.opcode"},
        }]}],
    }]}
    try:
        config_path.write_text(json.dumps(config), encoding="utf-8")
        request = {
            "api_version": "xdebug.v1", "action": "nwave.rc.generate", "target": target,
            "args": {"config_path": str(config_path), "output": {"path": str(rc_path)}},
        }
        result = cli_runner.run(request, output_format="json")
        assert result.ok, result.stdout_raw + result.stderr_raw
        lines = rc_path.read_text(encoding="utf-8").splitlines()
        assert "addSignal /xif_event_top/clk" in lines
        assert "addSignal /xif_event_top/if_rdy/pd" in lines
        assert "addSignal /xif_event_top/if_rdy/pd.opcode" in lines
        assert "addSignal /xif_event_top/if_rdy/pd.opcode[3:0]" in lines
        assert 'addExprSig -b 8 opcode_expr "/xif_event_top/if_rdy/pd.opcode"' in lines
        assert not any("/pd/" in line for line in lines)
        assert result.response["data"]["validation"] == {"signals": 5, "times": 0}

        # An unresolved expression operand must not silently create an empty
        # nWave expression or overwrite an already usable RC file.
        expression = config["groups"][0]["subgroups"][0]["expr_signals"][0]
        expression["signals"]["opcode"] = "xif_event_top.if_rdy.pd.missing_member"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        previous = rc_path.read_bytes()
        invalid = cli_runner.run(request, output_format="json")
        assert not invalid.ok
        assert invalid.response["error"]["code"] == "SIGNAL_NOT_FOUND"
        assert invalid.response["error"]["missing_name"] == expression["signals"]["opcode"]
        assert rc_path.read_bytes() == previous
    finally:
        closed = cli_runner.run({
            "api_version": "xdebug.v1", "action": "session.close", "target": target,
        }, output_format="json")
        assert closed.ok, closed.stdout_raw + closed.stderr_raw


def _query(
    binary: Path,
    home: Path,
    action: str,
    *,
    args: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    output_format: str = "json",
) -> dict[str, Any] | str:
    request: dict[str, Any] = {
        "api_version": "xdebug.v1",
        "action": action,
        "args": args or {},
    }
    if target is not None:
        request["target"] = target
    command = [str(binary)]
    if output_format == "json":
        command.append("--json")
    command.append("-")
    env = os.environ.copy()
    env["HOME"] = str(home)
    result = subprocess.run(
        command,
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT.parent,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if output_format == "xout":
        return result.stdout
    response = json.loads(result.stdout)
    assert response["ok"] is True, response
    return response


def test_xif_event_queries_published_fsdb(xverif_fixture) -> None:
    resources = xverif_fixture("xdebug.xif_event")
    script = ROOT / "testdata/waveform/xif_agent_event/scripts/check_event_waves.py"
    fsdb = resources / "out/waves/xif_event_multi_if_test.fsdb"
    result = subprocess.run(
        [
            "python3",
            str(script),
            "--xdebug",
            str(ROOT.parent / "tools/xdebug"),
            "--fsdb",
            str(fsdb),
        ],
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: xdebug event direct struct checks" in result.stdout


def test_event_find_preserves_canonical_json_and_flat_xout(
    xverif_fixture,
    tmp_path: Path,
) -> None:
    resources = xverif_fixture("xdebug.xif_event")
    fsdb = resources / "out/waves/xif_event_multi_if_test.fsdb"
    binary = ROOT.parent / "tools/xdebug"
    session_id = "xif_event_xout_contract"
    target = {"session_id": session_id}
    _query(
        binary,
        tmp_path,
        "session.open",
        args={"name": session_id},
        target={"fsdb": str(fsdb)},
    )
    try:
        _query(
            binary,
            tmp_path,
            "event.config.load",
            args={
                "name": "rdy",
                "config_path": str(
                    ROOT / "testdata/waveform/xif_agent_event/event_rdy.json"
                ),
            },
            target=target,
        )
        find_args = {
            "name": "rdy",
            "expr": "vld && rdy",
            "mode": "all",
            "line_limit": 2,
        }
        response = _query(
            binary,
            tmp_path,
            "event.find",
            args=find_args,
            target=target,
        )
        assert isinstance(response, dict)
        summary = response["summary"]
        for key in (
            "scan_complete",
            "analysis_complete",
            "response_truncated",
            "total_count",
            "returned_count",
            "truncation_scopes",
        ):
            assert key in summary
        for legacy in (
            "event_count",
            "returned_event_count",
            "truncated",
            "edge",
            "sample_point",
        ):
            assert legacy not in summary
        assert "sampling" in response["data"]
        assert "width_diagnostics" in summary

        xout = _query(
            binary,
            tmp_path,
            "event.find",
            args=find_args,
            target=target,
            output_format="xout",
        )
        assert isinstance(xout, str)
        assert xout.startswith("@xdebug.event.find.v1\n")
        for required in ("requested:", "effective:", "events:", "time", "vld", "rdy"):
            assert required in xout
        assert "8'h5a" in xout
        assert "16'ha55a" in xout
        for forbidden in (
            '"',
            ':{',
            ':[{',
            "known=true",
            "width_diagnostics",
            "XOUT_BEGIN",
            "XOUT_END",
            "pointer\tkind\tvalue",
        ):
            assert forbidden not in xout
        assert xout.endswith("\n") and not xout.endswith("\n\n")
    finally:
        _query(
            binary,
            tmp_path,
            "session.close",
            args={"mode": "force"},
            target={"session_id": "all"},
        )
