"""FastMCP server for xdebug — built on the official Python MCP SDK."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from .backend import XDebugMcpBackend, error_payload

Json = Dict[str, Any]

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
xdebug-mcp exposes deterministic xdebug tools to AI agents.

Typical Agent workflow:
1. Call xdebug_actions to inspect available xdebug actions.
2. Call xdebug_schema(action) if you need the exact request shape for an action.
3. Call xdebug_session_open to open or reuse a named session (required for FSDB/daidir queries).
4. Call xdebug_query with action + args to run the query.

Output format:
- output_format=xout (default) — AI-readable structured text, starts with "@xdebug.".
- output_format=json  — raw xdebug JSON object.
- output_format=envelope — wrapper envelope with stdout/stderr/exit_code, for debugging.

Backends:
- direct: starts local tools/xdebug --stdio-loop.
- lsf: starts one bsub -I tools/xdebug --stdio-loop job per session.
Both backends share the same JSONL loop protocol. No router, no TCP endpoint.

If xdebug_query returns error.code=SESSION_LOST:
  - the MCP server has already terminated the broken subprocess / LSF job
  - the session mapping has been evicted
  - the agent must explicitly call xdebug_session_open before retrying
No automatic retry or reopen is performed by the server.
"""

mcp = FastMCP(
    name="xdebug-mcp",
    instructions=INSTRUCTIONS,
)

backend = XDebugMcpBackend()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _tool_error(code: str, message: str) -> dict:
    return error_payload(code, message)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def xdebug_ping() -> str:
    """Ping the xdebug MCP backend. Use this to check whether the MCP server is alive."""
    return backend.ping()


@mcp.tool()
def xdebug_actions() -> dict:
    """Return the xdebug action catalog.

    Call this before xdebug_query when you are unsure which action to use.
    Returns the list of all available xdebug actions with brief descriptions.
    """
    return backend.request({"api_version": "xdebug.v1", "action": "actions"})


@mcp.tool()
def xdebug_schema(action: str, kind: str = "request") -> dict:
    """Return an action-specific xdebug JSON schema.

    Args:
        action: The xdebug action name (e.g. "value.at", "trace.drivers").
        kind: "request" for input schema, "response" for output schema.
    """
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return backend.request({
        "api_version": "xdebug.v1",
        "action": "schema",
        "args": {"action": action, "kind": kind},
    })


@mcp.tool()
def xdebug_direct_request(request: dict) -> dict:
    """Run a complete xdebug JSON request through the direct backend only.

    This tool does NOT use LSF sessions or the router.
    Use xdebug_query for normal session-based debug queries.

    Args:
        request: A full xdebug JSON request object with api_version, action, args, etc.
    """
    if not isinstance(request, dict):
        return _tool_error("INVALID_ARGUMENT", "request must be a JSON object")
    return backend.request(request)


@mcp.tool()
def xdebug_request(request: dict) -> dict:
    """[Compatibility alias] Same as xdebug_direct_request.

    Always uses the direct backend; does not use LSF sessions.
    Prefer xdebug_query for normal Agent workflows.
    """
    return xdebug_direct_request(request)


@mcp.tool()
def xdebug_session_open(
    name: str,
    daidir: Optional[str] = None,
    fsdb: Optional[str] = None,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
    reuse: bool = True,
    reopen: bool = False,
    make_default: bool = True,
) -> dict:
    """Open a loop-backed xdebug session immediately (eager open).

    In direct mode, starts a local tools/xdebug --stdio-loop process.
    In LSF mode, starts a bsub -I tools/xdebug --stdio-loop job.

    After opening, use xdebug_query(session=name, ...) or rely on the default session.

    Args:
        name: Unique session alias (e.g. "wave_a").
        daidir: Path to daidir (design database directory).
        fsdb: Path to FSDB waveform file.
        queue: LSF queue name (LSF backend only).
        resource: LSF resource string (LSF backend only).
        reuse: If True, reuse an existing session with the same name.
        reopen: If True, force reopen even if a session exists.
        make_default: If True, set this session as the default for xdebug_query.
    """
    return backend.session_open(
        name=name,
        daidir=daidir,
        fsdb=fsdb,
        queue=queue,
        resource=resource,
        reuse=reuse,
        reopen=reopen,
        make_default=make_default,
    )


@mcp.tool()
def xdebug_session_list(include_native: bool = False) -> dict:
    """List sessions known by this MCP server.

    Args:
        include_native: If True, also include native xdebug sessions from session.list.
    """
    return backend.session_list(include_native=include_native)


@mcp.tool()
def xdebug_session_use(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Set the default session used by xdebug_query.

    Provide either name or session_id. The default session is used when
    xdebug_query is called without an explicit session or target.

    Args:
        name: Session alias previously opened with xdebug_session_open.
        session_id: Raw session ID string.
    """
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return backend.session_use(key)


@mcp.tool()
def xdebug_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close the xdebug session, send stdio.quit, then terminate the loop process.
    In LSF mode also bkills the job as fallback.

    Args:
        name: Session alias to close.
        session_id: Raw session ID to close.
    """
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return backend.session_close(key)


@mcp.tool()
def xdebug_query(
    action: str,
    args: Optional[dict] = None,
    target: Optional[dict] = None,
    session: Optional[str] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "xout",
) -> Any:
    """Run an xdebug action.

    Recommended Agent workflow:
    1. Call xdebug_actions if you don't know available actions.
    2. Call xdebug_schema(action) if you need the exact request shape.
    3. Call xdebug_session_open first for repeated FSDB/daidir queries.
    4. Call xdebug_query with action + args.

    Args:
        action: The xdebug action name (e.g. "value.at", "trace.drivers").
        args: Action-specific arguments dict (e.g. {"signal": "top.clk", "time": "1ns"}).
        target: Explicit target with daidir/fsdb/session_id. Overrides session.
        session: Named session alias (from xdebug_session_open). Uses default if omitted.
        limits: Query limits dict (max_rows, timeout, etc.).
        output: Output control dict (rarely needed).
        output_format:
            "xout" (default) — AI-readable structured text, starts with "@xdebug.".
            "json" — raw xdebug JSON dict.
            "envelope" — wrapper envelope with stdout/stderr/exit_code for debugging.
    """
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT", "output_format must be 'xout', 'json', or 'envelope'")
    return backend.query(
        action=action,
        args=args or {},
        target=target,
        session=session,
        limits=limits,
        output=output,
        output_format=output_format,
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
