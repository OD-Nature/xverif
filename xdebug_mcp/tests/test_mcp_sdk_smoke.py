"""MCP SDK client integration tests for the xdebug-mcp FastMCP server."""

from __future__ import annotations

import os
import sys

import pytest

# Skip if MCP SDK is not installed (allows test collection to succeed
# even when mcp[cli] is not available).
mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


_XDEBUG_MCP_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)


def _server_env() -> dict:
    env = os.environ.copy()
    # Only add xdebug_mcp/src to PYTHONPATH — do NOT add xdebug/ directly
    # or it would shadow the pip-installed "mcp" package.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_XDEBUG_MCP_SRC}:{existing}".strip(":")
    return env


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "xdebug_mcp.server"],
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
            assert "xdebug_ping" in names
            assert "xdebug_query" in names
            assert "xdebug_session_open" in names
            assert "xdebug_direct_request" in names
            assert "xdebug_request" in names  # legacy alias
            assert "xdebug_actions" in names
            assert "xdebug_schema" in names
            assert "xdebug_session_list" in names
            assert "xdebug_session_use" in names
            assert "xdebug_session_close" in names


@pytest.mark.asyncio
async def test_mcp_ping_call():
    """Calling xdebug_ping should return a string containing 'pong'."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("xdebug_ping", {})
            assert len(result.content) > 0
            text = result.content[0].text
            assert "pong" in text.lower()
