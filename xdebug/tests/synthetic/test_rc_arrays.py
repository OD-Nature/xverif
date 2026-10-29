from __future__ import annotations

import json
from pathlib import Path


def test_rc_array_roots_elements_members_and_slices(cli_runner, xverif_fixture, tmp_path: Path) -> None:
    fsdb = xverif_fixture("xdebug.rc_arrays") / "out/waves.fsdb"
    paths = [
        "packets", "packets[1]", "packets[0].header.opcode", "packets[1].header.opcode",
        "packets[1].header.opcode[3:0]", "packed_packets[1].header.opcode",
        "matrix[1][0].header.opcode", "packets[1].lanes[0]",
        "loose[1].tag", "loose[1].words[0]", "loose[1].words[1][7:0]",
    ]
    opened = cli_runner.run({
        "api_version": "xdebug.v1", "action": "session.open",
        "target": {"fsdb": str(fsdb)}, "args": {"name": "rc_arrays_contract"},
    }, output_format="json")
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    target = {"session_id": opened.response["session"]["session_id"]}
    try:
        config, output = tmp_path / "arrays.json", tmp_path / "arrays.rc"
        config.write_text(json.dumps({"groups": [{
            "name": "Arrays", "signals": ["rc_arrays_tb." + p for p in paths],
            "subgroups": [{"name": "Expressions", "expr_signals": [{
                "name": "array_expr", "bit_size": 8, "expr": "$field",
                "signals": {"field": "rc_arrays_tb.matrix[1][0].header.opcode"},
            }]}],
        }]}), encoding="utf-8")
        result = cli_runner.run({
            "api_version": "xdebug.v1", "action": "nwave.rc.generate", "target": target,
            "args": {"config_path": str(config), "output": {"path": str(output)}},
        }, output_format="json")
        assert result.ok, result.stdout_raw + result.stderr_raw
        lines = output.read_text(encoding="utf-8").splitlines()
        for path in paths:
            assert "addSignal /rc_arrays_tb/" + path in lines
        assert 'addExprSig -b 8 array_expr "/rc_arrays_tb/matrix[1][0].header.opcode"' in lines
        assert lines[-1] == 'endSubGroup "Expressions"'
        assert result.response["data"]["validation"]["signals"] == len(paths) + 1
    finally:
        closed = cli_runner.run({
            "api_version": "xdebug.v1", "action": "session.close", "target": target,
        }, output_format="json")
        assert closed.ok, closed.stdout_raw + closed.stderr_raw


def test_rc_enum_paths_preserve_default_and_explicit_radix(cli_runner, xverif_fixture, tmp_path: Path) -> None:
    fsdb = xverif_fixture("xdebug.rc_arrays") / "out/waves.fsdb"
    enum_paths = [
        "enum_state", "enum_packet.state", "enum_packets[0].state",
        "enum_packets[1].state", "enum_states[0]", "enum_states[1]",
    ]
    numeric_paths = ["enum_state[0]", "enum_state[1:0]", "enum_state_bit", "enum_state_slice"]
    opened = cli_runner.run({
        "api_version": "xdebug.v1", "action": "session.open",
        "target": {"fsdb": str(fsdb)}, "args": {"name": "rc_enum_contract"},
    }, output_format="json")
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    target = {"session_id": opened.response["session"]["session_id"]}
    try:
        config, output = tmp_path / "enums.json", tmp_path / "enums.rc"
        config.write_text(json.dumps({"groups": [
            {"name": "Default", "signals": ["rc_arrays_tb." + p for p in enum_paths + numeric_paths]},
            {"name": "Styled", "signals": [
                {"path": "rc_arrays_tb." + p, "height": 24} for p in enum_paths
            ]},
            {"name": "ExplicitHex", "signals": [
                {"path": "rc_arrays_tb." + p, "radix": "hex"} for p in enum_paths
            ]},
        ]}), encoding="utf-8")
        result = cli_runner.run({
            "api_version": "xdebug.v1", "action": "nwave.rc.generate", "target": target,
            "args": {"config_path": str(config), "output": {"path": str(output)}},
        }, output_format="json")
        assert result.ok, result.stdout_raw + result.stderr_raw
        lines = output.read_text(encoding="utf-8").splitlines()
        # nWave restores enum literals when a row has no numeric radix override.
        # String/object configs must preserve that default, including struct and array members.
        for path in enum_paths + numeric_paths:
            assert "addSignal /rc_arrays_tb/" + path in lines
        for path in enum_paths:
            assert "addSignal -h 24 /rc_arrays_tb/" + path in lines
            assert "addSignal -HEX /rc_arrays_tb/" + path in lines
        assert result.response["data"]["validation"]["signals"] == 3 * len(enum_paths) + len(numeric_paths)
    finally:
        closed = cli_runner.run({
            "api_version": "xdebug.v1", "action": "session.close", "target": target,
        }, output_format="json")
        assert closed.ok, closed.stdout_raw + closed.stderr_raw
