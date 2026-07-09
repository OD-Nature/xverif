"""xdebug-specific MCP error shaping."""

from __future__ import annotations

from typing import Any, Dict

Json = Dict[str, Any]

FORBIDDEN_NATIVE_SESSION_ACTIONS = {
    "session.open",
    "session.close",
    "session.kill",
    "session.gc",
    "session.doctor",
    "session.list",
}


def is_forbidden_native_session_action(action: str | None) -> bool:
    return action in FORBIDDEN_NATIVE_SESSION_ACTIONS


def forbidden_native_session_error(action: str | None) -> Json:
    action_text = action or "session.*"
    if action == "session.open":
        tool = "xverif_debug_session_open"
        args: Json = {"name": "case_a", "fsdb": "<waves.fsdb>"}
    elif action in {"session.close", "session.kill"}:
        tool = "xverif_debug_session_close"
        args = {"session_id": "case_a"}
    else:
        tool = "xverif_debug_session_list"
        args = {}
    return {
        "ok": False,
        "error": {
            "code": "NATIVE_SESSION_ACTION_FORBIDDEN",
            "message": (
                f"MCP debug tools do not allow native xdebug action {action_text}; "
                "use xverif_debug_session_* tools for session lifecycle"
            ),
            "recoverable": True,
            "error_layer": "wrapper",
            "invalid_arg": "action",
            "expected": "use MCP session tools instead of native session.* actions",
            "example_note": "示例仅说明当前 MCP 入口的 session 生命周期工具形态；不要在 xverif_debug_query 中调用 native session.* action。",
            "correct_example": {"tool": tool, "args": args},
            "next_actions": [
                "xverif_debug_session_open",
                "xverif_debug_session_close",
                "xverif_debug_session_list",
            ],
        },
    }


def translate_native_example_for_query(response: Json, *, session_id: str) -> Json:
    """Return a copy whose error.correct_example matches xverif_debug_query."""
    out = dict(response)
    error = out.get("error")
    if not isinstance(error, dict):
        return out
    error = dict(error)
    example = error.get("correct_example")
    if isinstance(example, dict):
        action = example.get("action") or out.get("action")
        args = example.get("args") if isinstance(example.get("args"), dict) else {}
        tool_args: Json = {
            "session_id": session_id,
            "action": action,
            "args": args,
        }
        if isinstance(example.get("limits"), dict):
            tool_args["limits"] = example["limits"]
        if isinstance(example.get("output"), dict):
            tool_args["output"] = example["output"]
        error["correct_example"] = {
            "tool": "xverif_debug_query",
            "args": tool_args,
        }
        error["example_note"] = (
            "示例仅说明 xverif_debug_query 的 MCP 参数形态；不要把 "
            "api_version/target 写进 MCP args。"
        )
    out["error"] = error
    return out


def xout_error(response: Json) -> str:
    action = response.get("action") or "error"
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    lines = ["@xdebug.error.v1", f"action: {action}"]
    for key in (
        "code",
        "message",
        "recoverable",
        "error_layer",
        "invalid_arg",
        "expected",
        "received",
        "received_type",
        "allowed_values",
        "available_values",
        "missing_name",
        "missing_resource",
        "did_you_mean",
        "example_note",
    ):
        if key in error:
            lines.append(f"{key}: {_xout_value(error[key])}")
    if "correct_example" in error:
        lines.append("")
        lines.append("correct_example:")
        lines.append(f"  json: {_xout_value(error['correct_example'])}")
    next_actions = error.get("next_actions")
    if isinstance(next_actions, list) and next_actions:
        lines.append("")
        lines.append("next_actions:")
        for item in next_actions:
            lines.append(f"- {_xout_value(item)}")
    return "\n".join(lines).rstrip() + "\n"


def _xout_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("\n", "\\n")
