"""FastMCP registration tests for xverif-mcp."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import anyio
import pytest

XDEBUG_DIR = Path(__file__).resolve().parents[2] / "xdebug"
sys.path = [
    path for path in sys.path
    if Path(path or os.getcwd()).resolve() != XDEBUG_DIR
]

sys.modules.pop("mcp", None)
pytest.importorskip("mcp")


POLICY_ENV = [
    "XVERIF_MCP_ENABLE_COMMON",
    "XVERIF_MCP_ENABLE_DEBUG",
    "XVERIF_MCP_ENABLE_COV",
    "XVERIF_MCP_ENABLE_BIT",
    "XVERIF_MCP_ENABLE_ENTRY",
    "XVERIF_MCP_ENABLE_LOC",
    "XVERIF_MCP_ENABLE_SVA",
]


def _server(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None):
    for name in POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in (overrides or {}).items():
        monkeypatch.setenv(name, value)
    if "xverif_mcp.server" in sys.modules:
        return importlib.reload(sys.modules["xverif_mcp.server"])
    return importlib.import_module("xverif_mcp.server")


def _tool_names(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> set[str]:
    server = _server(monkeypatch, overrides)

    async def _run() -> set[str]:
        tools = await server.mcp.list_tools()
        return {tool.name for tool in tools}

    return anyio.run(_run)


def _call_tool(monkeypatch: pytest.MonkeyPatch, name: str, args: dict | None = None,
               overrides: dict[str, str] | None = None):
    server = _server(monkeypatch, overrides)

    async def _run():
        result = await server.mcp.call_tool(name, args or {})
        if isinstance(result, tuple):
            return result
        return result, None

    return anyio.run(_run)


def test_mcp_server_initialize(monkeypatch: pytest.MonkeyPatch):
    server = _server(monkeypatch)
    assert server.mcp.name == "xverif"


def test_stateful_cleanup_calls_debug_and_cov(monkeypatch: pytest.MonkeyPatch):
    server = _server(monkeypatch)
    calls: list[str] = []

    class DummyAdapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def close_all(self) -> None:
            calls.append(self.name)

    monkeypatch.setattr(server, "debug", DummyAdapter("debug"))
    monkeypatch.setattr(server, "cov", DummyAdapter("cov"))

    server._cleanup_stateful_sessions()

    assert calls == ["debug", "cov"]


def test_lifespan_cleanup_runs_on_exit(monkeypatch: pytest.MonkeyPatch):
    server = _server(monkeypatch)
    calls: list[str] = []

    class DummyAdapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def close_all(self) -> None:
            calls.append(self.name)

    monkeypatch.setattr(server, "debug", DummyAdapter("debug"))
    monkeypatch.setattr(server, "cov", DummyAdapter("cov"))

    async def _run() -> None:
        async with server._mcp_lifespan(server.mcp):
            assert calls == []

    anyio.run(_run)

    assert calls == ["debug", "cov"]


def test_mcp_tools_list(monkeypatch: pytest.MonkeyPatch):
    """tools/list must include all expected read-only tool names by default."""
    names = _tool_names(monkeypatch)
    assert "xverif_ping" in names
    assert "xverif_debug_query" in names
    assert "xverif_debug_session_open" in names
    assert "xverif_cov_session_open" in names
    assert "xverif_cov_query" in names
    assert "xverif_debug_list_actions" in names
    assert "xverif_debug_get_schema" in names
    assert "xverif_debug_session_list" in names
    assert "xverif_debug_session_doctor" in names
    assert "xverif_debug_session_use" not in names
    assert "xverif_debug_session_close" in names
    assert "xverif_debug_session_kill" in names
    assert "xverif_debug_session_gc" in names
    assert "xverif_cov_session_list" in names
    assert "xverif_cov_session_doctor" in names
    assert "xverif_cov_session_close" in names
    assert "xverif_cov_session_kill" in names
    assert "xverif_cov_session_gc" in names
    assert "xverif_session_open" not in names
    assert "xverif_session_list" not in names
    assert "xverif_session_use" not in names
    assert "xverif_session_close" not in names
    assert "xverif_debug_raw_request" not in names
    assert "xverif_cov_raw_request" not in names
    assert "xverif_wave_value_at" not in names
    assert "xverif_wave_changes" not in names
    assert "xverif_wave_generate_rc" not in names
    assert "xverif_waveform_render_list" not in names
    assert "xverif_design_trace_driver" not in names
    assert "xverif_tools" in names
    assert "xverif_bit_eval" in names
    assert "xverif_entry_decode" in names
    assert "xverif_loc_resolve" in names
    assert "xverif_sva_explain_property" in names
    assert all(not name.startswith("xverif_" + "context") for name in names)


def test_cov_tools_use_session_id_contract(monkeypatch: pytest.MonkeyPatch):
    server = _server(monkeypatch)

    async def _schemas():
        return {tool.name: tool.inputSchema for tool in await server.mcp.list_tools()}

    schemas = anyio.run(_schemas)
    for name in (
        "xverif_cov_query", "xverif_cov_session_doctor",
        "xverif_cov_session_close", "xverif_cov_session_kill",
    ):
        properties = schemas[name]["properties"]
        assert "session_id" in properties
        assert "session" not in properties
        assert "name" not in properties


def test_mcp_ping_call(monkeypatch: pytest.MonkeyPatch):
    """Calling xverif_ping should return a string containing 'pong'."""
    content, structured = _call_tool(monkeypatch, "xverif_ping")
    assert "pong" in content[0].text.lower()
    assert structured["result"] == "pong"


def test_debug_list_actions_verbose_maps_to_native_catalog_projection(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []
    server = _server(monkeypatch)
    monkeypatch.setattr(
        server.XverifDebugAdapter,
        "actions",
        lambda self, verbose=False: calls.append(verbose) or {"ok": True},
    )

    content, _ = _call_tool(monkeypatch, "xverif_debug_list_actions", {"verbose": True})

    assert json.loads(content[0].text)["ok"] is True
    assert calls == [True]


def test_tool_group_disable_sva(monkeypatch: pytest.MonkeyPatch):
    env = {"XVERIF_MCP_ENABLE_SVA": "0"}
    names = _tool_names(monkeypatch, env)
    assert "xverif_sva_explain_property" not in names
    assert "xverif_debug_query" in names

    content, _ = _call_tool(monkeypatch, "xverif_tools", {}, env)
    payload = json.loads(content[0].text)
    catalog = {tool["name"] for tool in payload["tools"]}
    assert "xverif_sva_explain_property" not in catalog


def test_tool_group_disable_debug(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"XVERIF_MCP_ENABLE_DEBUG": "0"})
    assert "xverif_debug_query" not in names
    assert "xverif_debug_session_open" not in names
    assert "xverif_wave_value_at" not in names
    assert "xverif_waveform_render_list" not in names
    assert "xverif_cov_query" in names
    assert "xverif_bit_eval" in names


def test_tool_group_disable_cov(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"XVERIF_MCP_ENABLE_COV": "0"})
    assert "xverif_cov_query" not in names
    assert "xverif_cov_session_open" not in names
    assert "xverif_debug_query" in names


def test_cov_session_fake_lifecycle(monkeypatch: pytest.MonkeyPatch):
    overrides = {
        "XVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "XVERIF_MCP_BACKEND": "direct",
    }
    server = _server(monkeypatch, overrides)

    async def _run():
        opened = await server.mcp.call_tool(
            "xverif_cov_session_open",
            {"name": "cov_fake", "vdb": "fake"},
        )
        queried = await server.mcp.call_tool(
            "xverif_cov_query",
            {"session_id": "cov_fake", "action": "code_coverage.holes",
             "args": {"metrics": ["toggle", "branch"]},
             "limits": {"max_items": 1},
             "output_format": "json"},
        )
        closed = await server.mcp.call_tool(
            "xverif_cov_session_close",
            {"session_id": "cov_fake"},
        )
        return opened, queried, closed

    opened, queried, _ = anyio.run(_run)
    opened_payload = json.loads(opened[0].text)
    queried_payload = json.loads(queried[0].text)
    assert opened_payload["ok"] is True
    assert queried_payload["summary"]["matched_count"] == 1
    assert queried_payload["summary"]["returned"] == 1


@pytest.mark.parametrize(
    ("env_name", "missing", "present"),
    [
        ("XVERIF_MCP_ENABLE_BIT", "xverif_bit_eval", "xverif_entry_decode"),
        ("XVERIF_MCP_ENABLE_ENTRY", "xverif_entry_decode", "xverif_bit_eval"),
        ("XVERIF_MCP_ENABLE_LOC", "xverif_loc_resolve", "xverif_bit_eval"),
    ],
)
def test_tool_group_disable_stateless_groups(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    missing: str,
    present: str,
):
    names = _tool_names(monkeypatch, {env_name: "0"})
    assert missing not in names
    assert present in names


def test_tool_group_disable_common(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"XVERIF_MCP_ENABLE_COMMON": "0"})
    assert "xverif_ping" not in names
    assert "xverif_tools" not in names
    assert "xverif_tool_help" not in names
    assert "xverif_debug_query" in names


def test_invalid_bool_policy_warning(monkeypatch: pytest.MonkeyPatch):
    content, _ = _call_tool(
        monkeypatch,
        "xverif_tools",
        {},
        {"XVERIF_MCP_ENABLE_SVA": "maybe"},
    )
    payload = json.loads(content[0].text)
    assert "xverif_sva_explain_property" in {tool["name"] for tool in payload["tools"]}
    assert payload["policy"]["warnings"]
    assert "XVERIF_MCP_ENABLE_SVA" in payload["policy"]["warnings"][0]


def test_tool_help_disabled_tool_is_hidden(monkeypatch: pytest.MonkeyPatch):
    content, _ = _call_tool(
        monkeypatch,
        "xverif_tool_help",
        {"name": "xverif_sva_explain_property"},
        {"XVERIF_MCP_ENABLE_SVA": "0"},
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TOOL_NOT_ENABLED"


def test_output_path_in_tool_schema(monkeypatch: pytest.MonkeyPatch):
    """xverif_ping schema must expose xverif_output_path and xverif_output_append."""
    server = _server(monkeypatch)

    async def _run():
        tools = await server.mcp.list_tools()
        ping = next(t for t in tools if t.name == "xverif_ping")
        schema = ping.inputSchema
        props = schema.get("properties", {})
        assert "xverif_output_path" in props
        assert "xverif_output_append" in props

    anyio.run(_run)


def test_output_path_writes_response(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Calling a tool with xverif_output_path writes the response to that file."""
    output_file = tmp_path / "rsp.txt"
    content, _ = _call_tool(
        monkeypatch,
        "xverif_ping",
        {"xverif_output_path": str(output_file)},
    )
    assert "pong" in content[0].text.lower()
    assert output_file.exists()
    assert "pong" in output_file.read_text().lower()


def test_output_path_append(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """xverif_output_append=True appends instead of overwriting."""
    output_file = tmp_path / "rsp.txt"
    output_file.write_text("existing\n")
    _call_tool(monkeypatch, "xverif_ping",
               {"xverif_output_path": str(output_file), "xverif_output_append": True})
    text = output_file.read_text()
    assert text.startswith("existing\n")
    assert "pong" in text.lower()


def test_output_path_does_not_affect_response(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Not passing xverif_output_path has no effect on normal response."""
    content, _ = _call_tool(monkeypatch, "xverif_ping", {})
    assert "pong" in content[0].text.lower()


def test_output_path_invalid_dir_no_crash(monkeypatch: pytest.MonkeyPatch):
    """If the output path is invalid, the tool still returns normally."""
    content, _ = _call_tool(
        monkeypatch,
        "xverif_ping",
        {"xverif_output_path": "/nonexistent/dir/rsp.txt"},
    )
    assert "pong" in content[0].text.lower()


def test_batch_fake_lifecycle(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """xverif_batch with fake cov session + ping + bit_eval in one file."""
    batch_file = tmp_path / "batch.ndjson"
    output_file = tmp_path / "results.ndjson"

    overrides = {
        "XVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "XVERIF_MCP_BACKEND": "direct",
    }

    batch_file.write_text("\n".join([
        json.dumps({"tool": "xverif_cov_session_open",
                     "args": {"name": "cov_fake", "vdb": "fake"}}),
        json.dumps({"tool": "xverif_cov_query",
                     "args": {"session_id": "cov_fake", "action": "code_coverage.holes",
                              "args": {"metrics": ["line"], "limits": {"max_items": 2}},
                              "output_format": "json"}}),
        json.dumps({"tool": "xverif_cov_session_close",
                     "args": {"session_id": "cov_fake"}}),
        json.dumps({"tool": "xverif_ping", "args": {}}),
        json.dumps({"tool": "xverif_bit_eval",
                     "args": {"expr": "2 + 3"}}),
    ]) + "\n")

    content, _ = _call_tool(
        monkeypatch,
        "xverif_batch",
        {"batch_file": str(batch_file), "output_file": str(output_file)},
        overrides,
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["total"] == 5
    assert payload["ok_count"] == 5
    assert payload["failed_count"] == 0

    lines = [json.loads(l) for l in output_file.read_text().splitlines() if l]
    assert len(lines) == 5
    assert all(r["ok"] for r in lines)


def test_batch_format_errors(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Invalid JSON and missing tool field are written as errors, not executed."""
    batch_file = tmp_path / "batch.ndjson"
    output_file = tmp_path / "results.ndjson"

    overrides = {
        "XVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "XVERIF_MCP_BACKEND": "direct",
    }

    batch_file.write_text("\n".join([
        "not json at all",
        json.dumps({"args": {"expr": "1+1"}}),  # missing tool
        json.dumps({"tool": "xverif_ping", "args": {}}),
    ]) + "\n")

    content, _ = _call_tool(
        monkeypatch,
        "xverif_batch",
        {"batch_file": str(batch_file), "output_file": str(output_file)},
        overrides,
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["total"] == 3
    assert payload["ok_count"] == 1
    assert payload["failed_count"] == 2

    lines = [json.loads(l) for l in output_file.read_text().splitlines() if l]
    assert len(lines) == 3
    assert lines[0]["tool"] is None
    assert lines[0]["ok"] is False
    assert "INVALID_JSON" in lines[0]["error"]
    assert lines[1]["tool"] is None
    assert lines[1]["ok"] is False
    assert "MISSING_TOOL_FIELD" in lines[1]["error"]
    assert lines[2]["tool"] == "xverif_ping"
    assert lines[2]["ok"] is True


def test_batch_file_not_found(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """xverif_batch on a nonexistent file returns FILE_NOT_FOUND error."""
    content, _ = _call_tool(
        monkeypatch,
        "xverif_batch",
        {"batch_file": "/nonexistent/batch.ndjson",
         "output_file": str(tmp_path / "out.ndjson")},
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FILE_NOT_FOUND"
