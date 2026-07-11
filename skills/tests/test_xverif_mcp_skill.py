from __future__ import annotations

import json
import re
from pathlib import Path

import anyio
import jsonschema

import xverif_mcp.server as server
from skill_test_utils import assert_markdown_links, fenced_json
from xcov.schemas import schema_for_action
from xverif_loop.wrapper import METHOD_PARAM_CONTRACTS, validate_method_params


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "xverif-mcp"


def _tools() -> dict[str, object]:
    async def collect() -> dict[str, object]:
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    return anyio.run(collect)


def test_xverif_mcp_links_and_registered_tool_coverage() -> None:
    assert_markdown_links(SKILL)
    text = "\n".join(path.read_text(encoding="utf-8") for path in SKILL.rglob("*.md"))
    tools = _tools()
    catalog = {entry["name"] for entry in server.TOOL_CATALOG}
    assert set(tools) == catalog
    for name in sorted(tools):
        assert re.search(rf"\b{re.escape(name)}\b", text), f"undocumented MCP tool: {name}"


def test_mcp_tool_examples_validate_against_fastmcp_schemas() -> None:
    tools = _tools()
    validated = 0
    for path, payload in fenced_json(SKILL):
        name = payload.get("tool")
        if not isinstance(name, str):
            continue
        assert name in tools, f"unknown MCP tool in {path}: {name}"
        args = payload.get("args", {})
        schema = getattr(tools[name], "inputSchema")
        jsonschema.Draft202012Validator(schema).validate(args)
        validated += 1
    assert validated >= 20


def test_sdk_free_examples_validate_against_method_and_action_contracts() -> None:
    validated = 0
    for path, payload in fenced_json(SKILL / "references/sdk-free-loop"):
        method = payload.get("method")
        if not isinstance(method, str):
            continue
        assert method in METHOD_PARAM_CONTRACTS, f"unknown SDK-free method in {path}: {method}"
        params = payload.get("params", {})
        assert isinstance(params, dict)
        validate_method_params(method, params)
        if method == "debug.query":
            request = {
                "api_version": "xdebug.v1",
                "action": params["action"],
                "target": {"session_id": "doc-session"},
                "args": params.get("args", {}),
            }
            schema_path = (
                ROOT / "xdebug/schemas/v1/actions"
                / f"{params['action']}.request.schema.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(request)
        elif method == "cov.query":
            request = {
                "api_version": "xcov.v1",
                "action": params["action"],
                "target": {"session_id": "doc-session"},
                "args": params.get("args", {}),
            }
            jsonschema.Draft202012Validator(
                schema_for_action(params["action"], "request")
            ).validate(request)
        validated += 1
    assert validated >= 1


def test_removed_raw_and_alias_tools_do_not_reappear() -> None:
    removed = {
        "xverif_cov_raw_request",
        "xverif_wave_value_at",
        "xverif_wave_changes",
        "xverif_wave_generate_rc",
        "xverif_waveform_render_list",
        "xverif_design_trace_driver",
    }
    tools = _tools()
    assert removed.isdisjoint(tools)
    debug_query_schema = getattr(tools["xverif_debug_query"], "inputSchema")
    assert "output" not in debug_query_schema["properties"]
    prompt = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    assert "raw_request" not in prompt
    assert "session_id/action/args/limits/output" not in prompt
