"""xverif-mcp — unified MCP server for all xverif tools."""
from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.errors import error_payload

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
xverif-mcp exposes deterministic local tools for chip verification debug agents.
The xdebug backend is stateful and may run locally or through LSF.
Other tools (xbit, xentry, xloc, xberif, xsva) are stateless CLI adapters.

Typical workflow:
1. Call xverif_tools to discover available tools.
2. For debug queries: xverif_debug_session_open → xverif_debug_query.
3. For stateless queries: call the tool directly (e.g., xverif_bit_eval).

If xverif_debug_query returns error.code=SESSION_LOST:
  - the MCP server has already terminated the broken subprocess / LSF job
  - the session mapping has been evicted
  - the agent must explicitly call xverif_debug_session_open before retrying
No automatic retry or reopen is performed by the server.
"""

mcp = FastMCP(
    name="xverif-mcp",
    instructions=INSTRUCTIONS,
)

debug = XverifDebugAdapter()


def _tool_error(code: str, message: str) -> dict:
    return error_payload(code, message)


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_ping() -> str:
    """Ping the xverif MCP server. Use this to check whether the server is alive."""
    return debug.ping()


# ---------------------------------------------------------------------------
# Debug tools (xdebug — the only stateful backend)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_debug_actions() -> dict:
    """Return the xdebug action catalog.

    Call this before xverif_debug_query when you are unsure which action to use.
    Returns the list of all available xdebug actions with brief descriptions.
    """
    return debug.actions()


@mcp.tool()
def xverif_debug_schema(action: str, kind: str = "request") -> dict:
    """Return an action-specific xdebug JSON schema.

    Args:
        action: The xdebug action name (e.g. "value.at", "trace.drivers").
        kind: "request" for input schema, "response" for output schema.
    """
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return debug.schema(action, kind)


@mcp.tool()
def xverif_debug_request(request: dict, output_format: str = "json") -> dict:
    """Run a complete xdebug JSON request (one-shot, no session).

    This tool does NOT use sessions. For session-based queries, use
    xverif_debug_query instead.

    Args:
        request: A full xdebug JSON request object with api_version, action, args, etc.
        output_format: "json" (default), "xout", or "envelope".
    """
    if not isinstance(request, dict):
        return _tool_error("INVALID_ARGUMENT", "request must be a JSON object")
    return debug.request(request, output_format)


@mcp.tool()
def xverif_debug_session_open(
    name: str,
    daidir: Optional[str] = None,
    fsdb: Optional[str] = None,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
    reuse: bool = True,
    reopen: bool = False,
    make_default: bool = True,
) -> dict:
    """Open a loop-backed xdebug session (eager open).

    In direct mode, starts a local tools/xdebug --stdio-loop process.
    In LSF mode, starts a bsub -I tools/xdebug --stdio-loop job.

    Args:
        name: Unique session alias (e.g. "wave_a").
        daidir: Path to daidir (design database directory).
        fsdb: Path to FSDB waveform file.
        queue: LSF queue name (LSF backend only).
        resource: LSF resource string (LSF backend only).
        reuse: If True, reuse an existing session with the same name.
        reopen: If True, force reopen even if a session exists.
        make_default: If True, set this session as the default.
    """
    return debug.session_open(
        name=name, daidir=daidir, fsdb=fsdb, queue=queue,
        resource=resource, reuse=reuse, reopen=reopen,
        make_default=make_default,
    )


@mcp.tool()
def xverif_debug_session_list(include_native: bool = False) -> dict:
    """List xdebug sessions managed by this MCP server.

    Args:
        include_native: If True, also include native xdebug sessions.
    """
    return debug.session_list(include_native=include_native)


@mcp.tool()
def xverif_debug_session_use(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Set the default xdebug session used by xverif_debug_query.

    Args:
        name: Session alias previously opened with xverif_debug_session_open.
        session_id: Raw session ID string.
    """
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_use(key)


@mcp.tool()
def xverif_debug_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close and cleanup an xdebug session.

    Sends stdio.quit, terminates the loop process, and evicts the session
    from the manager. In LSF mode also bkill's the job as fallback.

    Args:
        name: Session alias to close.
        session_id: Raw session ID to close.
    """
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_close(key)


@mcp.tool()
def xverif_debug_query(
    action: str,
    args: Optional[dict] = None,
    target: Optional[dict] = None,
    session: Optional[str] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "xout",
) -> Any:
    """Run an xdebug action through a loop session.

    Recommended workflow:
    1. Call xverif_debug_actions if you don't know available actions.
    2. Call xverif_debug_schema(action) if you need the exact request shape.
    3. Call xverif_debug_session_open first for FSDB/daidir queries.
    4. Call xverif_debug_query with action + args.

    Args:
        action: The xdebug action name (e.g. "value.at", "trace.drivers").
        args: Action-specific arguments dict.
        target: Explicit target with daidir/fsdb/session_id. Overrides session.
        session: Named session alias. Uses default session if omitted.
        limits: Query limits dict (max_rows, timeout, etc.).
        output: Output control dict (rarely needed).
        output_format:
            "xout" (default) — AI-readable structured text.
            "json" — raw xdebug JSON dict.
            "envelope" — wrapper envelope for debugging.
    """
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'xout', 'json', or 'envelope'")
    return debug.query(
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
