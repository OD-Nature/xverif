"""xverif-mcp — unified MCP server for all xverif tools."""

import inspect
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.adapters.xcov import XverifCoverageAdapter
from xverif_mcp.adapters.xbit import bit_conv, bit_eval, bit_slice, bit_check
from xverif_mcp.adapters.xentry import entry_decode, entry_explain, entry_validate
from xverif_mcp.adapters.xloc import loc_resolve, loc_context, loc_stats, loc_annotate
from xverif_mcp.adapters.xsva import sva_list, sva_scan, sva_parse, sva_explain
from xverif_mcp.errors import error_payload
from xverif_mcp.tool_policy import filtered_catalog, policy_summary, tool_enabled
from xverif_mcp.xdebug_errors import (
    forbidden_native_session_error,
    is_forbidden_native_session_action,
)

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

INSTRUCTIONS = """xverif exposes deterministic chip-verification tools.
xdebug and xcov are stateful; xbit, xentry, xloc and xsva are stateless.
Discover tools with xverif_tools and action contracts with the corresponding
catalog/schema tools. Stateful work uses session_open -> query -> session_close;
debug and coverage queries both use session_id/action/args/limits/output_format.
Use xverif_batch only for strict serial execution and keep action parameters
inside the query tool's inner args. No automatic retry, reopen, backend,
transport or data-source fallback is performed. Detailed workflows belong to
the xverif and xverif-admin skills."""


def _cleanup_stateful_sessions() -> None:
    for adapter in (debug, cov):
        try:
            adapter.close_all()
        except Exception:
            pass


@asynccontextmanager
async def _mcp_lifespan(app):
    try:
        yield {}
    finally:
        _cleanup_stateful_sessions()


mcp = FastMCP(
    name="xverif",
    instructions=INSTRUCTIONS,
    lifespan=_mcp_lifespan,
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
    ``{"tool":"xverif_debug_query","args":{"session_id":"s0","action":"value.at","args":{"signal":"top.clk","time":"10ns","clock":"top.clk"}}}``

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
def xverif_debug_list_actions(verbose: bool = False) -> dict:
    """Return the xdebug action catalog.

    Call this before xverif_debug_query when you are unsure which action to use.
    Default returns compact action names. Set verbose=true for descriptors,
    schemas, examples, required args, and usage guidance.
    """
    return debug.actions(verbose=verbose)


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
def xverif_debug_session_open(
    name: str,
    daidir: Optional[str] = None,
    fsdb: Optional[str] = None,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
) -> dict:
    """Open a loop-backed xdebug session."""
    return debug.session_open(
        name=name, daidir=daidir, fsdb=fsdb, queue=queue,
        resource=resource,
    )


@xverif_tool("debug")
def xverif_debug_session_list(
    include_tombstones: bool = False,
    verbose: bool = False,
) -> dict:
    """List xdebug sessions managed by this server."""
    return debug.session_list(include_tombstones=include_tombstones, verbose=verbose)


@xverif_tool("debug")
def xverif_debug_session_doctor(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """Read-only health diagnosis for one managed xdebug session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_doctor(key, verbose=verbose)


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
def xverif_debug_session_kill(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Force cleanup of exactly one managed xdebug session."""
    key = session_id or name
    if not key or key == "all":
        return _tool_error("INVALID_ARGUMENT", "provide one exact name or session_id; all is not supported")
    return debug.session_kill(key)


@xverif_tool("debug")
def xverif_debug_session_gc(verbose: bool = False) -> dict:
    """Remove confirmed terminal xdebug tombstones; report unresolved sessions."""
    return debug.session_gc(verbose=verbose)


@xverif_tool("debug")
def xverif_debug_query(
    session_id: str,
    action: str,
    args: Optional[dict] = None,
    limits: Optional[dict] = None,
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
        session_id: Explicit session alias or session_id returned by session_open.
        args: Action-specific arguments dict.
        limits: Query limits dict (max_rows, timeout, etc.).
        output_format:
            "xout" (default) — AI-readable structured text.
            "json" — raw xdebug JSON dict.
            "envelope" — wrapper envelope for debugging.
    """
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'xout', 'json', or 'envelope'")
    if is_forbidden_native_session_action(action):
        return forbidden_native_session_error(action)
    return debug.query(
        action=action,
        args=args or {},
        session=session_id,
        limits=limits,
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
def xverif_cov_session_open(
    name: str,
    vdb: str,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
) -> dict:
    """Open a loop-backed xcov coverage database session."""
    return cov.session_open(
        name=name, vdb=vdb, queue=queue, resource=resource,
    )


@xverif_tool("cov")
def xverif_cov_session_list(
    include_tombstones: bool = False,
    verbose: bool = False,
) -> dict:
    """List xcov sessions managed by this server."""
    return cov.session_list(include_tombstones=include_tombstones, verbose=verbose)


@xverif_tool("cov")
def xverif_cov_session_doctor(
    session_id: str,
    verbose: bool = False,
) -> dict:
    """Read-only health diagnosis for one managed xcov session."""
    return cov.session_doctor(session_id, verbose=verbose)


@xverif_tool("cov")
def xverif_cov_session_close(
    session_id: str,
) -> dict:
    """Close and cleanup an xcov session."""
    return cov.session_close(session_id)


@xverif_tool("cov")
def xverif_cov_session_kill(
    session_id: str,
) -> dict:
    """Terminate exactly one managed xcov loop session."""
    if session_id == "all":
        return _tool_error("INVALID_ARGUMENT", "provide one exact session_id; all is not supported")
    return cov.session_kill(session_id)


@xverif_tool("cov")
def xverif_cov_session_gc(verbose: bool = False) -> dict:
    """Remove confirmed terminal xcov tombstones; report unresolved sessions."""
    return cov.session_gc(verbose=verbose)


@xverif_tool("cov")
def xverif_cov_query(
    session_id: str,
    action: str,
    args: Optional[dict] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "xout",
) -> Any:
    """Run an xcov action through a coverage session."""
    if output_format not in ("xout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'xout', 'json', or 'envelope'")
    if is_forbidden_native_session_action(action):
        return forbidden_native_session_error(action, backend="cov")
    return cov.query(
        action=action,
        args=args or {},
        session=session_id,
        limits=limits,
        output=output,
        output_format=output_format,
    )


# ---------------------------------------------------------------------------
# Bit tools (xbit - stateless in-process adapter)
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
# Entry tools (xentry - stateless in-process adapter)
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
# Location tools (xloc - stateless in-process adapter)
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
# SVA tools (xsva - stateless in-process adapter)
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
                    "{\"session_id\":\"case_a\",\"action\":\"value.at\","
                    "\"args\":{\"signal\":\"top.clk\",\"time\":\"10ns\",\"clock\":\"top.clk\"}}}"},
    # debug
    {"name": "xverif_debug_list_actions", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return the xdebug action catalog."},
    {"name": "xverif_debug_get_schema", "category": "debug", "backend": "xdebug",
     "stateful": False, "requires_session": False,
     "description": "Return an action-specific xdebug JSON schema."},
    {"name": "xverif_debug_session_open", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed xdebug session (direct or LSF)."},
    {"name": "xverif_debug_session_list", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": False,
     "description": "List xdebug sessions managed by this server."},
    {"name": "xverif_debug_session_doctor", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Read-only diagnosis for one managed xdebug session."},
    {"name": "xverif_debug_session_close", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup an xdebug session."},
    {"name": "xverif_debug_session_kill", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": True,
     "description": "Force cleanup of exactly one managed xdebug session."},
    {"name": "xverif_debug_session_gc", "category": "debug", "backend": "xdebug",
     "stateful": True, "requires_session": False,
     "description": "Remove confirmed terminal xdebug tombstones."},
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
    {"name": "xverif_cov_session_open", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed xcov coverage database session."},
    {"name": "xverif_cov_session_list", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": False,
     "description": "List xcov sessions managed by this server."},
    {"name": "xverif_cov_session_doctor", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Read-only diagnosis for one managed xcov session."},
    {"name": "xverif_cov_session_close", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup an xcov session."},
    {"name": "xverif_cov_session_kill", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Terminate exactly one managed xcov loop session."},
    {"name": "xverif_cov_session_gc", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": False,
     "description": "Remove confirmed terminal xcov tombstones."},
    {"name": "xverif_cov_query", "category": "cov", "backend": "xcov",
     "stateful": True, "requires_session": True,
     "description": "Run an xcov action through a coverage session."},
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

for _tool in TOOL_CATALOG:
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        _cleanup_stateful_sessions()
