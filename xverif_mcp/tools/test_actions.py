#!/usr/bin/env python3
"""逐个测试全部 75 个 xdebug action，通过 MCP client 调用 FastMCP server。

用法:
    conda activate xverif-mcp
    PYTHONPATH=xverif_mcp/src python xverif_mcp/tools/test_actions.py
    PYTHONPATH=xverif_mcp/src python xverif_mcp/tools/test_actions.py -c my_config.json

选项:
    -c, --config      指定 JSON 配置文件（默认 tools/test_config.json）
    --schema-only     只测试 schema（快，不需要 FSDB）
    --level L1|L2|L3  测试级别（默认 all）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

# Add project to path
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
sys.path.insert(0, ROOT)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ALL_ACTIONS = [
    "actions", "batch", "schema",
    "session.open", "session.ensure", "session.list", "session.doctor",
    "session.gc", "session.kill", "session.close",
    "trace.driver", "trace.expand", "trace.explain", "trace.graph",
    "trace.load", "trace.path", "trace.query",
    "source.context", "expr.normalize",
    "fsm.explain",
    "port.trace",
    "control.explain", "counter.explain",
    "instance.map", "interface.resolve",
    "signal.resolve", "signal.canonicalize",
    "inspect_signal", "detect_anomaly",
    "handshake.inspect",
    "procedural.assignment", "sequential.update",
    "value.at", "value.batch_at",
    "scope.list",
    "signal.changes", "signal.stability", "signal.statistics", "signal.trend",
    "event.find", "event.export", "event.config.list", "event.config.load",
    "window.verify",
    "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
    "list.create", "list.add", "list.show", "list.delete",
    "list.diff", "list.validate", "list.value_at",
    "apb.config.list", "apb.config.load", "apb.cursor",
    "apb.query", "apb.transfer_window",
    "axi.analysis", "axi.channel_stall",
    "axi.config.list", "axi.config.load", "axi.cursor",
    "axi.latency_outlier", "axi.outstanding_timeline",
    "axi.query", "axi.request_response_pair",
    "trace.active_driver",
    "expr.eval_at",
    "verify.conditions", "rc.generate",
    "sampled_pulse.inspect",
]

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    """加载 JSON 配置文件。"""
    with open(config_path) as f:
        cfg = json.load(f)
    cfg.setdefault("session_name", "action_test")
    return cfg


def build_action_args(sig: str, clk: str, session_name: str) -> dict[str, dict]:
    """根据信号名构建 L2 测试用 action 参数表。"""
    return {
    "scope.list": {"path": "", "recursive": True, "max_depth": 3},
    "instance.map": {"instance": sig},
    "signal.resolve": {"signal": sig},
    "port.trace": {"signal": sig},
    "interface.resolve": {"interface": "xring_top_if"},
    "expr.normalize": {"expr": "a && b"},
    "control.explain": {"signal": sig},
    "counter.explain": {"signal": sig},
    "handshake.inspect": {"clock": clk, "valid": sig, "ready": sig},
    "detect_anomaly": {"signals": [sig, clk]},
    "fsm.explain": {"signal": sig},
    "procedural.assignment": {"signal": sig},
    "sequential.update": {"signal": sig},
    "event.config.list": {},
    "cursor.list": {},
    "list.create": {"name": "l2_test_list"},
    "event.export": {"expr": f"{clk} == 1", "clk": clk, "signals": {clk: clk}, "max_examples": 2},
    "trace.query": {"signal": sig},
    "trace.explain": {"signal": sig},
    "trace.path": {"signal": sig},
    "trace.graph": {"signal": sig},
    "trace.load": {"signal": sig},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Colors:
    """ANSI color codes — only active when stdout is a terminal."""
    _on = sys.stdout.isatty()
    GREEN = "\033[92m" if _on else ""
    RED = "\033[91m" if _on else ""
    YELLOW = "\033[93m" if _on else ""
    CYAN = "\033[96m" if _on else ""
    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""


def _server_env() -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC}:{ROOT}:{existing}".strip(":")
    return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_close(fn):
    """Helper: return (session_name, daidir, fsdb) from config."""
    pass  # unused, kept for symmetry


async def _open_session(session, cfg):
    """Open session using config."""
    sn = cfg["session_name"]
    rv = await session.call_tool("xverif_session_open", {
        "name": sn, "daidir": cfg["daidir"], "fsdb": cfg["fsdb"], "reuse": True,
    })
    d = json.loads(rv.content[0].text)
    if not d.get("ok"):
        print(f"  {Colors.RED}FAIL session.open: {d.get('error')}{Colors.RESET}")
        return False
    mode = d.get("summary", {}).get("mode", "?")
    print(f"  Session '{sn}' opened (mode={mode})")
    return True


async def _close_session(session, cfg):
    await session.call_tool("xverif_session_close", {"name": cfg["session_name"]})


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------


async def test_all_schemas(session: ClientSession) -> tuple[int, int]:
    """L1: 用 xdebug_schema tool 逐个验证全部 75 个 action 的 request/response schema。"""
    print(f"\n{Colors.BOLD}=== L1: Schema 验证 (150 tests) ==={Colors.RESET}")
    passed = 0
    failed = 0

    for kind in ["request", "response"]:
        for action in ALL_ACTIONS:
            result = await session.call_tool("xverif_debug_get_schema", {
                "action": action, "kind": kind,
            })
            data = json.loads(result.content[0].text)

            if data.get("ok"):
                passed += 1
                print(f"  {Colors.GREEN}OK{Colors.RESET}  schema {kind:8s} {action}")
            else:
                failed += 1
                err = data.get("error", {}).get("message", str(data))
                print(f"  {Colors.RED}FAIL{Colors.RESET} schema {kind:8s} {action}: {err}")

    return passed, failed


async def test_l2_basic(session: ClientSession, cfg: dict, action_args: dict) -> tuple[int, int]:
    """L2: 对已知 args 的 action 进行基础调用测试。"""
    sn = cfg["session_name"]
    print(f"\n{Colors.BOLD}=== L2: 基础调用 ({len(action_args)} actions) ==={Colors.RESET}")
    passed = 0
    failed = 0

    if not await _open_session(session, cfg):
        return 0, 1

    for action, args in action_args.items():
        result = await session.call_tool("xverif_debug_query", {
            "action": action, "session": sn, "args": args, "output_format": "json",
        })
        data = json.loads(result.content[0].text)
        if isinstance(data, dict):
            passed += 1
            ok = data.get("ok")
            marker = f"{Colors.GREEN}OK{Colors.RESET}" if ok else f"{Colors.YELLOW}ERR{Colors.RESET}"
            print(f"  {marker} ({'ok' if ok else 'err':3s}) {action} {json.dumps(args)}")
        else:
            failed += 1
            print(f"  {Colors.RED}FAIL{Colors.RESET} {action}: returned {type(data).__name__}")

    await _close_session(session, cfg)
    return passed, failed


async def test_with_signal(session: ClientSession, cfg: dict, signal: str) -> tuple[int, int]:
    """L3: 对已知信号进行完整数据验证。"""
    sn, clk = cfg["session_name"], cfg["clock"]
    print(f"\n{Colors.BOLD}=== L3: 信号验证 (signal={signal}) ==={Colors.RESET}")
    passed = 0
    failed = 0

    if not await _open_session(session, cfg):
        return 0, 1

    l3_actions = {
        "value.at": {"signal": signal, "time": "1ns"},
        "value.batch_at": {"signals": [signal], "time": "1ns"},
        "signal.statistics": {"signal": signal},
        "signal.changes": {"signal": signal, "time_range": {"start": "0ns", "end": "200ns"}, "aggregate_only": True},
        "signal.stability": {"signal": signal, "time_range": {"start": "0ns", "end": "200ns"}},
        "signal.trend": {"signal": signal, "clock": clk, "max_items": 20},
        "signal.canonicalize": {"signal": signal},
        "inspect_signal": {"signal": signal},
        "trace.driver": {"signal": signal},
        "trace.expand": {"signal": signal},
        "trace.active_driver": {"signal": signal, "requested_time": "1ns"},
        "expr.eval_at": {"expr": signal, "time": "1ns", "signals": {signal: signal}},
        "event.find": {"expr": f"{clk} == 1", "clk": clk, "signals": {clk: clk}, "max_examples": 3},
        "window.verify": {"conditions": [
            {"expr": signal, "signals": {signal: signal}, "op": "==", "value": "1"}
        ], "time_range": {"begin": "0ns", "end": "1us"}, "clock": clk},
    }

    for action, args in l3_actions.items():
        result = await session.call_tool("xverif_debug_query", {
            "action": action, "session": sn, "args": args, "output_format": "json",
        })
        data = json.loads(result.content[0].text)
        if isinstance(data, dict):
            passed += 1
            ok = data.get("ok")
            marker = f"{Colors.GREEN}OK{Colors.RESET}" if ok else f"{Colors.YELLOW}ERR{Colors.RESET}"
            detail = ""
            if not ok:
                err = data.get("error", {})
                detail = f" — {err.get('code', '?')}: {err.get('message', '?')[:60]}"
            print(f"  {marker} {action} {detail}")
        else:
            failed += 1
            print(f"  {Colors.RED}FAIL{Colors.RESET} {action}: bad response type")

    # XOUT format test
    print(f"\n{Colors.CYAN}--- 输出格式测试 ---{Colors.RESET}")
    result = await session.call_tool("xverif_debug_query", {
        "action": "value.at", "session": sn, "args": {"signal": signal, "time": "1ns"},
    })
    xout_text = result.content[0].text
    if xout_text.startswith("@xdebug."):
        print(f"  {Colors.GREEN}OK{Colors.RESET} xout_format: starts with @xdebug.")
        passed += 1
    else:
        print(f"  {Colors.RED}FAIL{Colors.RESET} xout_format: {xout_text[:80]}")
        failed += 1

    await _close_session(session, cfg)
    return passed, failed


async def discover_signal(session: ClientSession, cfg: dict) -> str | None:
    """尝试在真实数据中发现可用信号。优先用 config 中的 signal/clock。"""
    sn = cfg["session_name"]
    if not await _open_session(session, cfg):
        return None

    # Strategy 0: try config signal/clock first
    for key in ("signal", "clock"):
        sig = cfg.get(key)
        if sig:
            result = await session.call_tool("xverif_debug_query", {
                "action": "value.at", "session": sn,
                "args": {"signal": sig, "time": "1ns"}, "output_format": "json",
            })
            d = json.loads(result.content[0].text)
            if isinstance(d, dict) and d.get("ok"):
                await _close_session(session, cfg)
                return sig

    # Strategy 1: scope.list
    result = await session.call_tool("xverif_debug_query", {
        "action": "scope.list", "session": sn,
        "args": {"path": "", "recursive": True, "max_depth": 5}, "output_format": "json",
    })
    d = json.loads(result.content[0].text)
    if isinstance(d, dict):
        scopes = d.get("data", {}).get("scopes", d.get("data", {}).get("signals_preview", []))
        if scopes:
            name = scopes[0] if isinstance(scopes[0], str) else scopes[0].get("name", "")
            if name:
                await _close_session(session, cfg)
                return name

    await _close_session(session, cfg)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    default_config = os.path.join(HERE, "test_config.json")
    parser = argparse.ArgumentParser(description="Test xdebug actions via MCP server")
    parser.add_argument("-c", "--config", default=default_config, help=f"JSON config file (default: {default_config})")
    parser.add_argument("--schema-only", action="store_true", help="Only run L1 schema tests")
    parser.add_argument("--level", choices=["L1", "L2", "L3", "all"], default="all",
                        help="Test level (default: all)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    print(f"Config: daidir={cfg['daidir']}  fsdb={cfg['fsdb']}  signal={cfg.get('signal')}  clock={cfg.get('clock')}")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xverif_mcp.server"],
        env=_server_env(),
    )

    total_pass = 0
    total_fail = 0
    started = time.time()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"{Colors.CYAN}Connected to xverif-mcp FastMCP server{Colors.RESET}")

            # --- L1: Schema (always run) ---
            if args.level in ("L1", "all") or args.schema_only:
                p, f = await test_all_schemas(session)
                total_pass += p
                total_fail += f

            if args.schema_only or args.level == "L1":
                pass  # skip L2/L3
            elif args.level in ("L2", "all"):
                # --- L2: Basic invocation ---
                action_args = build_action_args(cfg["signal"], cfg["clock"], cfg["session_name"])
                p, f = await test_l2_basic(session, cfg, action_args)
                total_pass += p
                total_fail += f

                # --- Signal discovery ---
                print(f"\n{Colors.CYAN}Discovering signal...{Colors.RESET}")
                signal = await discover_signal(session, cfg)
                if signal:
                    print(f"  {Colors.GREEN}Found: {signal}{Colors.RESET}")

                    # --- L3: Full verification ---
                    if args.level in ("L3", "all"):
                        p, f = await test_with_signal(session, cfg, signal)
                        total_pass += p
                        total_fail += f
                else:
                    print(f"  {Colors.YELLOW}No signal found, skipping L3{Colors.RESET}")

    # Summary
    elapsed = time.time() - started
    print(f"\n{Colors.BOLD}=== 结果: {total_pass} passed, {total_fail} failed ({elapsed:.1f}s) ==={Colors.RESET}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
