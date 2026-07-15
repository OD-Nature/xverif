#!/usr/bin/env python3
"""Replay xdebug action return cases and write evidence.

The registry is intentionally data-driven: action examples stay in
``xdebug/examples/requests`` and per-action overrides live in
``xdebug/testdata/action_return_replay/cases.json``.  The runner records raw
request/response evidence under /tmp so later fixes can keep before/after
proof without checking bulky FSDB-derived output into git.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import importlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
XDEBUG_ROOT = REPO_ROOT / "xdebug"
REQUEST_DIR = XDEBUG_ROOT / "examples" / "requests"
SCHEMA_DIR = XDEBUG_ROOT / "schemas" / "v1" / "actions"
DEFAULT_REGISTRY = XDEBUG_ROOT / "testdata" / "action_return_replay" / "cases.json"
DEFAULT_MATRIX = REPO_ROOT / "doc" / "xdebug_action_return_replay_matrix_2026-07-09.md"
MCP_SRC = REPO_ROOT / "xverif_mcp" / "src"
NO_HANDLER_ERROR_ACTIONS = {"actions", "session.list", "session.gc"}


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _action_slug(action: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", action).replace(".", "_")


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for key, value in patch.items():
            out[key] = _deep_merge(out.get(key), value)
        return out
    return copy.deepcopy(patch)


def _substitute(obj: Any, values: dict[str, str]) -> Any:
    if isinstance(obj, str):
        for key, value in values.items():
            obj = obj.replace("${" + key + "}", value)
        return obj
    if isinstance(obj, list):
        return [_substitute(item, values) for item in obj]
    if isinstance(obj, dict):
        return {key: _substitute(value, values) for key, value in obj.items()}
    return obj


def _repo_values(tmpdir: Path) -> dict[str, str]:
    return {
        "tmpdir": str(tmpdir),
        "ai_complex_fsdb": str(XDEBUG_ROOT / "testdata" / "waveform" / "ai_complex_wave" / "out" / "waves.fsdb"),
        "stream_fsdb": str(XDEBUG_ROOT / "testdata" / "waveform" / "stream_v1" / "out" / "waves.fsdb"),
        "stream_daidir": str(XDEBUG_ROOT / "testdata" / "waveform" / "stream_v1" / "out" / "simv.daidir"),
        "apb_vip_fsdb": str(XDEBUG_ROOT / "testdata" / "waveform" / "apb_vip_real" / "out" / "regression" / "test" / "apb_vip_test" / "waves.fsdb"),
        "design_daidir": str(XDEBUG_ROOT / "testdata" / "design" / "uart" / "simv.daidir"),
        "combined_fsdb": str(XDEBUG_ROOT / "testdata" / "combined" / "active_driver" / "out" / "waves.fsdb"),
        "combined_daidir": str(XDEBUG_ROOT / "testdata" / "combined" / "active_driver" / "out" / "simv.daidir"),
        "apb_config": str(XDEBUG_ROOT / "testdata" / "waveform" / "apb_vip_real" / "config" / "apb0.json"),
        "event_config": str(XDEBUG_ROOT / "testdata" / "waveform" / "ai_complex_wave" / "config" / "event0.json"),
        "stream_config": str(XDEBUG_ROOT / "testdata" / "waveform" / "stream_v1" / "config" / "streams.json"),
    }


@dataclass(frozen=True)
class ReplayCase:
    action: str
    family: str
    requires: str
    setup_profile: str
    example: str
    mcp_applicable: bool
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return _action_slug(self.action)


def load_registry(path: Path) -> tuple[dict[str, Any], list[ReplayCase]]:
    registry = _json_load(path)
    rows = registry.get("actions")
    if not isinstance(rows, list):
        raise SystemExit(f"{path} missing actions[]")
    cases: list[ReplayCase] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("action"), str):
            raise SystemExit(f"{path} has invalid action row: {row!r}")
        action = row["action"]
        if action in seen:
            raise SystemExit(f"duplicate action in registry: {action}")
        seen.add(action)
        cases.append(
            ReplayCase(
                action=action,
                family=str(row.get("family", "")),
                requires=str(row.get("requires", "")),
                setup_profile=str(row.get("setup_profile", "none")),
                example=str(row.get("example", f"{action}.basic.json")),
                mcp_applicable=bool(row.get("mcp_applicable", False)),
                data=row,
            )
        )
    return registry, cases


def _catalog_actions(xdebug: Path, timeout_sec: float) -> list[str]:
    req = {"api_version": "xdebug.v1", "action": "actions"}
    proc = subprocess.run(
        [str(xdebug), "--json", "-"],
        input=json.dumps(req) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"actions catalog failed: rc={proc.returncode} stderr={proc.stderr[-1000:]}")
    rsp = json.loads(proc.stdout)
    actions = rsp.get("data", {}).get("actions")
    if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
        raise SystemExit("actions catalog response missing compact data.actions[] names")
    return sorted(actions)


def _static_check(cases: list[ReplayCase], xdebug: Path, timeout_sec: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    registry_actions = sorted(case.action for case in cases)
    catalog_actions = _catalog_actions(xdebug, timeout_sec)
    catalog_set = set(catalog_actions)
    registry_set = set(registry_actions)
    for action in sorted(registry_set | catalog_set):
        case = next((item for item in cases if item.action == action), None)
        example_ok = case is not None and (REQUEST_DIR / case.example).exists()
        request_schema_ok = (SCHEMA_DIR / f"{action}.request.schema.json").exists()
        response_schema_ok = (SCHEMA_DIR / f"{action}.response.schema.json").exists()
        rows.append(
            {
                "action": action,
                "in_registry": action in registry_set,
                "in_runtime_catalog": action in catalog_set,
                "example_ok": example_ok,
                "request_schema_ok": request_schema_ok,
                "response_schema_ok": response_schema_ok,
                "ok": (
                    action in registry_set
                    and action in catalog_set
                    and example_ok
                    and request_schema_ok
                    and response_schema_ok
                ),
            }
        )
    return rows


def _load_request(case: ReplayCase, placeholders: dict[str, str]) -> dict[str, Any]:
    request = _json_load(REQUEST_DIR / case.example)
    request = _substitute(request, placeholders)
    request = _normalize_seed_request(case, request, placeholders)
    if isinstance(case.data.get("success"), dict):
        request = _deep_merge(request, case.data["success"])
    if request.get("action") != case.action:
        raise SystemExit(f"{case.example} action mismatch: {request.get('action')} != {case.action}")
    return request


def _normalize_seed_request(
    case: ReplayCase,
    request: dict[str, Any],
    placeholders: dict[str, str],
) -> dict[str, Any]:
    """Map documentation seed examples to the replay fixture signals.

    The existing examples are useful as schema-shaped seeds, but many still use
    placeholder paths such as top.u.valid.  Replay needs deterministic fixture
    signals; action-specific behavior remains in runtime, not here.
    """
    request = copy.deepcopy(request)
    text = json.dumps(request)
    replacements = {
        "top.u.clk": "ai_complex_top.clk",
        "top.u.valid": "ai_complex_top.hs_valid",
        "top.u.ready": "ai_complex_top.hs_ready",
        "top.u.dbg_wait_count": "ai_complex_top.counter_inc",
        "top.valid": "ai_complex_top.event_vld",
        "top.clk": "stream_v1_top.clk" if case.setup_profile == "stream" else "ai_complex_top.clk",
        "top.rst_n": "stream_v1_top.rst_n" if case.setup_profile == "stream" else "ai_complex_top.rst_n",
        "top.req_vld": "stream_v1_top.ready_vld",
        "top.req_rdy": "stream_v1_top.ready_rdy",
        "top.req_sop": "stream_v1_top.rpkt_sop",
        "top.req_eop": "stream_v1_top.rpkt_eop",
        "top.req_data": "stream_v1_top.ready_data",
        "top.addr_hi": "stream_v1_top.ready_addr_hi",
        "top.addr_lo": "stream_v1_top.ready_addr_lo",
        "top.req_cmd": "stream_v1_top.ready_cmd",
        "top.data_out": "active_driver_tb.u_dut.q",
        "waves.fsdb": placeholders["combined_fsdb"] if case.setup_profile == "combined" else placeholders["ai_complex_fsdb"],
        "simv.daidir": placeholders["combined_daidir"] if case.setup_profile == "combined" else placeholders["design_daidir"],
        "events.json": placeholders["event_config"],
        "wave_view.json": placeholders["event_config"],
        "xdebug/testdata/waveform/ai_complex_wave/config/apb0.json": placeholders["apb_config"],
        "/tmp/if0_list_export": str(Path(placeholders["tmpdir"]) / "if0_list_export"),
        "/tmp/if0_axi": str(Path(placeholders["tmpdir"]) / "if0_axi"),
        "signal.rc": str(Path(placeholders["tmpdir"]) / "signal.rc"),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    request = json.loads(text)
    action = case.action
    args = request.setdefault("args", {})
    if action == "source.context":
        args.update({"file": str(XDEBUG_ROOT / "testdata" / "waveform" / "ai_complex_wave" / "tb" / "ai_complex_top.sv"), "line": 20})
    if action == "value.at":
        args.update({"signal": "ai_complex_top.sig_a", "clock": "ai_complex_top.clk", "time": "75ns"})
    if action == "value.batch_at":
        args.update({"signals": ["ai_complex_top.sig_a", "ai_complex_top.sig_b"], "clock": "ai_complex_top.clk", "time": "75ns"})
    if action == "expr.eval_at":
        args.update({"expr": "valid && ready", "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"}, "clock": "ai_complex_top.clk", "time": "100ns"})
    if action == "counter.statistics":
        args.clear()
        args.update(
            {
                "clock": "ai_complex_top.clk",
                "edge": "posedge",
                "time_range": {"begin": "55ns", "end": "95ns"},
                "vld": "ai_complex_top.rst_n",
                "cnt": "ai_complex_top.counter_inc",
            }
        )
    if action in ("signal.changes", "signal.stability", "signal.statistics"):
        args.update({"signal": "ai_complex_top.sig_a"})
    if action == "detect_abnormal":
        args.update({"signals": ["ai_complex_top.xz_bus", "ai_complex_top.glitch_sig"], "time_range": {"begin": "0ns", "end": "200ns"}})
    if action == "handshake.inspect":
        args.update({"clock": "ai_complex_top.clk", "valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"})
    if action == "verify.conditions":
        args.update({"clock": "ai_complex_top.clk", "signals": {"valid": "ai_complex_top.hs_valid"}, "conditions": [{"expr": "valid == 1"}], "time": "100ns"})
    if action == "window.verify":
        args.update({"clock": "ai_complex_top.clk", "signals": {"valid": "ai_complex_top.hs_valid"}, "conditions": [{"expr": "valid == 1", "mode": "always"}], "time_range": {"begin": "70ns", "end": "100ns"}})
    if action == "event.find":
        args.update({"clock": "ai_complex_top.clk", "signals": {"valid": "ai_complex_top.event_vld", "ready": "ai_complex_top.event_rdy"}, "expr": "valid && !ready", "line_limit": 5})
    if action == "event.export":
        args.update({"clock": "ai_complex_top.clk", "signals": {"valid": "ai_complex_top.event_vld", "ready": "ai_complex_top.event_rdy"}, "expr": "valid && !ready", "line_limit": 5})
    if action == "event.config.load":
        args.update({"name": "if0", "config_path": placeholders["event_config"]})
    if action == "sampled_pulse.inspect":
        args.update(
            {
                "clock": "ai_complex_top.clk",
                "valid": "ai_complex_top.glitch_sig",
                "payload": "ai_complex_top.hs_data",
                "time_range": {"begin": "0ns", "end": "200ns"},
                "edge": "posedge",
                "line_limit": 5,
            }
        )
    if action == "trace.active_driver":
        args.update({"signal": "active_driver_tb.u_dut.q", "time": "40ns"})
    if action == "trace.active_driver_chain":
        args.update({"signal": "active_driver_tb.u_dut.q", "time": "40ns", "clk_period": "10ns"})
    if action == "rc.generate":
        rc_path = Path(placeholders["tmpdir"]) / f"{_action_slug(action)}.rc.json"
        _write_rc_config(rc_path)
        args.update(
            {
                "config_path": str(rc_path),
                "output": {"path": str(Path(placeholders["tmpdir"]) / "signal.rc")},
            }
        )
    if action == "apb.config.load":
        args.update({"name": "if0", "config_path": placeholders["apb_config"]})
    if action.startswith("apb.") and action not in ("apb.config.list", "apb.config.load"):
        args["name"] = "if0"
    if action.startswith("axi.") and action not in ("axi.config.list", "axi.config.load"):
        args["name"] = "if0"
    if action.startswith("stream.") and action not in ("stream.config.list", "stream.config.load"):
        args["stream"] = "ready_stream"
    if action in ("cursor.get", "cursor.delete", "cursor.use"):
        args["name"] = "mark_a"
    if action.startswith("list."):
        args.setdefault("name", "if0")
        if action in ("list.create", "list.add", "list.delete"):
            args["signal"] = "ai_complex_top.hs_valid"
        if action == "list.create":
            args["signals"] = ["ai_complex_top.hs_valid", "ai_complex_top.hs_ready"]
            args.pop("signal", None)
        if action == "list.value_at":
            args.update({"clock": "ai_complex_top.clk", "time": "100ns"})
    if action == "stream.config.load":
        cfg = _json_load(Path(placeholders["stream_config"]))
        args.clear()
        args.update({"mode": "replace", "streams": cfg["streams"]})
    if action == "axi.config.load":
        args.clear()
        args.update({"name": "if0", "config": _synthetic_axi_config()})
    return request


def _synthetic_axi_config() -> dict[str, Any]:
    return {
        "clock": "ai_complex_top.clk",
        "reset": {"signal": "ai_complex_top.rst_n", "polarity": "active_low"},
        "edge": "posedge",
        "awaddr": "ai_complex_top.paddr",
        "awid": "ai_complex_top.sig_a",
        "awlen": "ai_complex_top.sig_a",
        "awsize": "ai_complex_top.sig_a",
        "awburst": "ai_complex_top.sig_a",
        "awvalid": "ai_complex_top.psel",
        "awready": "ai_complex_top.penable",
        "wdata": "ai_complex_top.pwdata",
        "wstrb": "ai_complex_top.sig_a",
        "wlast": "ai_complex_top.penable",
        "wvalid": "ai_complex_top.psel",
        "wready": "ai_complex_top.penable",
        "bid": "ai_complex_top.sig_a",
        "bresp": "ai_complex_top.sig_a",
        "bvalid": "ai_complex_top.penable",
        "bready": "ai_complex_top.psel",
        "araddr": "ai_complex_top.paddr",
        "arid": "ai_complex_top.sig_a",
        "arlen": "ai_complex_top.sig_a",
        "arsize": "ai_complex_top.sig_a",
        "arburst": "ai_complex_top.sig_a",
        "arvalid": "ai_complex_top.psel",
        "arready": "ai_complex_top.penable",
        "rid": "ai_complex_top.sig_a",
        "rdata": "ai_complex_top.prdata",
        "rresp": "ai_complex_top.sig_a",
        "rlast": "ai_complex_top.penable",
        "rvalid": "ai_complex_top.penable",
        "rready": "ai_complex_top.psel",
    }


def _write_rc_config(path: Path) -> None:
    _json_write(
        path,
        {
            "timescale": "1ns",
            "groups": [
                {
                    "name": "ClockReset",
                    "signals": [
                        {"path": "ai_complex_top.clk"},
                        {"path": "ai_complex_top.rst_n"},
                    ],
                },
                {
                    "name": "Handshake",
                    "signals": [
                        {"path": "ai_complex_top.hs_valid"},
                        {"path": "ai_complex_top.hs_ready"},
                    ],
                },
            ],
            "user_markers": [{"name": "cursor", "time": "120ns"}],
        },
    )


def _run_cli(xdebug: Path, request: dict[str, Any], output_format: str, timeout_sec: float) -> tuple[Any, dict[str, Any]]:
    assert output_format in ("json", "xout")
    argv = [str(xdebug), "-"] if output_format == "xout" else [str(xdebug), "--json", "-"]
    started = time.monotonic()
    proc = subprocess.run(
        argv,
        input=json.dumps(request) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_sec,
        check=False,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if output_format == "json":
        try:
            response: Any = json.loads(proc.stdout)
        except Exception:
            response = {
                "ok": False,
                "action": request.get("action"),
                "error": {
                    "code": "OUTPUT_PARSE_FAILED",
                    "message": proc.stdout[-2000:],
                    "stderr": proc.stderr[-2000:],
                },
            }
    else:
        response = proc.stdout
    meta = {
        "command": argv,
        "entry": "native_cli",
        "output_format": output_format,
        "elapsed_ms": elapsed_ms,
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-4000:],
    }
    return response, meta


def _open_native_session(
    xdebug: Path,
    name: str,
    profile: str,
    registry: dict[str, Any],
    placeholders: dict[str, str],
    timeout_sec: float,
) -> dict[str, Any] | None:
    if profile == "none":
        return None
    fixture = _substitute(registry.get("fixture_profiles", {}).get(profile, {}), placeholders)
    target = {key: value for key, value in fixture.items() if key in ("fsdb", "daidir")}
    if not target:
        return None
    request = {
        "api_version": "xdebug.v1",
        "action": "session.open",
        "target": target,
        "args": {"name": name},
    }
    response, meta = _run_cli(xdebug, request, "json", timeout_sec)
    return {"request": request, "response": response, "metadata": meta}


def _native_setup_requests(case: ReplayCase, session_name: str, placeholders: dict[str, str]) -> list[dict[str, Any]]:
    target = {"session_id": session_name}
    action = case.action
    requests: list[dict[str, Any]] = []
    if action.startswith("apb.") and action not in ("apb.config.list", "apb.config.load"):
        requests.append(
            {
                "api_version": "xdebug.v1",
                "action": "apb.config.load",
                "target": target,
                "args": {"name": "if0", "config_path": placeholders["apb_config"]},
            }
        )
    if action.startswith("axi.") and action not in ("axi.config.list", "axi.config.load"):
        requests.append(
            {
                "api_version": "xdebug.v1",
                "action": "axi.config.load",
                "target": target,
                "args": {"name": "if0", "config": _synthetic_axi_config()},
            }
        )
    if action.startswith("stream.") and action not in ("stream.config.list", "stream.config.load"):
        cfg = _json_load(Path(placeholders["stream_config"]))
        requests.append(
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "target": target,
                "args": {"mode": "replace", "streams": cfg["streams"]},
            }
        )
    if action in ("cursor.get", "cursor.delete", "cursor.use"):
        requests.append(
            {
                "api_version": "xdebug.v1",
                "action": "cursor.set",
                "target": target,
                "args": {"name": "mark_a", "time": "100ns"},
            }
        )
    if action in ("list.add", "list.show", "list.delete", "list.diff", "list.validate", "list.value_at", "list.export"):
        requests.append(
            {
                "api_version": "xdebug.v1",
                "action": "list.create",
                "target": target,
                "args": {"name": "if0", "signals": ["ai_complex_top.hs_valid", "ai_complex_top.hs_ready"]},
            }
        )
    return requests


def _close_native_session(xdebug: Path, name: str, timeout_sec: float) -> None:
    request = {
        "api_version": "xdebug.v1",
        "action": "session.close",
        "target": {"session_id": name},
    }
    _run_cli(xdebug, request, "json", timeout_sec)


def _kill_native_session(xdebug: Path, name: str, timeout_sec: float) -> None:
    request = {
        "api_version": "xdebug.v1",
        "action": "session.kill",
        "target": {"session_id": name},
    }
    _run_cli(xdebug, request, "json", timeout_sec)


def _prepare_native_request(
    case: ReplayCase,
    request: dict[str, Any],
    session_name: str,
    profile: str,
) -> dict[str, Any]:
    request = copy.deepcopy(request)
    action = case.action
    if action == "session.open":
        if profile != "none":
            request["target"] = {
                key: value
                for key, value in request.get("target", {}).items()
                if key in ("fsdb", "daidir")
            }
        request["args"] = _deep_merge(request.get("args", {}), {"name": session_name})
        return request
    if action in ("session.list", "session.gc", "actions", "schema", "batch", "expr.normalize"):
        return request
    if action in ("session.close", "session.doctor", "session.kill"):
        request["target"] = {"session_id": session_name}
        return request
    if profile != "none":
        request["target"] = {"session_id": session_name}
    return request


def _write_evidence(
    root: Path,
    case_id: str,
    request: dict[str, Any],
    response: Any,
    metadata: dict[str, Any],
) -> None:
    evidence = root / "evidence" / case_id
    _json_write(evidence / "request.json", request)
    if isinstance(response, str):
        _text_write(evidence / "response.xout", response)
    else:
        _json_write(evidence / "response.json", response)
    _json_write(evidence / "metadata.json", metadata)


def _load_mcp_server():
    sys.path = [
        path
        for path in sys.path
        if Path(path or os.getcwd()).resolve() != XDEBUG_ROOT
    ]
    if str(MCP_SRC) not in sys.path:
        sys.path.insert(0, str(MCP_SRC))
    os.environ.setdefault("XVERIF_HOME", str(REPO_ROOT))
    os.environ.setdefault("XVERIF_MCP_BACKEND", "direct")
    os.environ.setdefault("XVERIF_MCP_STARTUP_TIMEOUT_SEC", "30")
    os.environ.setdefault("XVERIF_MCP_REQUEST_TIMEOUT_SEC", "120")
    if "xverif_mcp.server" in sys.modules:
        return importlib.reload(sys.modules["xverif_mcp.server"])
    return importlib.import_module("xverif_mcp.server")


def _close_mcp_server(server: Any) -> None:
    for adapter_name in ("debug", "cov"):
        adapter = getattr(server, adapter_name, None)
        sessions = getattr(adapter, "_sessions", None)
        if sessions is not None:
            sessions.close_all()


async def _mcp_call(server: Any, tool: str, args: dict[str, Any] | None) -> Any:
    result = await server.mcp.call_tool(tool, args or {})
    content = result[0] if isinstance(result, tuple) else result
    if not content:
        return ""
    text = content[0].text
    try:
        return json.loads(text)
    except Exception:
        return text


def _run_mcp_tool(
    server: Any,
    tool: str,
    args: dict[str, Any],
    output_format: str,
    timeout_sec: float,
) -> tuple[Any, dict[str, Any]]:
    started = time.monotonic()
    try:
        response = asyncio.run(asyncio.wait_for(_mcp_call(server, tool, args), timeout=timeout_sec))
        returncode = 0
    except Exception as exc:
        response = {
            "ok": False,
            "error": {
                "code": "MCP_TOOL_ERROR",
                "message": str(exc),
                "error_layer": "wrapper",
            },
        }
        returncode = 1
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return response, {
        "command": ["mcp.call_tool", tool],
        "entry": "mcp_direct",
        "output_format": output_format,
        "elapsed_ms": elapsed_ms,
        "returncode": returncode,
    }


def _ok_from_response(response: Any, output_format: str, returncode: int) -> bool:
    if returncode != 0:
        return False
    if output_format == "json":
        return isinstance(response, dict) and response.get("ok") is True
    return isinstance(response, str) and response.startswith("@xdebug.")


def _ok_from_mcp_response(response: Any, output_format: str, returncode: int, *, tool: str) -> bool:
    if returncode != 0:
        return False
    if output_format == "json":
        return isinstance(response, dict) and response.get("ok") is True
    if tool != "xverif_debug_query":
        return isinstance(response, dict) and response.get("ok") is True
    return isinstance(response, str) and response.startswith("@xdebug.")


def _run_native_case(
    case: ReplayCase,
    registry: dict[str, Any],
    xdebug: Path,
    out_root: Path,
    output_format: str,
    timeout_sec: float,
) -> dict[str, Any]:
    placeholders = _repo_values(out_root)
    session_name = f"replay_{os.getpid()}_{case.id}_{output_format}"
    placeholders.update(
        {
            "wave_session": session_name,
            "design_session": session_name,
            "combined_session": session_name,
        }
    )
    setup = None
    should_open_setup_session = (
        case.setup_profile != "none" and case.action != "session.open"
    ) or case.action == "session.kill"
    if case.action == "session.open":
        _kill_native_session(xdebug, session_name, timeout_sec)
    if case.action == "session.kill":
        case = ReplayCase(
            action=case.action,
            family=case.family,
            requires=case.requires,
            setup_profile="combined",
            example=case.example,
            mcp_applicable=case.mcp_applicable,
            data=case.data,
        )
    if should_open_setup_session:
        setup = _open_native_session(xdebug, session_name, case.setup_profile, registry, placeholders, timeout_sec)
    setup_steps: list[dict[str, Any]] = []
    if should_open_setup_session:
        for setup_request in _native_setup_requests(case, session_name, placeholders):
            setup_response, setup_meta = _run_cli(xdebug, setup_request, "json", timeout_sec)
            setup_steps.append(
                {
                    "request": setup_request,
                    "response": setup_response,
                    "metadata": setup_meta,
                }
            )
    request = _prepare_native_request(case, _load_request(case, placeholders), session_name, case.setup_profile)
    response, meta = _run_cli(xdebug, request, output_format, timeout_sec)
    meta["fixture"] = case.setup_profile
    if setup is not None:
        meta["setup"] = setup
    if setup_steps:
        meta["setup_steps"] = setup_steps
    _write_evidence(out_root, f"{case.id}.native.{output_format}", request, response, meta)
    if should_open_setup_session:
        _close_native_session(xdebug, session_name, timeout_sec)
    if case.action == "session.open" and isinstance(response, dict) and response.get("ok") is True:
        _close_native_session(xdebug, session_name, timeout_sec)
    ok = _ok_from_response(response, output_format, int(meta["returncode"]))
    return {
        "case_id": f"{case.id}.native.{output_format}",
        "action": case.action,
        "entry": "native_cli",
        "output_format": output_format,
        "ok": ok,
        "returncode": meta["returncode"],
        "evidence": str(out_root / "evidence" / f"{case.id}.native.{output_format}"),
    }


def _negative_request(case: ReplayCase, placeholders: dict[str, str], kind: str) -> dict[str, Any]:
    request = _load_request(case, placeholders)
    if kind == "schema_error":
        request.setdefault("args", {})["__replay_bad_arg"] = True
        return request
    if case.action == "session.open":
        request["target"] = {"fsdb": str(Path(placeholders["tmpdir"]) / "missing.fsdb")}
        request["args"] = {"name": "replay_missing"}
        return request
    if case.action in ("actions", "schema"):
        request["action"] = case.action
        request["args"] = {"action": "no.such.action"} if case.action == "schema" else {}
        request["target"] = {"session_id": "no_such_session"}
        return request
    if case.action == "batch":
        request["args"] = {"requests": [{"api_version": "xdebug.v1", "action": "no.such.action"}]}
        return request
    request["target"] = {"session_id": "no_such_session"}
    return request


def _run_native_negative_case(
    case: ReplayCase,
    xdebug: Path,
    out_root: Path,
    output_format: str,
    kind: str,
    timeout_sec: float,
) -> dict[str, Any]:
    placeholders = _repo_values(out_root)
    request = _negative_request(case, placeholders, kind)
    response, meta = _run_cli(xdebug, request, output_format, timeout_sec)
    meta["fixture"] = "negative"
    evidence_id = f"{case.id}.native.{kind}.{output_format}"
    _write_evidence(out_root, evidence_id, request, response, meta)
    if output_format == "json":
        ok = (
            isinstance(response, dict)
            and response.get("ok") is False
            and isinstance(response.get("error"), dict)
            and bool(response["error"].get("code"))
        )
    else:
        ok = (
            isinstance(response, str)
            and response.startswith("@xdebug.error.v1")
        ) or (
            isinstance(response, dict)
            and response.get("ok") is False
            and isinstance(response.get("error"), dict)
            and bool(response["error"].get("code"))
        )
    return {
        "case_id": evidence_id,
        "action": case.action,
        "entry": "native_cli",
        "output_format": output_format,
        "negative_kind": kind,
        "ok": ok,
        "returncode": meta["returncode"],
        "evidence": str(out_root / "evidence" / evidence_id),
    }


def _mcp_open_args(profile: str, registry: dict[str, Any], placeholders: dict[str, str], name: str) -> dict[str, Any]:
    fixture = _substitute(registry.get("fixture_profiles", {}).get(profile, {}), placeholders)
    args: dict[str, Any] = {"name": name}
    if "fsdb" in fixture:
        args["fsdb"] = fixture["fsdb"]
    if "daidir" in fixture:
        args["daidir"] = fixture["daidir"]
    return args


def _run_mcp_case(
    server: Any,
    case: ReplayCase,
    registry: dict[str, Any],
    out_root: Path,
    output_format: str,
    timeout_sec: float,
) -> dict[str, Any]:
    placeholders = _repo_values(out_root)
    session_name = f"replay_mcp_{os.getpid()}_{case.id}_{output_format}"
    placeholders.update(
        {
            "wave_session": session_name,
            "design_session": session_name,
            "combined_session": session_name,
        }
    )
    request = _load_request(case, placeholders)
    evidence_id = f"{case.id}.mcp.{output_format}"
    setup_steps: list[dict[str, Any]] = []

    tool = "xverif_debug_query"
    tool_args: dict[str, Any]
    if case.data.get("mcp_tool") == "xverif_debug_list_actions":
        tool = "xverif_debug_list_actions"
        tool_args = {}
    elif case.data.get("mcp_tool") == "xverif_debug_get_schema":
        tool = "xverif_debug_get_schema"
        tool_args = dict(case.data.get("mcp_args", {}))
    elif case.data.get("mcp_tool") == "xverif_debug_session_open":
        tool = "xverif_debug_session_open"
        tool_args = _mcp_open_args(case.setup_profile, registry, placeholders, session_name)
    elif case.data.get("mcp_tool") == "xverif_debug_session_list":
        tool = "xverif_debug_session_list"
        tool_args = {}
    elif case.data.get("mcp_tool") == "xverif_debug_session_close":
        open_args = _mcp_open_args(case.setup_profile, registry, placeholders, session_name)
        open_response, open_meta = _run_mcp_tool(server, "xverif_debug_session_open", open_args, "json", timeout_sec)
        setup_steps.append({"tool": "xverif_debug_session_open", "args": open_args, "response": open_response, "metadata": open_meta})
        tool = "xverif_debug_session_close"
        tool_args = {"name": session_name}
    else:
        mcp_profile = case.setup_profile if case.setup_profile != "none" else "waveform"
        if case.action == "expr.normalize":
            mcp_profile = "design"
        open_args = _mcp_open_args(case.setup_profile, registry, placeholders, session_name)
        if mcp_profile != "none":
            open_args = _mcp_open_args(mcp_profile, registry, placeholders, session_name)
            open_response, open_meta = _run_mcp_tool(server, "xverif_debug_session_open", open_args, "json", timeout_sec)
            setup_steps.append({"tool": "xverif_debug_session_open", "args": open_args, "response": open_response, "metadata": open_meta})
            for setup_request in _native_setup_requests(case, session_name, placeholders):
                setup_args = {
                    "session_id": session_name,
                    "action": setup_request["action"],
                    "args": setup_request.get("args", {}),
                    "output_format": "json",
                }
                setup_response, setup_meta = _run_mcp_tool(server, "xverif_debug_query", setup_args, "json", timeout_sec)
                setup_steps.append({"tool": "xverif_debug_query", "args": setup_args, "response": setup_response, "metadata": setup_meta})
        tool_args = {
            "session_id": session_name,
            "action": case.action,
            "args": request.get("args", {}),
            "output_format": output_format,
        }

    response, meta = _run_mcp_tool(server, tool, tool_args, output_format, timeout_sec)
    meta["fixture"] = case.setup_profile
    if setup_steps:
        meta["setup_steps"] = setup_steps
    _write_evidence(out_root, evidence_id, {"tool": tool, "args": tool_args}, response, meta)
    if tool == "xverif_debug_query" and tool != "xverif_debug_session_close":
        try:
            _run_mcp_tool(server, "xverif_debug_session_close", {"name": session_name}, "json", timeout_sec)
        except Exception:
            pass
    if tool == "xverif_debug_session_open" and isinstance(response, dict) and response.get("ok") is True:
        try:
            _run_mcp_tool(server, "xverif_debug_session_close", {"name": session_name}, "json", timeout_sec)
        except Exception:
            pass
    ok = _ok_from_mcp_response(response, output_format, int(meta["returncode"]), tool=tool)
    return {
        "case_id": evidence_id,
        "action": case.action,
        "entry": "mcp_direct",
        "output_format": output_format,
        "ok": ok,
        "returncode": meta["returncode"],
        "evidence": str(out_root / "evidence" / evidence_id),
    }


def _run_mcp_negative_case(
    server: Any,
    case: ReplayCase,
    registry: dict[str, Any],
    out_root: Path,
    output_format: str,
    kind: str,
    timeout_sec: float,
) -> dict[str, Any]:
    placeholders = _repo_values(out_root)
    session_name = f"replay_mcp_l3_{os.getpid()}_{case.id}_{kind}_{output_format}"
    placeholders.update(
        {
            "wave_session": session_name,
            "design_session": session_name,
            "combined_session": session_name,
        }
    )
    request = _load_request(case, placeholders)
    setup_steps: list[dict[str, Any]] = []
    mcp_profile = case.setup_profile if case.setup_profile != "none" else "waveform"
    if case.action == "expr.normalize":
        mcp_profile = "design"
    open_args = _mcp_open_args(mcp_profile, registry, placeholders, session_name)
    open_response, open_meta = _run_mcp_tool(server, "xverif_debug_session_open", open_args, "json", timeout_sec)
    setup_steps.append({"tool": "xverif_debug_session_open", "args": open_args, "response": open_response, "metadata": open_meta})
    tool_args = {
        "session_id": session_name,
        "action": case.action,
        "args": request.get("args", {}),
        "output_format": output_format,
    }
    if kind == "schema_error":
        tool_args["args"] = dict(tool_args["args"])
        tool_args["args"]["__replay_bad_arg"] = True
    else:
        tool_args["session_id"] = "no_such_session"
    response, meta = _run_mcp_tool(server, "xverif_debug_query", tool_args, output_format, timeout_sec)
    meta["fixture"] = "negative"
    meta["setup_steps"] = setup_steps
    evidence_id = f"{case.id}.mcp.{kind}.{output_format}"
    _write_evidence(out_root, evidence_id, {"tool": "xverif_debug_query", "args": tool_args}, response, meta)
    try:
        _run_mcp_tool(server, "xverif_debug_session_close", {"name": session_name}, "json", timeout_sec)
    except Exception:
        pass
    if output_format == "json":
        ok = (
            isinstance(response, dict)
            and response.get("ok") is False
            and isinstance(response.get("error"), dict)
            and bool(response["error"].get("code"))
        )
    else:
        ok = (
            isinstance(response, str)
            and response.startswith("@xdebug.error.v1")
        ) or (
            isinstance(response, dict)
            and response.get("ok") is False
            and isinstance(response.get("error"), dict)
            and bool(response["error"].get("code"))
        )
    return {
        "case_id": evidence_id,
        "action": case.action,
        "entry": "mcp_direct",
        "output_format": output_format,
        "negative_kind": kind,
        "ok": ok,
        "returncode": meta["returncode"],
        "evidence": str(out_root / "evidence" / evidence_id),
    }


def render_matrix(cases: list[ReplayCase], static_rows: list[dict[str, Any]] | None = None) -> str:
    static_by_action = {row["action"]: row for row in static_rows or []}
    lines = [
        "# xdebug Action Return Replay Matrix（2026-07-09）",
        "",
        "本矩阵由 `xdebug/tools/replay_action_returns.py --write-matrix` 生成，覆盖 registry 中的 72 个 action。",
        "",
        "| # | action | family | requires | setup | native JSON | native xout | MCP JSON | MCP xout | L0 static |",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for idx, case in enumerate(cases, start=1):
        mcp = "planned" if case.mcp_applicable else "n/a"
        static = static_by_action.get(case.action, {})
        l0 = "pass" if static.get("ok") else ("pending" if not static else "fail")
        lines.append(
            f"| {idx} | `{case.action}` | {case.family} | {case.requires} | {case.setup_profile} | "
            f"planned | planned | {mcp} | {mcp} | {l0} |"
        )
    lines.extend(
        [
            "",
            "## 入口说明",
            "",
            "- `native JSON`：`tools/xdebug --json -`。",
            "- `native xout`：`tools/xdebug -`。",
            "- `MCP JSON/xout`：通过 direct backend 的 `xverif_debug_query` 或专用 session/schema/list tools。",
            "- `planned` 表示 registry 已纳入矩阵，执行状态以 `/tmp/xdebug_action_return_replay_*/summary.json` 为准。",
            "",
        ]
    )
    return "\n".join(lines)


def _case_filter(cases: list[ReplayCase], actions: list[str] | None) -> list[ReplayCase]:
    if not actions:
        return cases
    wanted = set(actions)
    selected = [case for case in cases if case.action in wanted]
    missing = sorted(wanted - {case.action for case in selected})
    if missing:
        raise SystemExit(f"unknown registry actions: {', '.join(missing)}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--xdebug", type=Path, default=REPO_ROOT / "tools" / "xdebug")
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L0")
    parser.add_argument(
        "--entry",
        choices=["native-json", "native-xout", "native-all", "mcp-json", "mcp-xout", "mcp-all"],
        default="native-all",
    )
    parser.add_argument("--action", action="append", help="Limit to one action; may be repeated.")
    parser.add_argument("--write-matrix", type=Path, nargs="?", const=DEFAULT_MATRIX)
    args = parser.parse_args()

    registry, cases = load_registry(args.registry)
    out_root = args.out_root or Path("/tmp") / f"xdebug_action_return_replay_{time.strftime('%Y%m%d_%H%M%S')}"
    out_root.mkdir(parents=True, exist_ok=True)

    static_rows = _static_check(cases, args.xdebug, args.timeout_sec)
    if args.write_matrix:
        _text_write(args.write_matrix, render_matrix(cases, static_rows))
        print(f"matrix={args.write_matrix}")

    if args.layer == "L0":
        _json_write(out_root / "matrix.json", static_rows)
        summary = {
            "layer": "L0",
            "total": len(static_rows),
            "failed": [row for row in static_rows if not row["ok"]],
            "out_root": str(out_root),
        }
        _json_write(out_root / "summary.json", summary)
        print(f"L0 total={summary['total']} failed={len(summary['failed'])} out_root={out_root}")
        return 0 if not summary["failed"] else 1

    selected = _case_filter(cases, args.action)
    if args.entry.startswith("mcp"):
        selected = [case for case in selected if case.mcp_applicable]
    formats = ["json", "xout"] if args.entry.endswith("-all") else [args.entry.split("-", 1)[1]]
    rows: list[dict[str, Any]] = []
    if args.entry.startswith("mcp"):
        server = _load_mcp_server()
        try:
            for case in selected:
                for output_format in formats:
                    if args.layer == "L3":
                        if case.data.get("mcp_tool"):
                            continue
                        for kind in ("schema_error", "handler_error"):
                            rows.append(
                                _run_mcp_negative_case(
                                    server,
                                    case,
                                    registry,
                                    out_root,
                                    output_format,
                                    kind,
                                    args.timeout_sec,
                                )
                            )
                    else:
                        rows.append(_run_mcp_case(server, case, registry, out_root, output_format, args.timeout_sec))
        finally:
            _close_mcp_server(server)
    else:
        for case in selected:
            for output_format in formats:
                if args.layer == "L3":
                    kinds = ["schema_error"]
                    if case.action not in NO_HANDLER_ERROR_ACTIONS:
                        kinds.append("handler_error")
                    for kind in kinds:
                        rows.append(
                            _run_native_negative_case(
                                case,
                                args.xdebug,
                                out_root,
                                output_format,
                                kind,
                                args.timeout_sec,
                            )
                        )
                else:
                    rows.append(_run_native_case(case, registry, args.xdebug, out_root, output_format, args.timeout_sec))
    summary = {
        "layer": args.layer,
        "entry": args.entry,
        "total": len(rows),
        "failed": [row for row in rows if not row["ok"]],
        "rows": rows,
        "out_root": str(out_root),
    }
    _json_write(out_root / "summary.json", summary)
    print(f"{args.layer} total={summary['total']} failed={len(summary['failed'])} out_root={out_root}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
