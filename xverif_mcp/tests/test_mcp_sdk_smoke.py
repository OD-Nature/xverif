"""MCP SDK client integration tests for the xverif-mcp FastMCP server."""

from __future__ import annotations

import os
import sys

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


_XVERIF_MCP_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../xverif_mcp/src")
)


def _server_env() -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_XVERIF_MCP_SRC}:{existing}".strip(":")
    return env


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "xverif_mcp.server"],
        env=_server_env(),
    )


@pytest.mark.asyncio
async def test_mcp_server_initialize():
    """The FastMCP server should accept initialize and return capabilities."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            assert result is not None
            assert hasattr(result, "capabilities")


@pytest.mark.asyncio
async def test_mcp_tools_list():
    """tools/list must include all expected tool names."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "xverif_ping" in names
            assert "xverif_debug_query" in names
            assert "xverif_session_open" in names
            assert "xverif_debug_list_actions" in names
            assert "xverif_debug_get_schema" in names
            assert "xverif_session_list" in names
            assert "xverif_session_use" in names
            assert "xverif_session_close" in names
            assert "xverif_debug_raw_request" in names
            assert "xverif_tools" in names
            assert "xverif_bit_eval" in names
            assert "xverif_entry_decode" in names
            assert "xverif_loc_resolve" in names
            assert "xverif_context_status" in names
            assert "xverif_sva_explain_property" in names


@pytest.mark.asyncio
async def test_mcp_ping_call():
    """Calling xverif_ping should return a string containing 'pong'."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("xverif_ping", {})
            assert len(result.content) > 0
            text = result.content[0].text
            assert "pong" in text.lower()
