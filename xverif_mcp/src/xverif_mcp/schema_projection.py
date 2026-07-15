"""Agent-oriented MCP projection for native xdebug schemas."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


Json = dict[str, Any]
_REPO_ROOT = Path(__file__).resolve().parents[3]


_SESSION_TOOL_CONTRACTS: dict[str, Json] = {
    "session.open": {"tool": "xverif_debug_session_open", "required": ["name"], "properties": {
        "name": {"type": "string", "description": "Stable name for the new managed session."},
        "daidir": {"type": "string", "description": "Optional simulation daidir path."},
        "fsdb": {"type": "string", "description": "Optional waveform FSDB path."},
        "run_manifest": {"type": "string", "description": "Optional published run-manifest path to verify before opening."},
        "queue": {"type": "string", "description": "Optional backend queue selection."},
        "resource": {"type": "string", "description": "Optional backend resource request."},
    }},
    "session.list": {"tool": "xverif_debug_session_list", "properties": {
        "include_tombstones": {"type": "boolean", "default": False, "description": "Include terminal tombstone records."},
        "verbose": {"type": "boolean", "default": False, "description": "Include detailed session metadata."},
    }},
    "session.doctor": {"tool": "xverif_debug_session_doctor", "any_of": [["name"], ["session_id"]], "properties": {
        "name": {"type": "string", "description": "Managed session name."},
        "session_id": {"type": "string", "description": "Managed session identifier."},
        "verbose": {"type": "boolean", "default": False, "description": "Include detailed health diagnostics."},
    }},
    "session.close": {"tool": "xverif_debug_session_close", "any_of": [["name"], ["session_id"]], "properties": {
        "name": {"type": "string", "description": "Managed session name to close."},
        "session_id": {"type": "string", "description": "Managed session identifier to close."},
    }},
    "session.kill": {"tool": "xverif_debug_session_kill", "any_of": [["name"], ["session_id"]], "properties": {
        "name": {"type": "string", "description": "One exact managed session name to force-clean."},
        "session_id": {"type": "string", "description": "One exact managed session identifier to force-clean."},
    }},
    "session.gc": {"tool": "xverif_debug_session_gc", "properties": {
        "verbose": {"type": "boolean", "default": False, "description": "Include unresolved-session detail in the cleanup report."},
    }},
}


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


def _repair_examples(minimal: Json | None, args_schema: Json) -> tuple[list[Json], list[Json]]:
    required = args_schema.get("required", [])
    selector_groups = [group.get("required", []) for group in args_schema.get("anyOf", []) if isinstance(group, dict)]
    if not minimal or not required and not selector_groups:
        return [], []
    invalid = dict(minimal)
    if "args" in invalid:
        invalid["args"] = {}
    else:
        for name in required:
            invalid.pop(name, None)
        for group in selector_groups:
            for name in group:
                invalid.pop(name, None)
    violations = [f"args.{name}" for name in required]
    if selector_groups:
        violations.append("one required selector group")
    return ([{"description": "Invalid: omits every required argument or selector.", "call": invalid,
              "violates": violations}],
            [{"description": "Corrected minimal call.", "call": minimal}])


def _meaning(value: Json) -> str:
    return value.get("description") or "Meaning is defined by the action contract."


def _guide(schema: Json, path: str, required: set[str] | None = None,
           example: Json | None = None) -> list[Json]:
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
            "meaning": _meaning(value),
        }
        if "enum" in value:
            item["accepted_values"] = value["enum"]
        if "default" in value:
            item["default"] = value["default"]
        if "x-dynamic-contract" in value:
            item["dynamic_contract"] = value["x-dynamic-contract"]
        if isinstance(example, dict) and name in example:
            item["example"] = example[name]
        guide.append(item)
        for keyword in ("oneOf", "anyOf"):
            for branch in value.get(keyword, []):
                if isinstance(branch, dict):
                    guide.extend(_guide(branch, item["path"], set(branch.get("required", [])), example))
        nested_required = set(value.get("required", [])) if isinstance(value.get("required"), list) else set()
        child_example = example.get(name) if isinstance(example, dict) and isinstance(example.get(name), dict) else None
        guide.extend(_guide(value, item["path"], nested_required, child_example))
        items = value.get("items")
        if isinstance(items, dict):
            item_example = None
            if isinstance(example, dict) and isinstance(example.get(name), list) and example[name] and isinstance(example[name][0], dict):
                item_example = example[name][0]
            guide.extend(_guide(items, item["path"] + "[]", set(items.get("required", [])), item_example))
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
    for branch in args_schema.get("allOf", []):
        if not isinstance(branch, dict):
            continue
        condition = branch.get("if", {}).get("properties", {})
        required_when = branch.get("then", {}).get("required", [])
        if not isinstance(condition, dict) or not isinstance(required_when, list):
            continue
        terms = []
        for name, rule in condition.items():
            if isinstance(rule, dict) and "const" in rule:
                terms.append(f"{name}={rule['const']}")
        if terms and required_when:
            out.append("当 " + "、".join(terms) + " 时，还必须提供：" + "、".join(required_when) + "。")
    action_constraints = {
        "event.find": "line_limit 仅在 mode=all 时合法，且只限制返回 evidence，不限制扫描。",
        "stream.query": "query 选择查询种类；field filter 的每个字段独立匹配，字段之间取 AND。",
        "handshake.inspect": "check_data_stable_when_stalled 仅在提供 data 时产生 data-stability finding。",
        "detect_abnormal": "checks 的每项由 type 判别；glitch 必须带 min_pulse_width，stuck 必须带 min_duration。",
    }
    if action in action_constraints:
        out.append(action_constraints[action])
    return out


def _action_descriptions(action: str, schema: Json) -> Json:
    """Read the bilingual action overview from the catalog source."""
    contracts = _contracts_module()
    specs_path = Path(contracts.__file__).with_name("actions") / "actions.yaml"
    specs = json.loads(specs_path.read_text(encoding="utf-8"))["actions"]
    spec = next(item for item in specs if item["name"] == action)
    return {
        "en": spec.get("description_en") or schema.get("description", action),
        "zh": spec.get("description_zh") or schema.get("x-description-zh") or action,
    }


def _session_projection(action: str, descriptions: Json, guidance: Json, include_examples: bool, view: str) -> Json:
    contract = _SESSION_TOOL_CONTRACTS[action]
    args_schema: Json = {"type": "object", "properties": contract["properties"], "additionalProperties": False}
    if contract.get("required"):
        args_schema["required"] = contract["required"]
    if contract.get("any_of"):
        args_schema["anyOf"] = [{"required": group} for group in contract["any_of"]]
    constraints = ["Provide one of: " + " or ".join(" + ".join(group) for group in contract.get("any_of", []))] if contract.get("any_of") else []
    minimal = {name: "<" + name + ">" for name in contract.get("required", [])}
    if contract.get("any_of"):
        minimal[contract["any_of"][0][0]] = "<name>"
    invalid_examples, corrected_examples = _repair_examples(minimal, args_schema)
    payload: Json = {
        "action": action, "kind": "request", "view": view, "call_with": contract["tool"],
        "purpose": descriptions["zh"], "purpose_en": descriptions["en"], "purpose_zh": descriptions["zh"],
        "use_when": guidance["use_when"], "do_not_use_when": guidance["do_not_use_when"], "alternatives": guidance["alternatives"],
        "required_session": False, "fixed_arguments": {}, "args_schema": args_schema,
        "limits_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "constraints": constraints, "parameter_guide": _guide(args_schema, "arguments", set(args_schema.get("required", []))),
        "minimal_call": minimal,
    }
    if include_examples:
        payload["invalid_examples"] = invalid_examples
        payload["corrected_examples"] = corrected_examples
    return payload


def project(action: str, kind: str, view: str, native: Json, include_examples: bool = True) -> Json:
    """Convert a successful native schema response to an MCP-safe discovery view."""
    if native.get("ok") is not True:
        return native
    data = native.get("data", {})
    schema = data.get("schema", {}) if isinstance(data, dict) else {}
    if view == "response":
        if kind != "response":
            return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "view=response requires kind=response"}}
        return {"ok": True, "action": "schema", "summary": {"action": action, "kind": kind, "view": view},
                "data": {"schema": schema, "schema_path": data.get("schema_path")}}
    if kind != "request":
        return {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "request MCP projections require kind=request; use view=response"}}
    root = schema.get("properties", {})
    args_schema = root.get("args", {"type": "object", "properties": {}, "additionalProperties": False})
    limits_schema = root.get("limits", {"type": "object", "properties": {}, "additionalProperties": False})
    contracts = _contracts_module()
    guidance = contracts.guidance_for(action)
    descriptions = _action_descriptions(action, schema)
    if action in _SESSION_TOOL_CONTRACTS:
        return {"ok": True, "action": "schema", "summary": {"action": action, "kind": kind, "view": view},
                "data": _session_projection(action, descriptions, guidance, include_examples, view)}
    minimal, common = _examples(action)
    invalid_examples, corrected_examples = _repair_examples(minimal, args_schema)
    payload: Json = {
        "action": action, "kind": kind, "view": view, "call_with": "xverif_debug_query",
        "purpose": descriptions["zh"], "purpose_en": descriptions["en"], "purpose_zh": descriptions["zh"],
        "use_when": guidance["use_when"], "do_not_use_when": guidance["do_not_use_when"],
        "alternatives": guidance["alternatives"],
        "required_session": bool(root.get("target", {}).get("required", []) or action not in {"actions", "schema", "batch"}),
        "fixed_arguments": {"action": action}, "args_schema": args_schema, "limits_schema": limits_schema,
        "constraints": _constraints(action, args_schema),
        "parameter_guide": _guide(args_schema, "args", set(args_schema.get("required", []))) + _guide(limits_schema, "limits", set(limits_schema.get("required", []))),
        "minimal_call": minimal,
    }
    if include_examples:
        payload["common_examples"] = common
        payload["invalid_examples"] = invalid_examples
        payload["corrected_examples"] = corrected_examples
    if view == "args":
        payload = {key: payload[key] for key in ("action", "kind", "view", "args_schema", "constraints", "parameter_guide", "minimal_call")}
        if include_examples:
            payload["common_examples"] = common
            payload["invalid_examples"] = invalid_examples
            payload["corrected_examples"] = corrected_examples
    return {"ok": True, "action": "schema", "summary": {"action": action, "kind": kind, "view": view}, "data": payload}
