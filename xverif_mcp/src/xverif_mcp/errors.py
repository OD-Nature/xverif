"""Unified MCP error payload builders."""
from __future__ import annotations

from typing import Any, Dict

Json = Dict[str, Any]


def error_payload(code: str, message: str, **extra: Any) -> Json:
    payload: Json = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return payload


def cli_failed(tool: str, exit_code: int, stdout_tail: str = "",
               stderr_tail: str = "") -> Json:
    return error_payload("XVERIF_CLI_FAILED", f"{tool} exit {exit_code}",
                         tool=tool, exit_code=exit_code,
                         stdout_tail=stdout_tail[-4096:],
                         stderr_tail=stderr_tail[-4096:])


def bad_json(tool: str, stdout_tail: str = "", stderr_tail: str = "") -> Json:
    return error_payload("XVERIF_BAD_JSON_RESPONSE",
                         f"{tool} did not return a JSON object",
                         tool=tool,
                         stdout_tail=stdout_tail[-4096:],
                         stderr_tail=stderr_tail[-4096:])


def tool_timeout(tool: str, timeout_sec: float) -> Json:
    return error_payload("XVERIF_TOOL_TIMEOUT",
                         f"{tool} timed out after {timeout_sec:g}s",
                         tool=tool, timeout_sec=timeout_sec)
