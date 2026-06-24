"""Stateless xbit adapter — deterministic bit/expression calculator."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()

from xbit import cli
from xbit.format import failure, human_result


def _state(state: str) -> str:
    if state in {"2", "2state"}:
        return "2state"
    if state in {"4", "4state"}:
        return "4state"
    raise ValueError("state must be 2 or 4")


def _format(payload: dict, output_format: str) -> Any:
    if output_format == "json":
        return payload
    return human_result(payload)


def _call(op: str, output_format: str, **kwargs: Any) -> Any:
    args = SimpleNamespace(command=op, **kwargs)
    try:
        payload = {
            "conv": cli.cmd_conv,
            "eval": cli.cmd_eval,
            "slice": cli.cmd_slice,
            "check": cli.cmd_check,
        }[op](args)
    except Exception as exc:
        payload = failure(exc)
    return _format(payload, output_format)


def bit_conv(value: str, width: int = 0, signed: bool = False,
             unsigned: bool = False, state: str = "2",
             output_format: str = "json") -> Any:
    """Convert a value between radices and SV literal formats."""
    sign = True if signed else False if unsigned else None
    return _call("conv", output_format, value=value, state=_state(state),
                 width=width or None, signed=sign)


def bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
             signed: bool = False, unsigned: bool = False,
             state: str = "2", output_format: str = "json") -> Any:
    """Evaluate a deterministic bit/expression calculation."""
    sign = True if signed else False if unsigned else None
    var_items = [f"{k}={v}" for k, v in (vars or {}).items()]
    return _call("eval", output_format, expr=expr, var=var_items,
                 state=_state(state), width=width or None, signed=sign)


def bit_slice(value: str, msb: int, lsb: int, state: str = "2",
              output_format: str = "json") -> Any:
    """Extract a bit slice from a value."""
    return _call("slice", output_format, value=value, msb=msb, lsb=lsb,
                 state=_state(state))


def bit_check(expr: str, vars: Optional[dict] = None,
              values: Optional[str] = None, state: str = "2",
              output_format: str = "json") -> Any:
    """Check a bit expression against expected values."""
    var_items = [f"{k}={v}" for k, v in (vars or {}).items()]
    return _call("check", output_format, expr=expr, var=var_items,
                 values=values, state=_state(state))
