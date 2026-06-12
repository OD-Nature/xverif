"""xverif-mcp — unified MCP server for all xverif tools."""

import inspect
import json
import time
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.adapters.xcov import XverifCoverageAdapter
from xverif_mcp.adapters.xbit import bit_conv, bit_eval, bit_slice, bit_check
from xverif_mcp.adapters.xentry import entry_decode, entry_explain, entry_validate
from xverif_mcp.adapters.xloc import loc_resolve, loc_context, loc_stats, loc_annotate
from xverif_mcp.adapters.xberif import (context_status, context_list_topics, context_brief,
                                         context_get, context_detail, context_validate,
                                         context_config_init, context_init, context_repair)
from xverif_mcp.adapters.xsva import sva_list, sva_scan, sva_parse, sva_explain
from xverif_mcp.errors import error_payload
from xverif_mcp.tool_policy import filtered_catalog, policy_summary, tool_enabled

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
xverif-mcp — https://github.com/BLANK2077/xverif

Exposes deterministic local tools for chip verification debug agents.
The xdebug and xcov backends are stateful and may run locally or through LSF.
Other tools (xbit, xentry, xloc, xberif, xsva) are stateless CLI adapters.

Typical workflow:
1. Call xverif_tools to discover available tools.
2. For debug queries: xverif_debug_session_open → xverif_debug_query.
3. For coverage queries: xverif_cov_session_open → xverif_cov_query.
4. For stateless queries: call the tool directly (e.g., xverif_bit_eval).

If xverif_debug_query returns error.code=SESSION_LOST:
  - check error.terminal_source: "transport" means subprocess/LSF crash or timeout
  - if timeout: inform user of possible causes (large data, LSF queue delay)
    and let user decide — narrow query scope or increase timeout env vars
  - the MCP server has already cleaned up the subprocess/LSF job
  - the session mapping has been evicted
  - the agent must explicitly call xverif_debug_session_open before retrying
No automatic retry or reopen is performed by the server.

Batch execution (xverif_batch):
  Use xverif_batch when you need to run multiple tools in strict serial order,
  especially for stateful workflows like session.open → query → session.close.
  This avoids race conditions where a query might execute before the session is
  ready.

  IMPORTANT — nested args: tools like xverif_debug_query and xverif_cov_query
  have their own "args" parameter.  In a batch line, the outer "args" maps to
  the tool's MCP parameters, and the inner "args" maps to the action's arguments:
    {"tool":"xverif_debug_query","args":{"action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}

  Step 1 — write the batch file (bash inline):
    cat > /tmp/batch.ndjson << 'EOF'
    {"tool": "xverif_cov_session_open", "args": {"name": "s0", "vdb": "/path/to/merged.vdb"}}
    {"tool": "xverif_cov_query", "args": {"session": "s0", "action": "cov.holes", "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}}
    {"tool": "xverif_cov_session_close", "args": {"name": "s0"}}
    EOF

  Or Python inline:
    import json
    reqs = [
        {"tool": "xverif_cov_session_open", "args": {"name": "s0", "vdb": "/path/to/merged.vdb"}},
        {"tool": "xverif_cov_query", "args": {"session": "s0", "action": "cov.holes", "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}},
        {"tool": "xverif_cov_session_close", "args": {"name": "s0"}},
    ]
    with open("/tmp/batch.ndjson", "w") as f:
        for r in reqs: f.write(json.dumps(r) + "\\n")

  Step 2 — call xverif_batch(batch_file="/tmp/batch.ndjson", output_file="/tmp/batch_results.ndjson").
  Returns {total, ok_count, failed_count, output_file}.

  Step 3 — read results (Python inline):
    import json
    with open("/tmp/batch_results.ndjson") as f:
        for line in f:
            r = json.loads(line)
            # r["tool"], r["ok"], r["elapsed_ms"], r["error"]
  Format errors (invalid JSON, missing tool field) appear as tool=null with ok=false.

Output format: all tools default to output_format="xout" (compact AI-readable
structured text, saves tokens vs JSON). Use output_format="json" only when you
need structured data for programmatic analysis.
"""

mcp = FastMCP(
    name="xverif",
    instructions=INSTRUCTIONS,
)

debug = XverifDebugAdapter()
cov = XverifCoverageAdapter()


def _tool_error(code: str, message: str) -> dict:
    return error_payload(code, message)


def _write_output(result: Any, path: str, append: bool) -> None:
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        if isinstance(result, str):
            f.write(result)
        else:
            f.write(str(result))


def _wrap_with_output(fn):
    """Wrap a tool function so it accepts ``xverif_output_path`` and
    ``xverif_output_append`` keyword arguments.  When *output_path* is
    given the raw return value is also written to that file."""
    sig = inspect.signature(fn)
    new_params = list(sig.parameters.values()) + [
        inspect.Parameter("xverif_output_path", inspect.Parameter.KEYWORD_ONLY,
                          default=None),
        inspect.Parameter("xverif_output_append", inspect.Parameter.KEYWORD_ONLY,
                          default=False),
    ]
    new_sig = sig.replace(parameters=new_params)

    if inspect.iscoroutinefunction(fn):
        async def wrapper(*args, **kwargs):
            output_path = kwargs.pop("xverif_output_path", None)
            output_append = kwargs.pop("xverif_output_append", False)
            result = await fn(*args, **kwargs)
            if output_path:
                try:
                    _write_output(result, output_path, output_append)
                except Exception:
                    pass
            return result
    else:
        def wrapper(*args, **kwargs):
            output_path = kwargs.pop("xverif_output_path", None)
            output_append = kwargs.pop("xverif_output_append", False)
            result = fn(*args, **kwargs)
            if output_path:
                try:
                    _write_output(result, output_path, output_append)
                except Exception:
                    pass
            return result

    wrapper.__signature__ = new_sig
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__annotations__ = {}
    return wrapper


def xverif_tool(group: str, write: bool = False):
    """Conditionally register a FastMCP tool according to env policy."""
    def decorator(fn):
        fn = _wrap_with_output(fn)
        if tool_enabled(group, write=write):
            return mcp.tool()(fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


@xverif_tool("common")
def xverif_ping() -> str:
    """Ping the xverif MCP server. Use this to check whether the server is alive."""
    return debug.ping()


def _append_result(output_file: str, tool: str | None, ok: bool,
                   error: str | None, elapsed_ms: int,
                   response: str | None = None) -> None:
    entry: dict = {
        "tool": tool,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }
    if response is not None:
        entry["response"] = response
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


async def _execute_one(name: str, args: dict) -> tuple[bool, str | None, int, str | None]:
    t0 = time.monotonic()
    try:
        result = await mcp.call_tool(name, args)
        content = result[0] if isinstance(result, tuple) else result
        text = content[0].text if content else ""
        try:
            j = json.loads(text)
            return j.get("ok", False), None, int((time.monotonic() - t0) * 1000), text
        except (json.JSONDecodeError, AttributeError):
            ok = ("pong" in str(text).lower()
                  or "XOUT_BEGIN" in text
                  or (text.startswith("@") and ".error." not in text))
            return ok, None, int((time.monotonic() - t0) * 1000), text
    except Exception as e:
        return False, str(e), int((time.monotonic() - t0) * 1000), None


@xverif_tool("common")
async def xverif_batch(batch_file: str, output_file: str) -> dict:
    """Execute multiple MCP tool requests from an NDJSON batch file serially.

    Each line is a JSON object with ``tool`` (tool name) and ``args``
    (arguments dict passed to that tool).  Results are written to
    ``output_file`` as NDJSON, one line per request (including parse errors).

    For tools that have their own nested ``args`` parameter (e.g.
    xverif_debug_query, xverif_cov_query), the inner args must be nested:
    ``{"tool":"xverif_debug_query","args":{"action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}``

    Returns ``{total, ok_count, failed_count, output_file}``.
    """
    stats = {"total": 0, "ok": 0, "failed": 0}

    try:
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    req = json.loads(line)
                except json.JSONDecodeError as e:
                    _append_result(output_file, None, False,
                                   f"INVALID_JSON: {e}", 0)
                    stats["failed"] += 1
                    stats["total"] += 1
                    continue

                tool_name = req.get("tool")
                if not tool_name:
                    _append_result(output_file, None, False,
                                   "MISSING_TOOL_FIELD", 0)
                    stats["failed"] += 1
                    stats["total"] += 1
                    continue

                tool_args = req.get("args", {})
                if not isinstance(tool_args, dict):
                    tool_args = {}

                ok, error, elapsed_ms, response = await _execute_one(tool_name, tool_args)
                _append_result(output_file, tool_name, ok, error, elapsed_ms, response)
                if ok:
                    stats["ok"] += 1
                else:
                    stats["failed"] += 1
                stats["total"] += 1
    except FileNotFoundError:
        return _tool_error("FILE_NOT_FOUND",
                           f"batch file not found: {batch_file}")
    except Exception as e:
        return _tool_error("BATCH_FAILED", str(e))

    return {
        "ok": True,
        "total": stats["total"],
        "ok_count": stats["ok"],
        "failed_count": stats["failed"],
        "output_file": output_file,
    }


# ---------------------------------------------------------------------------
# Debug tools (xdebug)
# ---------------------------------------------------------------------------


@xverif_tool("debug")
def xverif_debug_list_actions() -> dict:
    """Return the xdebug action catalog.

    Call this before xverif_debug_query when you are unsure which action to use.
    Returns the list of all available xdebug actions with brief descriptions.
    """
    return debug.actions()


@xverif_tool("debug")
def xverif_debug_get_schema(action: str, kind: str = "request") -> dict:
    """Return an action-specific xdebug JSON schema.

    Args:
        action: The xdebug action name (e.g. "value.at", "trace.drivers").
        kind: "request" for input schema, "response" for output schema.
    """
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return debug.schema(action, kind)


@xverif_tool("debug")
def xverif_debug_raw_request(request: dict, output_format: str = "xout") -> dict:
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


@xverif_tool("debug")
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
    """Open a loop-backed xdebug session."""
    return debug.session_open(
        name=name, daidir=daidir, fsdb=fsdb, queue=queue,
        resource=resource, reuse=reuse, reopen=reopen,
        make_default=make_default,
    )


@xverif_tool("debug")
def xverif_debug_session_list(include_native: bool = False) -> dict:
    """List xdebug sessions managed by this server."""
    return debug.session_list(include_native=include_native)


@xverif_tool("debug")
def xverif_debug_session_use(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Set the default xdebug session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_use(key)


@xverif_tool("debug")
def xverif_debug_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close and cleanup an xdebug session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_close(key)


@xverif_tool("debug")
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
    1. Call xverif_debug_list_actions if you don't know available actions.
    2. Call xverif_debug_get_schema(action) if you need the exact request shape.
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
# Coverage tools (xcov — stateful backend)
# ---------------------------------------------------------------------------


@xverif_tool("cov")
def xverif_cov_list_actions() -> dict:
    """Return the xcov action catalog."""
    return cov.actions()


@xverif_tool("cov")
def xverif_cov_get_schema(action: str, kind: str = "request") -> dict:
    """Return an xcov action schema."""
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return cov.schema(action, kind)


@xverif_tool("cov")
def xverif_cov_raw_request(request: dict, output_format: str = "xout") -> Any:
    """Run a complete xcov JSON request one-shot."""
    if not isinstance(request, dict):
        return _tool_error("INVALID_ARGUMENT", "request must be a JSON object")
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'xout', 'json', or 'envelope'")
    return cov.request(request, output_format)


@xverif_tool("cov")
def xverif_cov_session_open(
    name: str,
    vdb: str,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
    reuse: bool = True,
    reopen: bool = False,
    make_default: bool = True,
) -> dict:
    """Open a loop-backed xcov coverage database session."""
    return cov.session_open(
        name=name, vdb=vdb, queue=queue, resource=resource,
        reuse=reuse, reopen=reopen, make_default=make_default,
    )


@xverif_tool("cov")
def xverif_cov_session_list() -> dict:
    """List xcov sessions managed by this server."""
    return cov.session_list()


@xverif_tool("cov")
def xverif_cov_session_use(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Set the default xcov session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return cov.session_use(key)


@xverif_tool("cov")
def xverif_cov_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close and cleanup an xcov session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return cov.session_close(key)


@xverif_tool("cov")
def xverif_cov_query(
    action: str,
    args: Optional[dict] = None,
    target: Optional[dict] = None,
    session: Optional[str] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "xout",
) -> Any:
    """Run an xcov action through a coverage session."""
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'xout', 'json', or 'envelope'")
    return cov.query(
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


@xverif_tool("bit")
def xverif_bit_convert(value: str, width: int = 0, signed: bool = False,
                     unsigned: bool = False, state: str = "2",
                     output_format: str = "xout") -> Any:
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


@xverif_tool("bit")
def xverif_bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
                     signed: bool = False, unsigned: bool = False,
                     state: str = "2", output_format: str = "xout") -> Any:
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


@xverif_tool("bit")
def xverif_bit_slice(value: str, msb: int, lsb: int, state: str = "2",
                      output_format: str = "xout") -> Any:
    """Extract a bit slice from a value.

    Args:
        value: The source value.
        msb: Most significant bit index.
        lsb: Least significant bit index.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "xout".
    """
    return bit_slice(value, msb, lsb, state=state, output_format=output_format)


@xverif_tool("bit")
def xverif_bit_check(expr: str, vars: Optional[dict] = None,
                      values: Optional[str] = None, state: str = "2",
                      output_format: str = "xout") -> Any:
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


@xverif_tool("entry")
def xverif_entry_decode(config_path: Optional[str] = None,
                         input_path: Optional[str] = None,
                         config: Optional[dict] = None,
                         fragments: Optional[list] = None,
                         output_format: str = "xout") -> Any:
    """Decode multi-beat byte fragments into raw field slices per config.

    Provide either (config_path + input_path) or (config + fragments).

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Path to JSONL fragments input file.
        config: Inline entry config dict (alternative to config_path).
        fragments: Inline fragments list (alternative to input_path).
        output_format: "json" or "xout".
    """
    if not config_path and not config:
        return _tool_error("INVALID_ARGUMENT",
                           "provide config_path or config")
    return entry_decode(config_path=config_path or "",
                         input_path=input_path or "",
                         config=config, fragments=fragments,
                         output_format=output_format)


@xverif_tool("entry")
def xverif_entry_explain(config_path: str, output_format: str = "xout") -> Any:
    """Explain the field layout defined by an entry config.

    Args:
        config_path: Path to YAML/JSON entry config file.
        output_format: "json" or "xout".
    """
    return entry_explain(config_path, output_format=output_format)


@xverif_tool("entry")
def xverif_entry_validate(config_path: Optional[str] = None,
                           input_path: Optional[str] = None,
                           config: Optional[dict] = None,
                           fragments: Optional[list] = None,
                           output_format: str = "xout") -> Any:
    """Validate an entry config (and optionally an input) without decoding.

    Provide either (config_path + input_path) or (config + fragments).

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Optional path to JSONL fragments for deeper validation.
        config: Inline entry config dict (alternative to config_path).
        fragments: Inline fragments list (alternative to input_path).
        output_format: "json" or "xout".
    """
    if not config_path and not config:
        return _tool_error("INVALID_ARGUMENT",
                           "provide config_path or config")
    return entry_validate(config_path=config_path or "",
                           input_path=input_path,
                           config=config, fragments=fragments,
                           output_format=output_format)


# ---------------------------------------------------------------------------
# Location tools (xloc — stateless CLI adapter)
# ---------------------------------------------------------------------------


@xverif_tool("loc")
def xverif_loc_resolve(loc_id: str, map_path: str,
                        output_format: str = "xout") -> Any:
    """Resolve a compressed loc_id (L_XXXXXXXX) to source file:line.

    Args:
        loc_id: The loc_id to resolve (e.g. L_00000001).
        map_path: Path to JSONL sidecar map file.
        output_format: "json" or "xout".
    """
    return loc_resolve(loc_id, map_path, output_format=output_format)


@xverif_tool("loc")
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


@xverif_tool("loc")
def xverif_loc_stats(log_path: str, map_path: Optional[str] = None,
                      top: int = 20, output_format: str = "xout") -> Any:
    """Count loc_id frequency in a simulation log (hotspot analysis).

    Args:
        log_path: Path to simulation log.
        map_path: Optional path to JSONL sidecar map file for resolution.
        top: Show top N locations (default: 20).
        output_format: "json" or "xout".
    """
    return loc_stats(log_path, map_path=map_path, top=top,
                     output_format=output_format)


@xverif_tool("loc")
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


@xverif_tool("context")
def xverif_context_status(project_root: Optional[str] = None,
                           output_format: str = "xout") -> Any:
    """Check xberif project status (which kinds, cards, details exist)."""
    return context_status(project_root=project_root, output_format=output_format)


@xverif_tool("context")
def xverif_context_topics(project_root: Optional[str] = None,
                                output_format: str = "xout") -> Any:
    """List all known context topics."""
    return context_list_topics(project_root=project_root, output_format=output_format)


@xverif_tool("context")
def xverif_context_brief(mode: str = "debug", project_root: Optional[str] = None,
                          output_format: str = "xout") -> Any:
    """Generate a context summary brief for the given mode.

    Args:
        mode: Context mode (e.g. "debug").
        output_format: "json" or "xout".
    """
    return context_brief(mode=mode, project_root=project_root,
                         output_format=output_format)


@xverif_tool("context")
def xverif_context_topic(topic: str, detail: bool = False,
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


@xverif_tool("context")
def xverif_context_topic_detail(topic: str, project_root: Optional[str] = None,
                           output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic.

    Args:
        topic: Topic name.
        output_format: "markdown" (raw detail text).
    """
    return context_detail(topic, project_root=project_root,
                          output_format=output_format)


@xverif_tool("context")
def xverif_context_validate(project_root: Optional[str] = None,
                             output_format: str = "xout") -> Any:
    """Validate project cards and detail files for consistency."""
    return context_validate(project_root=project_root, output_format=output_format)


@xverif_tool("context_write", write=True)
def xverif_context_init_config(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif kind.toml config. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_config_init(kind, project_root=project_root)


@xverif_tool("context_write", write=True)
def xverif_context_init_project(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif project structure. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_init(model, project_root=project_root)


@xverif_tool("context_write", write=True)
def xverif_context_repair_index(project_root: Optional[str] = None) -> Any:
    """Repair xberif catalog index. Requires XVERIF_MCP_ENABLE_WRITE=1."""
    return context_repair(project_root=project_root)


# ---------------------------------------------------------------------------
# SVA tools (xsva — stateless CLI adapter)
# ---------------------------------------------------------------------------


@xverif_tool("sva")
def xverif_sva_list_properties(file: str, output_format: str = "xout") -> Any:
    """List all property/assertion names in a SVA source file.

    Args:
        file: Path to SVA source file (.sv/.sva/.v).
    """
    return sva_list(file, output_format=output_format)


@xverif_tool("sva")
def xverif_sva_scan_constructs(file: str, output_format: str = "xout") -> Any:
    """Scan syntax constructs used in a SVA source file.

    Args:
        file: Path to SVA source file.
    """
    return sva_scan(file, output_format=output_format)


@xverif_tool("sva")
def xverif_sva_parse_property(file: str, property: str, emit: str = "timeline-ir",
                      output_format: str = "xout") -> Any:
    """Parse a SVA property into IR.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        emit: IR level — "surface-ir", "sequence-ir", or "timeline-ir".
    """
    return sva_parse(file, property, emit=emit, output_format=output_format)


@xverif_tool("sva")
def xverif_sva_explain_property(file: str, property: str, strict: bool = False,
                        output_format: str = "xout") -> Any:
    """Generate a human-readable explanation of a SVA property.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        strict: If True, error on unsupported constructs.
        output_format: "json", "markdown", or "xout".
    """
    return sva_explain(file, property, strict=strict, output_format=output_format)


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
    {"name": "xverif_batch", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Execute MCP tools from NDJSON batch file serially. "
                    "Line: {\"tool\":\"<name>\",\"args\":{<params>}}. "
                    "Nested args for debug_query/cov_query: "
                    "{\"tool\":\"xverif_debug_query\",\"args\":"
                    "{\"action\":\"value.at\",\"args\":{\"signal\":\"top.clk\",\"time\":\"10ns\"}}}"},
    # debug
    {"name": "xverif_debug_list_actions", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return the xdebug action catalog."},
    {"name": "xverif_debug_get_schema", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return an action-specific xdebug JSON schema."},
    {"name": "xverif_debug_raw_request", "category": "debug", "backend": "xdebug",
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
    # coverage
    {"name": "xverif_cov_list_actions", "category": "cov", "backend": "xcov",
     "stateful": False, "requires_session": False,
     "description": "Return the xcov action catalog."},
    {"name": "xverif_cov_get_schema", "category": "cov", "backend": "xcov",
     "stateful": False, "requires_session": False,
     "description": "Return an xcov action schema."},
    {"name": "xverif_cov_raw_request", "category": "cov", "backend": "xcov",
     "stateful": False, "requires_session": False,
     "description": "Run a complete xcov JSON request one-shot."},
    {"name": "xverif_cov_session_open", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed xcov coverage database session."},
    {"name": "xverif_cov_session_list", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": False,
     "description": "List xcov sessions managed by this server."},
    {"name": "xverif_cov_session_use", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": False,
     "description": "Set the default xcov session."},
    {"name": "xverif_cov_session_close", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup an xcov session."},
    {"name": "xverif_cov_query", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Run an xcov action through a coverage session."},
    # wave aliases
    {"name": "xverif_wave_value_at", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Get signal value at a time (alias for value.at)."},
    {"name": "xverif_wave_changes", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Get all value changes in a time window (alias for signal.changes)."},
    {"name": "xverif_wave_generate_rc", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Generate RC from config (alias for rc.generate)."},
    {"name": "xverif_design_trace_driver", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Trace the driver of a signal (alias for trace.driver)."},
    # bit
    {"name": "xverif_bit_convert", "category": "bit", "backend": "xbit",
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
    {"name": "xverif_context_topics", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "List all known context topics."},
    {"name": "xverif_context_brief", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Generate a context summary brief."},
    {"name": "xverif_context_topic", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Get a topic summary card, optionally with detail."},
    {"name": "xverif_context_topic_detail", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Get the full detail markdown for a topic."},
    {"name": "xverif_context_validate", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Validate project cards and detail files."},
    {"name": "xverif_context_init_config", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize xberif kind.toml config (write)."},
    {"name": "xverif_context_init_project", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize xberif project structure (write)."},
    {"name": "xverif_context_repair_index", "category": "context", "backend": "xberif",
     "stateful": False, "requires_session": False,
     "description": "Repair xberif catalog index (write)."},
    # sva
    {"name": "xverif_sva_list_properties", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "List all property/assertion names in a SVA file."},
    {"name": "xverif_sva_scan_constructs", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Scan syntax constructs in a SVA file."},
    {"name": "xverif_sva_parse_property", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Parse a SVA property into IR."},
    {"name": "xverif_sva_explain_property", "category": "sva", "backend": "xsva",
     "stateful": False, "requires_session": False,
     "description": "Generate a human-readable SVA property explanation."},
]

_WRITE_TOOL_NAMES = {
    "xverif_context_init_config",
    "xverif_context_init_project",
    "xverif_context_repair_index",
}

for _tool in TOOL_CATALOG:
    if _tool["name"] in _WRITE_TOOL_NAMES:
        _tool.setdefault("group", "context_write")
        _tool.setdefault("write", True)
    else:
        _tool.setdefault("group", _tool["category"])
        _tool.setdefault("write", False)


@xverif_tool("common")
def xverif_tools(category: Optional[str] = None,
                  include_write: bool = True) -> dict:
    """List all available xverif tools, optionally filtered by category.

    Args:
        category: Filter by category ("debug", "bit", "entry", "loc", "context", "sva").
        include_write: If False, hide write-protected tools from this catalog view.
    """
    return {
        "ok": True,
        "tools": filtered_catalog(TOOL_CATALOG, category=category, include_write=include_write),
        "policy": policy_summary(),
    }


@xverif_tool("common")
def xverif_tool_help(name: str) -> dict:
    """Get detailed help for a specific xverif tool.

    Args:
        name: Exact tool name (e.g. "xverif_debug_query").
    """
    for t in filtered_catalog(TOOL_CATALOG, include_write=True):
        if t["name"] == name:
            return {"ok": True, "tool": t, "policy": policy_summary()}
    for t in TOOL_CATALOG:
        if t["name"] == name:
            return _tool_error("TOOL_NOT_ENABLED", f"tool is disabled by MCP policy: {name}")
    return _tool_error("TOOL_NOT_FOUND", f"tool not found: {name}")


# ---------------------------------------------------------------------------
# High-frequency debug aliases (shortcuts for xverif_debug_query)
# ---------------------------------------------------------------------------


@xverif_tool("debug")
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


@xverif_tool("debug")
def xverif_wave_changes(signal: str, begin: str = "0ns",
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


@xverif_tool("debug")
def xverif_wave_generate_rc(config_path: str, rc_path: str,
                              session: Optional[str] = None,
                              output_format: str = "xout") -> Any:
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


@xverif_tool("debug")
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
