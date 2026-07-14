"""Agent-oriented MCP projection for native xdebug schemas."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


Json = dict[str, Any]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _contracts_module() -> Any:
    path = _REPO_ROOT / "xdebug" / "specs" / "action_contracts.py"
    spec = importlib.util.spec_from_file_location("xdebug_action_contracts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("xdebug action contracts are unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _examples(action: str) -> tuple[Json | None, list[Json]]:
    path = _REPO_ROOT / "xdebug" / "examples" / "requests" / f"{action}.basic.json"
    if not path.is_file():
        return None, []
    request = json.loads(path.read_text(encoding="utf-8"))
    call: Json = {"session_id": "<session_id>", "action": action, "args": request.get("args", {})}
    if request.get("limits"):
        call["limits"] = request["limits"]
    return call, [{"description": "该 action 的最小 checked-in MCP 调用。", "call": call}]


def _guide(schema: Json, path: str, required: set[str] | None = None) -> list[Json]:
    required = required or set()
    guide: list[Json] = []
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not isinstance(props, dict):
        return guide
    for name, value in props.items():
        if not isinstance(value, dict):
            continue
        item: Json = {
            "path": f"{path}.{name}",
            "required": name in required,
            "type": value.get("type", "oneOf" if "oneOf" in value else "schema"),
            "meaning": value.get("x-description-zh") or value.get("description") or "该字段的语义由 action contract 定义。",
        }
        if "enum" in value:
            item["accepted_values"] = value["enum"]
        if "default" in value:
            item["default"] = value["default"]
        if "x-dynamic-contract" in value:
            item["dynamic_contract"] = value["x-dynamic-contract"]
        guide.append(item)
        nested_required = set(value.get("required", [])) if isinstance(value.get("required"), list) else set()
        guide.extend(_guide(value, item["path"], nested_required))
        items = value.get("items")
        if isinstance(items, dict):
            guide.extend(_guide(items, item["path"] + "[]", set(items.get("required", []))))
    return guide


def _constraints(action: str, args_schema: Json) -> list[str]:
    out: list[str] = []
    required = args_schema.get("required", [])
    if required:
        out.append("必须提供：" + "、".join(required) + "。")
    for group in args_schema.get("anyOf", []):
        values = group.get("required") if isinstance(group, dict) else None
        if values:
            out.append("还必须满足以下一组参数：" + "、".join(values) + "。")
    action_constraints = {
        "event.find": "line_limit 仅在 mode=all 时合法，且只限制返回 evidence，不限制扫描。",
        "stream.query": "query 选择查询种类；field filter 的每个字段独立匹配，字段之间取 AND。",
        "handshake.inspect": "check_data_stable_when_stalled 仅在提供 data 时产生 data-stability finding。",
        "detect_abnormal": "checks 的每项由 type 判别；glitch 必须带 min_pulse_width，stuck 必须带 min_duration。",
    }
    if action in action_constraints:
        out.append(action_constraints[action])
    return out


def project(action: str, kind: str, view: str, native: Json, include_examples: bool = True) -> Json:
    """Convert a successful native schema response to an MCP-safe discovery view."""
    if native.get("ok") is not True:
        return native
    data = native.get("data", {})
    schema = data.get("schema", {}) if isinstance(data, dict) else {}
    if view == "native":
        return native
    if view == "response":
        if kind != "response":
            return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "view=response requires kind=response"}}
        primary = _guide(schema, "response", set(schema.get("required", [])))
        return {"ok": True, "action": "schema", "summary": {"action": action, "kind": kind, "view": view},
                "data": {"schema": schema, "schema_path": data.get("schema_path"), "response_guide": {"primary_fields": primary,
                "empty_result": "检查 summary/data 的 action-specific primary fields；不要把空 evidence 当作完整分析。",
                "completeness": "若存在 truncated、analysis_complete、scan_complete 或相关字段，必须先检查后再下结论。"}}}
    if kind != "request":
        return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "request MCP projections require kind=request; use view=response"}}
    root = schema.get("properties", {})
    args_schema = root.get("args", {"type": "object", "properties": {}, "additionalProperties": False})
    limits_schema = root.get("limits", {"type": "object", "properties": {}, "additionalProperties": False})
    contracts = _contracts_module()
    guidance = contracts.guidance_for(action)
    minimal, common = _examples(action)
    payload: Json = {
        "action": action, "kind": kind, "view": view, "call_with": "xverif_debug_query",
        "purpose": schema.get("x-description-zh") or schema.get("description"),
        "use_when": guidance["use_when"], "do_not_use_when": guidance["do_not_use_when"],
        "alternatives": guidance["alternatives"],
        "required_session": bool(root.get("target", {}).get("required", []) or action not in {"actions", "schema", "batch"}),
        "fixed_arguments": {"action": action}, "args_schema": args_schema, "limits_schema": limits_schema,
        "constraints": _constraints(action, args_schema),
        "parameter_guide": _guide(args_schema, "args", set(args_schema.get("required", []))) + _guide(limits_schema, "limits", set(limits_schema.get("required", []))),
        "minimal_call": minimal,
        "response_guide": {"schema_view": "调用 xverif_debug_get_schema(action, kind='response', view='response') 获取 primary fields。"},
    }
    if include_examples:
        payload["common_examples"] = common
        payload["invalid_examples"] = []
    if view == "args":
        payload = {key: payload[key] for key in ("action", "kind", "view", "args_schema", "constraints", "parameter_guide", "minimal_call", "response_guide")}
        if include_examples:
            payload["common_examples"] = common
            payload["invalid_examples"] = []
    return {"ok": True, "action": "schema", "summary": {"action": action, "kind": kind, "view": view}, "data": payload}
