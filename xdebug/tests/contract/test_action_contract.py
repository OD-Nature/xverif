from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

import jsonschema
import pytest

from runner import CliRunner


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_catalog(cli_runner: CliRunner) -> Dict[str, Any]:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "actions",
            "args": {"output": {"verbose": True}},
        },
        output_format="json",
    )
    assert result.ok, result.stderr_raw
    return result.response


def _request_schema_args_required(schema: Dict[str, Any]) -> list[str]:
    args_schema = schema.get("properties", {}).get("args", {})
    return list(args_schema.get("required", []))


def _example_satisfies_groups(args: Dict[str, Any], groups: list[list[str]]) -> bool:
    return any(all(key in args for key in group) for group in groups)


def _required_related_args(spec: Dict[str, Any]) -> set[str]:
    keys = set(spec.get("required_args", []))
    for group in spec.get("required_arg_groups", []):
        keys.update(group)
    for conditional in spec.get("conditional_required_args", []):
        keys.update(conditional.get("when", {}).keys())
        keys.update(conditional.get("required", []))
    return keys


@pytest.mark.contract
def test_runtime_catalog_matches_specs_and_referenced_files(
    cli_runner: CliRunner, xdebug_root: Path
) -> None:
    catalog = _runtime_catalog(cli_runner)
    specs = _load_json(xdebug_root / "specs" / "actions" / "actions.yaml")[
        "actions"
    ]
    specs_by_name = {spec["name"]: spec for spec in specs}
    descriptors = {
        descriptor["name"]: descriptor
        for descriptor in catalog["data"]["actions"]
    }

    expected_implemented = {
        name for name, spec in specs_by_name.items() if spec["status"] != "removed"
    }
    expected_removed = {
        name for name, spec in specs_by_name.items() if spec["status"] == "removed"
    }
    assert set(catalog["data"]["removed"]) == expected_removed
    assert set(descriptors) == expected_implemented

    for name, descriptor in descriptors.items():
        spec = specs_by_name[name]
        assert descriptor["category"] == spec["category"]
        assert descriptor["status"] == spec["status"]
        assert descriptor["requires"] == spec["requires"]
        assert descriptor["handler_kind"] == spec["handler_kind"]
        assert descriptor["request_schema"] == spec["schemas"]["request"]
        assert descriptor["response_schema"] == spec["schemas"]["response"]
        assert descriptor["request_examples"] == spec["examples"]["request"]
        assert set(spec["examples"]["response"]).issubset(
            descriptor["response_examples"]
        )
        for reference in (
            descriptor["request_schema"],
            descriptor["response_schema"],
            *descriptor["request_examples"],
            *descriptor["response_examples"],
        ):
            assert (xdebug_root / reference).is_file(), reference


@pytest.mark.contract
def test_runtime_catalog_default_is_compact_without_duplicate_names(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(
        {"api_version": "xdebug.v1", "action": "actions", "args": {}},
        output_format="json",
    )
    assert result.ok, result.response
    assert result.response["summary"]["verbose"] is False
    assert "implemented" not in result.response["data"]
    assert result.response["data"]["actions"]
    assert all(isinstance(name, str) for name in result.response["data"]["actions"])


@pytest.mark.contract
def test_runtime_schema_unknown_action_suggests_nearby_names(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "schema",
            "args": {"action": "value.batc_at", "kind": "request"},
        },
        output_format="json",
    )
    assert result.returncode == 1
    error = result.response["error"]
    assert error["code"] == "UNKNOWN_ACTION"
    assert error["error_layer"] == "handler"
    assert error["did_you_mean"] == "value.batch_at"
    assert "value.batch_at" in error["suggested_actions"]


@pytest.mark.contract
def test_runtime_unknown_action_suggests_nearby_names(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(
        {"api_version": "xdebug.v1", "action": "signal.statistcs", "args": {}},
        output_format="json",
    )
    assert result.returncode == 1
    error = result.response["error"]
    assert error["code"] == "UNKNOWN_ACTION"
    assert error["error_layer"] == "handler"
    assert error["did_you_mean"] == "signal.statistics"
    assert "signal.statistics" in error["suggested_actions"]

@pytest.mark.contract
def test_action_required_args_match_runtime_schema_and_examples(
    cli_runner: CliRunner, xdebug_root: Path
) -> None:
    catalog = _runtime_catalog(cli_runner)
    specs = _load_json(xdebug_root / "specs" / "actions" / "actions.yaml")[
        "actions"
    ]
    descriptors = {
        descriptor["name"]: descriptor
        for descriptor in catalog["data"]["actions"]
    }

    for spec in specs:
        if spec["status"] == "removed":
            continue
        name = spec["name"]
        required_args = list(spec.get("required_args", []))
        descriptor = descriptors[name]
        assert list(descriptor.get("required_args", [])) == required_args

        request_schema = _load_json(xdebug_root / spec["schemas"]["request"])
        assert _request_schema_args_required(request_schema) == required_args

        for example_ref in spec["examples"]["request"]:
            example = _load_json(xdebug_root / example_ref)
            args = example.get("args", {})
            for key in required_args:
                assert key in args, "%s example is missing args.%s" % (name, key)
            for group in spec.get("required_arg_groups", []):
                assert _example_satisfies_groups(args, [group]) or _example_satisfies_groups(
                    args, spec["required_arg_groups"]
                ), "%s example does not satisfy any required_arg_groups" % name
            for conditional in spec.get("conditional_required_args", []):
                when = conditional.get("when", {})
                if all(args.get(key) == value for key, value in when.items()):
                    for key in conditional.get("required", []):
                        assert key in args, "%s example is missing conditional args.%s" % (
                            name,
                            key,
                        )


@pytest.mark.contract
def test_action_schema_hints_are_synced(xdebug_root: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(xdebug_root / "tools" / "sync_action_schema_hints.py"),
            "--check",
        ],
        cwd=xdebug_root.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.contract
def test_runtime_request_schemas_are_strict_and_synced(xdebug_root: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(xdebug_root / "tools" / "sync_runtime_request_schemas.py"),
            "--check",
        ],
        cwd=xdebug_root.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    specs = _load_json(xdebug_root / "specs" / "actions" / "actions.yaml")[
        "actions"
    ]
    for spec in specs:
        if spec["status"] == "removed":
            continue
        schema = _load_json(xdebug_root / spec["schemas"]["request"])
        assert schema.get("additionalProperties") is False, spec["name"]
        args_schema = schema.get("properties", {}).get("args", {})
        assert args_schema.get("additionalProperties") is False, spec["name"]


@pytest.mark.contract
def test_waveform_expression_contract_schemas_are_strict(xdebug_root: Path) -> None:
    value_batch_schema = _load_json(
        xdebug_root / "schemas" / "v1" / "actions" / "value.batch_at.request.schema.json"
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {
                "api_version": "xdebug.v1",
                "action": "value.batch_at",
                "args": {
                    "signals": {"a": "top.u.a"},
                    "time": "10ns",
                    "clock": "top.u.clk",
                },
            },
            value_batch_schema,
        )

    for action in ("verify.conditions", "window.verify"):
        schema = _load_json(
            xdebug_root / "schemas" / "v1" / "actions" / f"{action}.request.schema.json"
        )
        args = {
            "clock": "top.u.clk",
            "signals": {"a": "top.u.a"},
            "conditions": [{}],
        }
        if action == "verify.conditions":
            args["time"] = "10ns"
        else:
            args["time_range"] = {"begin": "0ns", "end": "10ns"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "api_version": "xdebug.v1",
                    "action": action,
                    "args": args,
                },
                schema,
            )


@pytest.mark.contract
def test_bad_parameter_schema_errors_include_ai_repair_hints(
    cli_runner: CliRunner,
) -> None:
    cases = [
        (
            {
                "api_version": "xdebug.v1",
                "action": "apb.query",
                "args": {"name": "apb0", "direction": "read", "limit": 10},
            },
            "args.limit",
            "args.query.line_limit",
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "event.find",
                "args": {"expr": "valid"},
            },
            "args",
            None,
            ["args.name", "args.clock + args.signals"],
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "args": {},
            },
            "args",
            None,
            ["args.streams", "args.config", "args.config_path", "args.file"],
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "trace.active_driver_chain",
                "args": {"signal": "top.q", "time": "10ns", "depth": 4},
            },
            "args.depth",
            "limits.max_depth",
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "args": {"name": "req_stream", "query": "summary"},
            },
            "args.name",
            "args.stream",
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "session.doctor",
                "target": {"session_id": 123},
            },
            "target.session_id",
            None,
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "session.list",
                "target": {"session_id": 123},
            },
            "target.session_id",
            None,
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "axi.channel_stall",
                "args": {"name": "if0", "channel": "zz"},
            },
            "args.channel",
            None,
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "trace.active_driver",
                "args": {"signal": "top.q", "time": "10ns", "include_trace": True},
            },
            "args.include_trace",
            None,
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "source.context",
                "args": {"file": "rtl/foo.sv", "line": 1, "include_source": True},
            },
            "args.include_source",
            None,
            None,
        ),
        (
            {
                "api_version": "xdebug.v1",
                "action": "event.find",
                "args": {
                    "expr": "valid",
                    "clock": "top.clk",
                    "signals": {"valid": "top.valid"},
                    "time_range": {"start": "0ns", "end": "10ns"},
                },
            },
            "args.time_range.start",
            "args.time_range.begin",
            None,
        ),
    ]
    for request, invalid_arg, did_you_mean, required_any_of in cases:
        result = cli_runner.run(request, output_format="json")
        assert not result.ok, request
        error = result.response["error"]
        assert error["code"] == "INVALID_REQUEST"
        assert error["error_layer"] == "schema"
        assert error["invalid_arg"] == invalid_arg
        assert "correct_example" in error
        assert "data" not in result.response or result.response["data"] is None
        assert invalid_arg in error["message"]
        if did_you_mean is not None:
            assert error["did_you_mean"] == did_you_mean
            assert did_you_mean in error["message"]
        if required_any_of is not None:
            assert error["required_any_of"] == required_any_of
            for item in required_any_of:
                assert item in error["message"]


@pytest.mark.contract
def test_all_actions_unknown_args_report_correct_example(
    cli_runner: CliRunner,
) -> None:
    catalog = _runtime_catalog(cli_runner)
    for descriptor in catalog["data"]["actions"]:
        action = descriptor["name"]
        request = {
            "api_version": "xdebug.v1",
            "action": action,
            "args": {"__bad_param__": True},
        }
        result = cli_runner.run(request, output_format="json")
        assert not result.ok, action
        error = result.response["error"]
        assert error["code"] == "INVALID_REQUEST", action
        assert error["error_layer"] == "schema", action
        assert "invalid_arg" in error, action
        assert "correct_example" in error, action


@pytest.mark.contract
def test_schema_error_has_canonical_shape_and_all_validation_issues(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "stream.show",
            "args": {"__bad_param__": True},
        },
        output_format="json",
    )
    assert not result.ok
    response = result.response
    assert response["summary"] == {
        "status": "error",
        "error_code": "INVALID_REQUEST",
    }
    assert response.get("data") is None
    error = response["error"]
    assert error["error_layer"] == "schema"
    assert len(error["validation_issues"]) >= 2
    assert error.get("did_you_mean") != error["invalid_arg"]


@pytest.mark.contract
def test_schema_handler_enum_error_uses_diagnostic_error(cli_runner: CliRunner) -> None:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "schema",
            "args": {"action": "value.batch_at", "kind": "bad_kind"},
        },
        output_format="json",
    )
    assert not result.ok
    error = result.response["error"]
    assert error["code"] == "INVALID_ENUM"
    assert error["error_layer"] == "handler"
    assert error["invalid_arg"] == "args.kind"
    assert error["allowed_values"] == ["request", "response"]
    assert error["received"] == "bad_kind"
    assert "example_note" in error
    assert error["correct_example"]["args"]["kind"] == "request"
    assert "data" not in result.response or result.response["data"] is None


@pytest.mark.contract
def test_bad_parameter_xout_shows_correct_example(cli_runner: CliRunner) -> None:
    result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "apb.query",
            "args": {"name": "apb0", "direction": "read", "limit": 10},
        },
        output_format="xout",
    )
    assert not result.ok
    assert "invalid_arg" in result.stdout_raw
    assert "args.limit" in result.stdout_raw
    assert "did_you_mean" in result.stdout_raw
    assert "args.query.line_limit" in result.stdout_raw
    assert "correct_example" in result.stdout_raw


@pytest.mark.contract
def test_bad_parameter_runtime_errors_include_ai_repair_hints(
    cli_runner: CliRunner,
    complex_wave_fsdb: Path,
) -> None:
    fsdb = complex_wave_fsdb
    session_name = "bad_param_runtime_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        cases = [
            {
                "api_version": "xdebug.v1",
                "action": "window.verify",
                "target": target,
                "args": {
                    "clock": "ai_complex_top.clk",
                    "signals": {"a": "ai_complex_top.sig_a"},
                    "conditions": [
                        {
                            "expr": "a == 8'h22",
                            "mode": "always",
                        }
                    ],
                    "time_range": {"begin": "100ns", "end": "0ns"},
                },
            },
            {
                "api_version": "xdebug.v1",
                "action": "counter.statistics",
                "target": target,
                "args": {
                    "clock": "ai_complex_top.clk",
                    "time_range": {"begin": "100ns", "end": "0ns"},
                    "vld": {"expr": "vld", "signals": {"vld": "ai_complex_top.sig_valid"}},
                    "cnt": "ai_complex_top.sig_a",
                },
            },
        ]
        for request in cases:
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == "TIME_RANGE_INVALID"
            assert error["invalid_arg"] == "args.time_range.end"
            assert "correct_example" in error
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_stream_handler_errors_include_current_entry_examples(
    cli_runner: CliRunner,
    xdebug_root: Path,
    stream_wave_fsdb: Path,
) -> None:
    fsdb = stream_wave_fsdb
    session_name = "stream_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        config_path = xdebug_root / "testdata" / "waveform" / "stream_v1" / "config" / "streams.json"
        loaded = cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "target": target,
                "args": {"config_path": str(config_path)},
            },
            output_format="json",
            timeout_sec=120,
        )
        assert loaded.ok, loaded.stdout_raw + loaded.stderr_raw
        cases = [
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.config.list",
                    "target": target,
                    "args": {"name": "missing_stream"},
                },
                "args.name",
                "stream.config.list",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.show",
                    "target": target,
                    "args": {"stream": "missing_stream"},
                },
                "args.stream",
                "stream.show",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": "ready_stream",
                        "query": "summary",
                        "time_range": {"begin": "not_time", "end": "100ns"},
                    },
                },
                "args.time_range.begin",
                "stream.query",
                "INVALID_TIME",
            ),
        ]
        for case in cases:
            if len(case) == 3:
                request, invalid_arg, example_action = case
                code = "CONFIG_NOT_FOUND"
            else:
                request, invalid_arg, example_action, code = case
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == code
            assert error["error_layer"] == "handler"
            assert error["invalid_arg"] == invalid_arg
            if code == "CONFIG_NOT_FOUND":
                assert error["missing_resource"] == "stream config"
            assert "next_actions" in error
            assert "example_note" in error
            assert error["correct_example"]["action"] == example_action
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_list_handler_errors_include_current_entry_examples(
    cli_runner: CliRunner,
    complex_wave_fsdb: Path,
) -> None:
    fsdb = complex_wave_fsdb
    session_name = "list_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        create = cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "list.create",
                "target": target,
                "args": {"name": "list_contract"},
            },
            output_format="json",
            timeout_sec=120,
        )
        assert create.ok, create.stdout_raw + create.stderr_raw
        cases = [
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "list.show",
                    "target": target,
                    "args": {"name": "missing_list"},
                },
                "LIST_NOT_FOUND",
                "args.name",
                "list.show",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "list.add",
                    "target": target,
                    "args": {"name": "list_contract", "signal": "ai_complex_top.no_such"},
                },
                "SIGNAL_NOT_FOUND",
                "args.signal",
                "list.add",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "list.delete",
                    "target": target,
                    "args": {"name": "list_contract", "index": 1},
                },
                "PRECONDITION_FAILED",
                "args.index",
                "list.delete",
            ),
        ]
        for request, code, invalid_arg, example_action in cases:
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == code
            assert error["error_layer"] == "handler"
            assert error["invalid_arg"] == invalid_arg
            assert "expected" in error
            assert "example_note" in error
            assert error["correct_example"]["action"] == example_action
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_event_handler_errors_include_current_entry_examples(
    cli_runner: CliRunner,
    complex_wave_fsdb: Path,
) -> None:
    fsdb = complex_wave_fsdb
    session_name = "event_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        cases = [
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "event.find",
                    "target": target,
                    "args": {"name": "missing_event", "expr": "valid"},
                },
                "CONFIG_NOT_FOUND",
                "args.name",
                "event.find",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "event.find",
                    "target": target,
                    "args": {
                        "clock": "ai_complex_top.clk",
                        "signals": {"valid": "ai_complex_top.sig_valid"},
                        "expr": "ai_complex_top.sig_valid",
                    },
                },
                "INVALID_ARGUMENT",
                "args.expr",
                "event.find",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "event.find",
                    "target": target,
                    "args": {
                        "clock": "ai_complex_top.clk",
                        "signals": {"valid": "ai_complex_top.sig_valid"},
                        "expr": "valid",
                        "mode": "middle",
                    },
                },
                "INVALID_ENUM",
                "args.mode",
                "event.find",
            ),
        ]
        for request, code, invalid_arg, example_action in cases:
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == code
            assert error["error_layer"] == "handler"
            assert error["invalid_arg"] == invalid_arg
            assert "expected" in error
            assert "example_note" in error
            assert error["correct_example"]["action"] == example_action
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_value_and_verify_handler_errors_include_current_entry_examples(
    cli_runner: CliRunner,
    complex_wave_fsdb: Path,
) -> None:
    fsdb = complex_wave_fsdb
    session_name = "value_verify_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        cases = [
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "value.at",
                    "target": target,
                    "args": {
                        "signal": "ai_complex_top.no_such_signal",
                        "time": "10ns",
                        "clock": "ai_complex_top.clk",
                    },
                },
                "SIGNAL_NOT_FOUND",
                "args.signal",
                "value.at",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "value.batch_at",
                    "target": target,
                    "args": {
                        "signals": ["ai_complex_top.sig_valid"],
                        "time": "not_time",
                        "clock": "ai_complex_top.clk",
                    },
                },
                "INVALID_TIME",
                "args.time",
                "value.batch_at",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "verify.conditions",
                    "target": target,
                    "args": {
                        "clock": "ai_complex_top.clk",
                        "time": "10ns",
                        "signals": {"valid": "ai_complex_top.sig_valid"},
                        "conditions": [{"expr": "ai_complex_top.sig_valid"}],
                    },
                },
                "INVALID_ARGUMENT",
                "args.conditions[].expr",
                "verify.conditions",
            ),
        ]
        for request, code, invalid_arg, example_action in cases:
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == code
            assert error["error_layer"] == "handler"
            assert error["invalid_arg"] == invalid_arg
            assert "expected" in error
            assert "correct_example" in error
            assert error["correct_example"]["action"] == example_action
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_protocol_handler_errors_include_current_entry_examples(
    cli_runner: CliRunner,
    complex_wave_fsdb: Path,
) -> None:
    fsdb = complex_wave_fsdb
    session_name = "protocol_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        cases = [
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "axi.config.list",
                    "target": target,
                    "args": {"name": "missing_axi"},
                },
                "CONFIG_NOT_FOUND",
                "args.name",
                "axi.config.list",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "apb.config.list",
                    "target": target,
                    "args": {"name": "missing_apb"},
                },
                "CONFIG_NOT_FOUND",
                "args.name",
                "apb.config.list",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "axi.config.load",
                    "target": target,
                    "args": {"name": "bad_axi", "config": {"clk": "top.clk"}},
                },
                "INVALID_ARGUMENT",
                "config.clk",
                "axi.config.load",
            ),
            (
                {
                    "api_version": "xdebug.v1",
                    "action": "axi.export",
                    "target": target,
                    "args": {
                        "name": "missing_axi",
                        "time_range": {"begin": "0ns", "end": "10ns"},
                        "output": {"file_format": "tsv"},
                    },
                },
                "CONFIG_NOT_FOUND",
                "args.name",
                "axi.export",
            ),
        ]
        for request, code, invalid_arg, example_action in cases:
            result = cli_runner.run(request, output_format="json", timeout_sec=120)
            assert not result.ok, result.stdout_raw + result.stderr_raw
            error = result.response["error"]
            assert error["code"] == code
            assert error["error_layer"] == "handler"
            assert error["invalid_arg"] == invalid_arg
            assert "expected" in error
            assert "correct_example" in error
            assert error["correct_example"]["action"] == example_action
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_rc_and_source_handler_errors_include_repair_hints(
    cli_runner: CliRunner,
    xdebug_root: Path,
    complex_wave_fsdb: Path,
) -> None:
    source_result = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "source.context",
            "args": {"file": "/tmp/xdebug_missing_source_for_contract.sv", "line": 1},
        },
        output_format="json",
    )
    assert not source_result.ok
    source_error = source_result.response["error"]
    assert source_error["code"] == "SOURCE_NOT_FOUND"
    assert source_error["error_layer"] == "handler"
    assert source_error["invalid_arg"] == "args.file"
    assert source_error["missing_resource"] == "source file"

    fsdb = complex_wave_fsdb
    session_name = "rc_error_contract"
    opened = cli_runner.run(
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": session_name},
        },
        output_format="json",
        timeout_sec=120,
    )
    assert opened.ok, opened.stdout_raw + opened.stderr_raw
    session = opened.response.get("session") or opened.response["data"]["session"]
    target = {"session_id": session.get("id") or session.get("session_id") or session_name}
    try:
        rc_result = cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "rc.generate",
                "target": target,
                "args": {"config_path": "/tmp/xdebug_missing_rc_config.json", "output": {}},
            },
            output_format="json",
            timeout_sec=120,
        )
        assert not rc_result.ok
        rc_error = rc_result.response["error"]
        assert rc_error["code"] == "MISSING_FIELD"
        assert rc_error["error_layer"] == "handler"
        assert rc_error["invalid_arg"] == "args.output.path"
        assert "correct_example" in rc_error
        assert "example_note" in rc_error
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.close",
                "target": target,
            },
            output_format="json",
            timeout_sec=120,
        )


@pytest.mark.contract
def test_action_schemas_explain_purpose_and_required_args(xdebug_root: Path) -> None:
    specs = _load_json(xdebug_root / "specs" / "actions" / "actions.yaml")[
        "actions"
    ]
    for spec in specs:
        if spec["status"] == "removed":
            continue
        name = spec["name"]
        request_schema = _load_json(xdebug_root / spec["schemas"]["request"])
        response_schema = _load_json(xdebug_root / spec["schemas"]["response"])

        for key in ("description", "x-purpose", "x-how_it_works", "x-when_to_use"):
            assert request_schema.get(key), "%s request schema missing %s" % (
                name,
                key,
            )
        assert response_schema.get("description"), "%s response schema missing description" % name

        args_properties = (
            request_schema.get("properties", {})
            .get("args", {})
            .get("properties", {})
        )
        for key in _required_related_args(spec):
            assert args_properties.get(key, {}).get("description"), (
                "%s request schema missing args.%s description" % (name, key)
            )


@pytest.mark.contract
def test_runtime_modes_are_derived_from_action_categories(
    cli_runner: CliRunner,
) -> None:
    catalog = _runtime_catalog(cli_runner)
    expected = defaultdict(set)
    for descriptor in catalog["data"]["actions"]:
        expected[descriptor["category"]].add(descriptor["name"])
    actual = {
        category: set(actions)
        for category, actions in catalog["data"]["modes"].items()
    }
    for category in ("builtin", "session", "design", "waveform", "combined"):
        assert actual[category] == expected[category]


@pytest.mark.contract
def test_action_inventory_matches_specs(xdebug_root: Path) -> None:
    specs = _load_json(xdebug_root / "specs" / "actions" / "actions.yaml")[
        "actions"
    ]
    expected = {
        spec["name"]: (spec["category"], spec["status"], spec["requires"])
        for spec in specs
    }
    inventory_text = (xdebug_root / "docs" / "action-inventory.md").read_text(
        encoding="utf-8"
    )
    actual = {}
    row_pattern = re.compile(
        r"^\|\s*`([^`]+)`\s*\|\s*([^\n|]+?)\s*\|\s*([^\n|]+?)\s*\|"
        r"\s*([^\n|]+?)\s*\|",
        re.MULTILINE,
    )
    for match in row_pattern.finditer(inventory_text):
        name, category, status, requires = (
            item.strip() for item in match.groups()
        )
        if category not in {"builtin", "session", "design", "waveform", "combined"}:
            continue
        actual[name] = (category, status, requires)
    assert actual == expected


@pytest.mark.contract
def test_runtime_schema_action_returns_exact_checked_in_schema(
    cli_runner: CliRunner, xdebug_root: Path
) -> None:
    catalog = _runtime_catalog(cli_runner)
    for descriptor in catalog["data"]["actions"]:
        for kind in ("request", "response"):
            result = cli_runner.run(
                {
                    "api_version": "xdebug.v1",
                    "action": "schema",
                    "args": {"action": descriptor["name"], "kind": kind},
                },
                output_format="json",
            )
            assert result.ok, (descriptor["name"], kind, result.response)
            schema_path = xdebug_root / descriptor["%s_schema" % kind]
            assert result.response["data"]["schema_path"] == descriptor[
                "%s_schema" % kind
            ]
            assert result.response["data"]["schema"] == _load_json(schema_path)


@pytest.mark.contract
def test_all_examples_validate_against_action_schemas(xdebug_root: Path) -> None:
    for kind in ("request", "response"):
        for example_path in sorted((xdebug_root / "examples" / (kind + "s")).glob("*.json")):
            example = _load_json(example_path)
            action = example["action"]
            schema = _load_json(
                xdebug_root
                / "schemas"
                / "v1"
                / "actions"
                / ("%s.%s.schema.json" % (action, kind))
            )
            jsonschema.Draft202012Validator(schema).validate(example)


@pytest.mark.contract
def test_stream_query_match_schema_rejects_legacy_field_shorthand(
    xdebug_root: Path,
) -> None:
    schema = _load_json(
        xdebug_root / "schemas" / "v1" / "actions" / "stream.query.request.schema.json"
    )
    validator = jsonschema.Draft202012Validator(schema)
    valid = {
        "api_version": "xdebug.v1",
        "action": "stream.query",
        "args": {
            "stream": "req_stream",
            "query": "match_field",
            "match": {"field": "opcode", "op": "==", "value": "8'h5a"},
        },
    }
    validator.validate(valid)

    legacy = {
        "api_version": "xdebug.v1",
        "action": "stream.query",
        "args": {
            "stream": "req_stream",
            "query": "match_field",
            "match": {"opcode": "8'h5a"},
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(legacy)


@pytest.mark.contract
def test_ai_usability_high_risk_request_shapes_are_strict(
    xdebug_root: Path,
) -> None:
    def schema_for(action: str) -> Dict[str, Any]:
        return _load_json(
            xdebug_root
            / "schemas"
            / "v1"
            / "actions"
            / ("%s.request.schema.json" % action)
        )

    apb = jsonschema.Draft202012Validator(schema_for("apb.query"))
    apb.validate({
        "api_version": "xdebug.v1",
        "action": "apb.query",
        "args": {"name": "apb0", "direction": "read", "query": {"index": 1, "line_limit": 1}},
    })
    with pytest.raises(jsonschema.ValidationError):
        apb.validate({
            "api_version": "xdebug.v1",
            "action": "apb.query",
            "args": {"name": "apb0", "direction": "read", "num": 1},
        })
    with pytest.raises(jsonschema.ValidationError):
        apb.validate({
            "api_version": "xdebug.v1",
            "action": "apb.query",
            "args": {"name": "apb0", "direction": "read", "limit": 1},
        })
    with pytest.raises(jsonschema.ValidationError):
        apb.validate({
            "api_version": "xdebug.v1",
            "action": "apb.query",
            "args": {"name": "apb0", "direction": "read", "query": {"limit": 1}},
        })
    with pytest.raises(jsonschema.ValidationError):
        apb.validate({
            "api_version": "xdebug.v1",
            "action": "apb.query",
            "args": {"name": "apb0", "direction": "all"},
        })

    axi = jsonschema.Draft202012Validator(schema_for("axi.query"))
    axi.validate({
        "api_version": "xdebug.v1",
        "action": "axi.query",
        "args": {"name": "axi0", "direction": "write", "query": {"index": 1, "line_limit": 1}},
    })
    with pytest.raises(jsonschema.ValidationError):
        axi.validate({
            "api_version": "xdebug.v1",
            "action": "axi.query",
            "args": {"name": "axi0", "direction": "write", "num": 1},
        })
    with pytest.raises(jsonschema.ValidationError):
        axi.validate({
            "api_version": "xdebug.v1",
            "action": "axi.query",
            "args": {"name": "axi0", "direction": "write", "query": {"limit": 1}},
        })
    with pytest.raises(jsonschema.ValidationError):
        axi.validate({
            "api_version": "xdebug.v1",
            "action": "axi.query",
            "args": {"name": "axi0", "direction": "all"},
        })

    stream_export = jsonschema.Draft202012Validator(schema_for("stream.export"))
    stream_export.validate({
        "api_version": "xdebug.v1",
        "action": "stream.export",
        "args": {"stream": "ready_stream", "kind": "packet_beats",
                 "output": {"path": "/tmp/ready.tsv", "file_format": "tsv"}},
    })
    with pytest.raises(jsonschema.ValidationError):
        stream_export.validate({
            "api_version": "xdebug.v1",
            "action": "stream.export",
            "args": {"stream": "ready_stream", "kind": "packet_beats",
                     "format": "tsv", "output": {"path": "/tmp/ready.tsv"}},
        })
    with pytest.raises(jsonschema.ValidationError):
        stream_export.validate({
            "api_version": "xdebug.v1",
            "action": "stream.export",
            "args": {"stream": "ready_stream", "kind": "beats",
                     "output": {"path": "/tmp/ready.tsv", "file_format": "tsv"}},
        })

    stream_config_list = jsonschema.Draft202012Validator(schema_for("stream.config.list"))
    stream_config_list.validate({
        "api_version": "xdebug.v1",
        "action": "stream.config.list",
        "args": {"output": {"verbose": True}},
    })
    with pytest.raises(jsonschema.ValidationError):
        stream_config_list.validate({
            "api_version": "xdebug.v1",
            "action": "stream.config.list",
            "args": {"verbose": True},
        })

    list_export = jsonschema.Draft202012Validator(schema_for("list.export"))
    list_export.validate({
        "api_version": "xdebug.v1",
        "action": "list.export",
        "args": {"name": "basic", "time_range": {"begin": "0ns", "end": "400ns"},
                 "output": {"path": "/tmp/basic", "file_format": "u64bin"}},
    })
    with pytest.raises(jsonschema.ValidationError):
        list_export.validate({
            "api_version": "xdebug.v1",
            "action": "list.export",
            "args": {"name": "basic", "format": "tsv",
                     "time_range": {"begin": "0ns", "end": "400ns"}},
        })

    axi_export = jsonschema.Draft202012Validator(schema_for("axi.export"))
    axi_export.validate({
        "api_version": "xdebug.v1",
        "action": "axi.export",
        "args": {"name": "axi0", "time_range": {"begin": "0ns", "end": "400ns"},
                 "output": {"path": "/tmp/axi0", "file_format": "tsv"}},
    })
    with pytest.raises(jsonschema.ValidationError):
        axi_export.validate({
            "api_version": "xdebug.v1",
            "action": "axi.export",
            "args": {"name": "axi0", "time_range": {"begin": "0ns", "end": "400ns"},
                     "format": "tsv", "output": {"path": "/tmp/axi0"}},
        })

    for action in ("apb.config.list", "axi.config.list", "event.config.list", "stream.config.list"):
        config_list = jsonschema.Draft202012Validator(schema_for(action))
        config_list.validate({
            "api_version": "xdebug.v1",
            "action": action,
        })
        config_list.validate({
            "api_version": "xdebug.v1",
            "action": action,
            "args": {"name": "if0"},
        })

    list_delete = jsonschema.Draft202012Validator(schema_for("list.delete"))
    list_delete.validate({
        "api_version": "xdebug.v1",
        "action": "list.delete",
        "args": {"name": "basic", "index": 2},
    })
    list_delete.validate({
        "api_version": "xdebug.v1",
        "action": "list.delete",
        "args": {"name": "basic", "index": "2"},
    })
    with pytest.raises(jsonschema.ValidationError):
        list_delete.validate({
            "api_version": "xdebug.v1",
            "action": "list.delete",
            "args": {"name": "basic", "index": {"bad": 2}},
        })

    active_chain = jsonschema.Draft202012Validator(schema_for("trace.active_driver_chain"))
    with pytest.raises(jsonschema.ValidationError):
        active_chain.validate({
            "api_version": "xdebug.v1",
            "action": "trace.active_driver_chain",
            "args": {"signal": "top.q", "time": "10ns", "depth": 4},
        })
    with pytest.raises(jsonschema.ValidationError):
        active_chain.validate({
            "api_version": "xdebug.v1",
            "action": "trace.active_driver_chain",
            "args": {"signal": "top.q", "time": "10ns",
                     "limits": {"max_depth": 4}},
        })
    active_chain.validate({
        "api_version": "xdebug.v1",
        "action": "trace.active_driver_chain",
        "args": {"signal": "top.q", "time": "10ns"},
        "limits": {"max_depth": 4},
    })


@pytest.mark.contract
def test_response_examples_do_not_encode_removed_redundant_payloads(
    xdebug_root: Path,
) -> None:
    response_dir = xdebug_root / "examples" / "responses"
    cases = {
        "scope.list.basic.json": ["data.signals_preview", "data.examples"],
        "event.find.basic.json": ["data.examples"],
        "event.export.basic.json": ["data.examples"],
        "verify.conditions.basic.json": ["data.results", "data.examples"],
        "list.create.basic.json": ["data.summary", "data.examples"],
        "list.add.basic.json": ["data.summary", "data.examples"],
        "list.delete.basic.json": ["data.summary", "data.examples"],
        "list.show.basic.json": ["data.count", "data.summary", "data.examples"],
        "list.value_at.basic.json": ["data.summary", "data.examples"],
        "list.validate.basic.json": ["data.summary", "data.examples"],
        "list.diff.basic.json": ["data.time", "data.summary", "data.examples"],
        "list.export.basic.json": ["data.summary", "data.examples"],
        "trace.active_driver_chain.basic.json": ["data.text", "data.chain.text"],
    }
    for filename, forbidden_paths in cases.items():
        example = _load_json(response_dir / filename)
        for dotted_path in forbidden_paths:
            current = example
            found = True
            for part in dotted_path.split("."):
                if not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current[part]
            assert not found, "%s must not contain %s" % (filename, dotted_path)


@pytest.mark.contract
@pytest.mark.parametrize("action", ["actions", "schema", "batch"])
def test_safe_request_examples_execute_with_real_binary(
    cli_runner: CliRunner, xdebug_root: Path, action: str
) -> None:
    request = _load_json(
        xdebug_root / "examples" / "requests" / ("%s.basic.json" % action)
    )
    result = cli_runner.run(request, output_format="json")
    assert result.ok, result.response
    response_schema = _load_json(
        xdebug_root
        / "schemas"
        / "v1"
        / "actions"
        / ("%s.response.schema.json" % action)
    )
    jsonschema.Draft202012Validator(response_schema).validate(result.response)
