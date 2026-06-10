"""xverif-mcp — unified MCP server for all xverif tools."""
from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.adapters.xbit import bit_conv, bit_eval, bit_slice, bit_check
from xverif_mcp.adapters.xentry import entry_decode, entry_explain, entry_validate
from xverif_mcp.adapters.xloc import loc_resolve, loc_context, loc_stats, loc_annotate
from xverif_mcp.adapters.xberif import (context_status, context_list_topics, context_brief,
                                         context_get, context_detail, context_validate,
                                         context_config_init, context_init, context_repair)
from xverif_mcp.adapters.xsva import sva_list, sva_scan, sva_parse, sva_explain, sva_render
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
# Bit tools (xbit — stateless CLI adapter)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_bit_conv(value: str, width: int = 0, signed: bool = False,
                     unsigned: bool = False, state: str = "2",
                     output_format: str = "json") -> Any:
    """Convert a value between radices and SV literal formats.

    Args:
        value: The value to convert (hex, binary, SV literal, etc.).
        width: Resize result to N bits (0 = keep original).
        signed: Treat as signed value.
        unsigned: Treat as unsigned value.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "xout".
    """
    return bit_conv(value, width=width, signed=signed, unsigned=unsigned,
                    state=state, output_format=output_format)


@mcp.tool()
def xverif_bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
                     signed: bool = False, unsigned: bool = False,
                     state: str = "2", output_format: str = "json") -> Any:
    """Evaluate a deterministic bit/expression calculation.

    Args:
        expr: Expression string (e.g. "0x10 + 0x1", "sig_a & sig_b").
        vars: Dict of variable name to literal value.
        width: Resize result to N bits.
        signed: Treat as signed value.
        unsigned: Treat as unsigned value.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "xout".
    """
    return bit_eval(expr, vars=vars, width=width, signed=signed,
                    unsigned=unsigned, state=state, output_format=output_format)


@mcp.tool()
def xverif_bit_slice(value: str, msb: int, lsb: int, state: str = "2",
                      output_format: str = "json") -> Any:
    """Extract a bit slice from a value.

    Args:
        value: The source value.
        msb: Most significant bit index.
        lsb: Least significant bit index.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "xout".
    """
    return bit_slice(value, msb, lsb, state=state, output_format=output_format)


@mcp.tool()
def xverif_bit_check(expr: str, vars: Optional[dict] = None,
                      values: Optional[str] = None, state: str = "2",
                      output_format: str = "json") -> Any:
    """Check a bit expression against expected values.

    Args:
        expr: Expression to evaluate.
        vars: Dict of variable name to literal value.
        values: Expected values to check against.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "xout".
    """
    return bit_check(expr, vars=vars, values=values, state=state,
                     output_format=output_format)


# ---------------------------------------------------------------------------
# Entry tools (xentry — stateless CLI adapter)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_entry_decode(config_path: str, input_path: str,
                         output_format: str = "json") -> Any:
    """Decode multi-beat byte fragments into raw field slices per config.

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Path to JSONL fragments input file.
        output_format: "json" or "xout".
    """
    return entry_decode(config_path, input_path, output_format=output_format)


@mcp.tool()
def xverif_entry_explain(config_path: str, output_format: str = "json") -> Any:
    """Explain the field layout defined by an entry config.

    Args:
        config_path: Path to YAML/JSON entry config file.
        output_format: "json" or "xout".
    """
    return entry_explain(config_path, output_format=output_format)


@mcp.tool()
def xverif_entry_validate(config_path: str,
                           input_path: Optional[str] = None,
                           output_format: str = "json") -> Any:
    """Validate an entry config (and optionally an input) without decoding.

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Optional path to JSONL fragments for deeper validation.
        output_format: "json" or "xout".
    """
    return entry_validate(config_path, input_path=input_path,
                          output_format=output_format)


# ---------------------------------------------------------------------------
# Location tools (xloc — stateless CLI adapter)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_loc_resolve(loc_id: str, map_path: str,
                        output_format: str = "json") -> Any:
    """Resolve a compressed loc_id (L_XXXXXXXX) to source file:line.

    Args:
        loc_id: The loc_id to resolve (e.g. L_00000001).
        map_path: Path to JSONL sidecar map file.
        output_format: "json" or "xout".
    """
    return loc_resolve(loc_id, map_path, output_format=output_format)


@mcp.tool()
def xverif_loc_context(loc_id: str, map_path: str, before: int = 20,
                        after: int = 20, output_format: str = "xout") -> Any:
    """Resolve a loc_id and show surrounding source code context.

    Args:
        loc_id: The loc_id to resolve.
        map_path: Path to JSONL sidecar map file.
        before: Lines to show before the target line.
        after: Lines to show after the target line.
        output_format: "json" or "xout".
    """
    return loc_context(loc_id, map_path, before=before, after=after,
                       output_format=output_format)


@mcp.tool()
def xverif_loc_stats(log_path: str, map_path: Optional[str] = None,
                      top: int = 20, output_format: str = "json") -> Any:
    """Count loc_id frequency in a simulation log (hotspot analysis).

    Args:
        log_path: Path to simulation log.
        map_path: Optional path to JSONL sidecar map file for resolution.
        top: Show top N locations (default: 20).
        output_format: "json" or "xout".
    """
    return loc_stats(log_path, map_path=map_path, top=top,
                     output_format=output_format)


@mcp.tool()
def xverif_loc_annotate(log_path: str, map_path: Optional[str] = None,
                         output_format: str = "xout") -> Any:
    """Insert source location hints into a simulation log.

    Args:
        log_path: Path to simulation log.
        map_path: Optional path to JSONL sidecar map file.
        output_format: "xout" (annotated text).
    """
    return loc_annotate(log_path, map_path=map_path,
                        output_format=output_format)


# ---------------------------------------------------------------------------
# Context tools (xberif — stateless CLI adapter)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_context_status(project_root: Optional[str] = None,
                           output_format: str = "json") -> Any:
    """Check xberif project status (which kinds, cards, details exist)."""
    return context_status(project_root=project_root, output_format=output_format)


@mcp.tool()
def xverif_context_list_topics(project_root: Optional[str] = None,
                                output_format: str = "json") -> Any:
    """List all known context topics."""
    return context_list_topics(project_root=project_root, output_format=output_format)


@mcp.tool()
def xverif_context_brief(mode: str = "debug", project_root: Optional[str] = None,
                          output_format: str = "xout") -> Any:
    """Generate a context summary brief for the given mode.

    Args:
        mode: Context mode (e.g. "debug").
        output_format: "json" or "xout".
    """
    return context_brief(mode=mode, project_root=project_root,
                         output_format=output_format)


@mcp.tool()
def xverif_context_get(topic: str, detail: bool = False,
                        project_root: Optional[str] = None,
                        output_format: str = "xout") -> Any:
    """Get a topic summary card, optionally with full detail.

    Args:
        topic: Topic name (e.g. "clk_rst", "memory_map").
        detail: If True, also include full detail content.
        output_format: "json" or "xout".
    """
    return context_get(topic, detail=detail, project_root=project_root,
                       output_format=output_format)


@mcp.tool()
def xverif_context_detail(topic: str, project_root: Optional[str] = None,
                           output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic.

    Args:
        topic: Topic name.
        output_format: "markdown" (raw detail text).
    """
    return context_detail(topic, project_root=project_root,
                          output_format=output_format)


@mcp.tool()
def xverif_context_validate(project_root: Optional[str] = None,
                             output_format: str = "json") -> Any:
    """Validate project cards and detail files for consistency."""
    return context_validate(project_root=project_root, output_format=output_format)


@mcp.tool()
def xverif_context_config_init(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif kind.toml config. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_config_init(kind, project_root=project_root)


@mcp.tool()
def xverif_context_init(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif project structure. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_init(model, project_root=project_root)


@mcp.tool()
def xverif_context_repair(project_root: Optional[str] = None) -> Any:
    """Repair xberif catalog index. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_repair(project_root=project_root)


# ---------------------------------------------------------------------------
# SVA tools (xsva — stateless CLI adapter)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_sva_list(file: str, output_format: str = "json") -> Any:
    """List all property/assertion names in a SVA source file.

    Args:
        file: Path to SVA source file (.sv/.sva/.v).
    """
    return sva_list(file, output_format=output_format)


@mcp.tool()
def xverif_sva_scan(file: str, output_format: str = "json") -> Any:
    """Scan syntax constructs used in a SVA source file.

    Args:
        file: Path to SVA source file.
    """
    return sva_scan(file, output_format=output_format)


@mcp.tool()
def xverif_sva_parse(file: str, property: str, emit: str = "timeline-ir",
                      output_format: str = "json") -> Any:
    """Parse a SVA property into IR.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        emit: IR level — "surface-ir", "sequence-ir", or "timeline-ir".
    """
    return sva_parse(file, property, emit=emit, output_format=output_format)


@mcp.tool()
def xverif_sva_explain(file: str, property: str, strict: bool = False,
                        output_format: str = "xout") -> Any:
    """Generate a human-readable explanation of a SVA property.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        strict: If True, error on unsupported constructs.
        output_format: "json", "markdown", or "xout".
    """
    return sva_explain(file, property, strict=strict, output_format=output_format)


@mcp.tool()
def xverif_sva_render(file: str, property: str, format: str = "mermaid",
                       output_format: str = "xout") -> Any:
    """Render a SVA property as mermaid or SVG.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        format: "mermaid" or "svg".
        output_format: "xout" (rendered text).
    """
    return sva_render(file, property, format=format, output_format=output_format)


# ---------------------------------------------------------------------------
# Tool catalog (meta-tools for AI discovery)
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    {"name": "xverif_ping", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Ping the xverif MCP server."},
    {"name": "xverif_tools", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "List all available xverif tools."},
    {"name": "xverif_tool_help", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Get help for a specific tool."},
    # debug
    {"name": "xverif_debug_actions", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return the xdebug action catalog."},
    {"name": "xverif_debug_schema", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return an action-specific xdebug JSON schema."},
    {"name": "xverif_debug_request", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Run a complete xdebug JSON request (one-shot, no session)."},
    {"name": "xverif_debug_session_open", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed xdebug session (direct or LSF)."},
    {"name": "xverif_debug_session_list", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": False,
     "description": "List xdebug sessions managed by this server."},
    {"name": "xverif_debug_session_use", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": False,
     "description": "Set the default xdebug session."},
    {"name": "xverif_debug_session_close", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup an xdebug session."},
    {"name": "xverif_debug_query", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Run an xdebug action through a loop session."},
    # wave aliases
    {"name": "xverif_wave_value_at", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Get signal value at a time (alias for value.at)."},
    {"name": "xverif_wave_signal_changes", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Get all value changes in a time window (alias for signal.changes)."},
    {"name": "xverif_wave_rc_generate", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Generate RC from config (alias for rc.generate)."},
    {"name": "xverif_design_trace_driver", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Trace the driver of a signal (alias for trace.driver)."},
    # bit
    {"name": "xverif_bit_conv", "category": "bit", "backend": "xbit",
     "stateful": False, "requires_session": False,
     "description": "Convert a value between radices and SV literal formats."},
    {"name": "xverif_bit_eval", "category": "bit", "backend": "xbit",
     "stateful": False, "requires_session": False,
     "description": "Evaluate a deterministic bit/expression calculation."},
    {"name": "xverif_bit_slice", "category": "bit", "backend": "xbit",
     "stateful": False, "requires_session": False,
     "description": "Extract a bit slice from a value."},
    {"name": "xverif_bit_check", "category": "bit", "backend": "xbit",
     "stateful": False, "requires_session": False,
     "description": "Check a bit expression against expected values."},
    # entry
    {"name": "xverif_entry_decode", "category": "entry", "backend": "xentry",
     "stateful": False, "requires_session": False,
     "description": "Decode multi-beat fragments into raw field slices."},
    {"name": "xverif_entry_explain", "category": "entry", "backend": "xentry",
     "stateful": False, "requires_session": False,
     "description": "Explain field layout defined by an entry config."},
    {"name": "xverif_entry_validate", "category": "entry", "backend": "xentry",
     "stateful": False, "requires_session": False,
     "description": "Validate an entry config and optionally its input."},
    # loc
    {"name": "xverif_loc_resolve", "category": "loc", "backend": "xloc",
     "stateful": False, "requires_session": False,
     "description": "Resolve a loc_id to source file:line."},
    {"name": "xverif_loc_context", "category": "loc", "backend": "xloc",
     "stateful": False, "requires_session": False,
     "description": "Resolve a loc_id and show surrounding source context."},
    {"name": "xverif_loc_stats", "category": "loc", "backend": "xloc",
     "stateful": False, "requires_session": False,
     "description": "Count loc_id frequency in a simulation log."},
    {"name": "xverif_loc_annotate", "category": "loc", "backend": "xloc",
     "stateful": False, "requires_session": False,
     "description": "Insert source location hints into a simulation log."},
    # context
    {"name": "xverif_context_status", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Check xberif project status."},
    {"name": "xverif_context_list_topics", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "List all known context topics."},
    {"name": "xverif_context_brief", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Generate a context summary brief."},
    {"name": "xverif_context_get", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Get a topic summary card, optionally with detail."},
    {"name": "xverif_context_detail", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Get the full detail markdown for a topic."},
    {"name": "xverif_context_validate", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Validate project cards and detail files."},
    {"name": "xverif_context_config_init", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize xberif kind.toml config (write)."},
    {"name": "xverif_context_init", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize xberif project structure (write)."},
    {"name": "xverif_context_repair", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Repair xberif catalog index (write)."},
    # sva
    {"name": "xverif_sva_list", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "List all property/assertion names in a SVA file."},
    {"name": "xverif_sva_scan", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Scan syntax constructs in a SVA file."},
    {"name": "xverif_sva_parse", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Parse a SVA property into IR."},
    {"name": "xverif_sva_explain", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Generate a human-readable SVA property explanation."},
    {"name": "xverif_sva_render", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Render a SVA property as mermaid or SVG."},
]


@mcp.tool()
def xverif_tools(category: Optional[str] = None,
                  include_write: bool = False) -> dict:
    """List all available xverif tools, optionally filtered by category.

    Args:
        category: Filter by category ("debug", "bit", "entry", "loc", "context", "sva").
        include_write: If True, include write-protected tools.
    """
    tools = TOOL_CATALOG
    if category:
        tools = [t for t in tools if t["category"] == category]
    if not include_write:
        tools = [t for t in tools if "write" not in t.get("description", "").lower() or "(write)" not in t.get("description", "")]
    return {"ok": True, "tools": tools}


@mcp.tool()
def xverif_tool_help(name: str) -> dict:
    """Get detailed help for a specific xverif tool.

    Args:
        name: Exact tool name (e.g. "xverif_debug_query").
    """
    for t in TOOL_CATALOG:
        if t["name"] == name:
            return {"ok": True, "tool": t}
    return _tool_error("TOOL_NOT_FOUND", f"tool not found: {name}")


# ---------------------------------------------------------------------------
# High-frequency debug aliases (shortcuts for xverif_debug_query)
# ---------------------------------------------------------------------------


@mcp.tool()
def xverif_wave_value_at(signal: str, time: str = "0ns",
                          session: Optional[str] = None,
                          output_format: str = "xout") -> Any:
    """Get a signal value at a specific time (alias for value.at).

    Args:
        signal: Full hierarchical signal path.
        time: Target time string (e.g. "100ns", "1us").
        session: Session alias (uses default if omitted).
        output_format: "xout", "json", or "envelope".
    """
    return debug.query(action="value.at", args={"signal": signal, "time": time},
                       session=session, output_format=output_format)


@mcp.tool()
def xverif_wave_signal_changes(signal: str, begin: str = "0ns",
                                end: str = "100ns",
                                session: Optional[str] = None,
                                output_format: str = "xout") -> Any:
    """Get all value changes for a signal in a time window.

    Args:
        signal: Full hierarchical signal path.
        begin: Start time (e.g. "0ns").
        end: End time (e.g. "100ns").
        session: Session alias.
        output_format: "xout", "json", or "envelope".
    """
    return debug.query(action="signal.changes",
                       args={"signal": signal, "begin": begin, "end": end},
                       session=session, output_format=output_format)


@mcp.tool()
def xverif_wave_rc_generate(config_path: str, rc_path: str,
                              session: Optional[str] = None,
                              output_format: str = "json") -> Any:
    """Generate recovery context from config (alias for rc.generate).

    Args:
        config_path: Path to RC config file.
        rc_path: Output path for generated RC.
        session: Session alias.
        output_format: "json" or "xout".
    """
    return debug.query(action="rc.generate",
                       args={"config_path": config_path, "rc_path": rc_path},
                       session=session, output_format=output_format)


@mcp.tool()
def xverif_design_trace_driver(signal: str, time: str = "0ns",
                                session: Optional[str] = None,
                                output_format: str = "xout") -> Any:
    """Trace the active driver of a signal at a specific time.

    Args:
        signal: Full hierarchical signal path.
        time: Target time string.
        session: Session alias.
        output_format: "xout", "json", or "envelope".
    """
    return debug.query(action="trace.driver",
                       args={"signal": signal, "time": time},
                       session=session, output_format=output_format)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
