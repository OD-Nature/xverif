#!/usr/bin/env python3
"""Mark response extension points without inferring runtime contracts from examples.

Compact examples are illustrations, not a complete runtime type declaration.
Only a handler-backed ActionContract may close a response object.  This tool
therefore preserves open primary objects as explicit dynamic contracts instead
of guessing properties or types from one example.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs" / "actions" / "actions.yaml"


def closed(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        out["required"] = required
    return out


def value_at_contract() -> dict[str, Any]:
    logic_value = closed({
        "value": {"type": "string", "description": "格式化后的四态 SystemVerilog literal。", "x-description-zh": "格式化后的四态 SystemVerilog literal。"},
        "known": {"type": "boolean", "description": "value 是否不含 X/Z。", "x-description-zh": "value 是否不含 X/Z。"},
        "width": {"type": "integer", "minimum": 1, "description": "可靠时的逻辑位宽。", "x-description-zh": "可靠时的逻辑位宽。"},
        "bits": {"type": "string", "description": "可靠时的逐位 bit/X/Z 表示。", "x-description-zh": "可靠时的逐位 bit/X/Z 表示。"},
        "has_x": {"type": "boolean", "description": "value 是否包含 X。", "x-description-zh": "value 是否包含 X。"},
        "has_z": {"type": "boolean", "description": "value 是否包含 Z。", "x-description-zh": "value 是否包含 Z。"},
        "requested_value_format": {"type": "string", "description": "调用方请求但未完全可用的显示格式。", "x-description-zh": "调用方请求但未完全可用的显示格式。"},
        "effective_value_format": {"type": "string", "description": "为保留逻辑值实际采用的显示格式。", "x-description-zh": "为保留逻辑值实际采用的显示格式。"},
        "value_format_reason": {"type": "string", "description": "显示格式被调整的原因。", "x-description-zh": "显示格式被调整的原因。"},
    }, ["value", "known"])
    logic_value["type"] = ["object", "null"]
    logic_value["description"] = "采样得到的四态 LogicValue；没有可用采样 cell 时为 null。"
    logic_value["x-description-zh"] = "采样得到的四态 LogicValue。"
    return {
        "summary": closed({
            "signal": {"type": "string", "description": "被读取的最终 signal 路径。", "x-description-zh": "被读取的最终 signal 路径。"},
            "time": {"type": "string", "description": "实际采样时间。", "x-description-zh": "实际采样时间。"},
            "known": {"type": "boolean", "description": "采样值是否不含 X/Z。", "x-description-zh": "采样值是否不含 X/Z。"},
            "status": {"type": "string", "description": "采样状态。", "x-description-zh": "采样状态。"},
        }, ["signal", "time", "known", "status"]),
        "data": closed({
            "value": logic_value,
            "clock_context": {"type": "object", "description": "clock edge 与 sample-point 解析上下文。", "x-description-zh": "clock edge 与 sample-point 解析上下文。",
                              "x-dynamic-contract": "clock sampling helper 发布的上下文字段；读取 clock、edge、sample_point 与实际命中状态。", "additionalProperties": True},
            "xbit_hints": {"type": "object", "description": "可选 xbit 后续计算提示。", "x-description-zh": "可选 xbit 后续计算提示。",
                           "x-dynamic-contract": "xbit hint contract 由 xbit capability 定义。", "additionalProperties": True},
        }, ["value", "clock_context"]),
    }


HANDLER_RESPONSE_CONTRACTS = {"value.at": value_at_contract}


def error_object() -> dict[str, Any]:
    return closed({
        "code": {"type": "string", "description": "稳定机器错误码。", "x-description-zh": "稳定机器错误码。"},
        "message": {"type": "string", "description": "人类可读错误说明。", "x-description-zh": "人类可读错误说明。"},
        "recoverable": {"type": "boolean", "description": "修正请求或环境后是否可重试。", "x-description-zh": "修正请求或环境后是否可重试。"},
        "error_layer": {"type": "string", "enum": ["schema", "handler", "internal", "transport", "wrapper", "session_manager"], "description": "产生错误的合同层。", "x-description-zh": "产生错误的合同层。"},
        "invalid_arg": {"type": "string", "description": "可修正的参数路径。", "x-description-zh": "可修正的参数路径。"},
        "expected": {"type": "string", "description": "期望的类型或语义。", "x-description-zh": "期望的类型或语义。"},
        "received_type": {"type": "string", "description": "实际输入 JSON 类型。", "x-description-zh": "实际输入 JSON 类型。"},
        "received": {"description": "实际收到的 JSON 值。", "x-description-zh": "实际收到的 JSON 值。"},
        "allowed_values": {"type": "array", "description": "合法候选值。", "x-description-zh": "合法候选值。", "items": {}},
        "available_values": {"type": "array", "description": "当前资源中可用的候选值。", "x-description-zh": "当前资源中可用的候选值。", "items": {}},
        "candidates": {"type": "array", "description": "相近候选项。", "x-description-zh": "相近候选项。", "items": {}},
        "suggested_actions": {"type": "array", "description": "建议的替代 action。", "x-description-zh": "建议的替代 action。", "items": {}},
        "supported": {"type": "array", "description": "实现支持的候选能力。", "x-description-zh": "实现支持的候选能力。", "items": {}},
        "reason": {"type": "string", "description": "该值或请求不被支持的原因。", "x-description-zh": "该值或请求不被支持的原因。"},
        "did_you_mean": {"type": "string", "description": "建议改用的字段或 action。", "x-description-zh": "建议改用的字段或 action。"},
        "required_any_of": {"type": "array", "description": "至少需要提供的一组参数。", "x-description-zh": "至少需要提供的一组参数。", "items": {}},
        "schema_path": {"type": "string", "description": "用于校验的 request schema 路径。", "x-description-zh": "用于校验的 request schema 路径。"},
        "missing_name": {"type": "string", "description": "缺失的命名资源。", "x-description-zh": "缺失的命名资源。"},
        "missing_resource": {"type": "string", "description": "缺失的设计或波形资源。", "x-description-zh": "缺失的设计或波形资源。"},
        "next_actions": {"type": "array", "description": "可继续执行的恢复 action。", "x-description-zh": "可继续执行的恢复 action。", "items": {}},
        "example_note": {"type": "string", "description": "correct_example 的使用说明。", "x-description-zh": "correct_example 的使用说明。"},
        "cause_code": {"type": "string", "description": "底层原因错误码。", "x-description-zh": "底层原因错误码。"},
        "correct_example": {"type": "object", "description": "可直接修正的最小请求。", "x-description-zh": "可直接修正的最小请求。", "x-dynamic-contract": "该对象是对应 action 的 native request example。", "additionalProperties": True},
    }, ["code", "message", "recoverable", "error_layer"])


def error_summary() -> dict[str, Any]:
    return closed({
        "status": {"const": "error", "description": "固定错误状态。", "x-description-zh": "固定错误状态。"},
        "error_code": {"type": "string", "description": "与 error.code 相同的摘要错误码。", "x-description-zh": "与 error.code 相同的摘要错误码。"},
    }, ["status", "error_code"])


def dynamic_item(name: str) -> dict[str, Any]:
    return {"type": "object", "description": f"{name} 的动态诊断条目。",
            "x-description-zh": f"{name} 的动态诊断条目。",
            "x-dynamic-contract": "每个条目由 finding/warning type 决定；调用方必须读取 type、severity、message 和 evidence。",
            "additionalProperties": True}


def update(schema: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    props = out.setdefault("properties", {})
    for name in ("summary", "data", "meta"):
        node = props.get(name)
        if not isinstance(node, dict) or name not in example:
            continue
        generated = str(node.get("description", "")).endswith("稳定 response 字段。")
        if generated:
            props[name] = {"type": "object", "description": f"{name} 的 action-specific response 对象。",
                           "x-description-zh": f"{name} 的 action-specific response 对象。",
                           "x-dynamic-contract": "在 ActionContract 明确闭合前，字段由该 action handler 的稳定业务结果定义。",
                           "additionalProperties": True}
    for name in ("findings", "warnings"):
        node = props.get(name)
        if not isinstance(node, dict):
            continue
        if node.get("type") != "array" or "items" not in node:
            props[name] = {
                "type": "array", "description": f"{name} 诊断列表。", "x-description-zh": f"{name} 诊断列表。",
                "items": dynamic_item(name),
            }
    # Envelope fields are known globally.  Closing the root catches accidental
    # business-field drift while retaining explicitly modeled diagnostics.
    props.setdefault("tool", {"type": "object", "description": "生成响应的工具元数据。",
                               "x-description-zh": "生成响应的工具元数据。",
                               "x-dynamic-contract": "build metadata 由工具版本定义。", "additionalProperties": True})
    props.setdefault("session", {"type": ["object", "null"], "description": "本响应关联的 session 元数据。",
                                  "x-description-zh": "本响应关联的 session 元数据。",
                                  "x-dynamic-contract": "session transport metadata 由 session contract 定义。", "additionalProperties": True})
    props.setdefault("schema_version", {"type": "string", "description": "生成该响应的 schema 版本路径。", "x-description-zh": "生成该响应的 schema 版本路径。"})
    props.setdefault("text", {"type": "string", "description": "可选的人类可读渲染文本。", "x-description-zh": "可选的人类可读渲染文本。"})
    props.setdefault("suggested_next_actions", {"type": "array", "description": "建议的后续 action。", "x-description-zh": "建议的后续 action。", "items": dynamic_item("suggested_next_actions")})
    out["additionalProperties"] = False
    action = str(out.get("properties", {}).get("action", {}).get("enum", [""])[0])
    if action in HANDLER_RESPONSE_CONTRACTS:
        props.update(HANDLER_RESPONSE_CONTRACTS[action]())
    # A handler error always has data:null and the common error summary.  Keep
    # the action success shape separate so success-only required fields do not
    # reject a valid diagnostic response.
    success_summary = props.get("summary", {})
    if isinstance(success_summary, dict) and success_summary.get("description") == "成功摘要或统一错误摘要。":
        success_summary = success_summary.get("anyOf", [{}])[0]
    success_data = props.get("data", {})
    if isinstance(success_data, dict) and success_data.get("description") == "成功业务 data 或错误 null。":
        success_data = success_data.get("anyOf", [{}])[0]
    if isinstance(props.get("summary"), dict) and props["summary"].get("description") != "成功摘要或统一错误摘要。":
        props["summary"] = {"anyOf": [success_summary, error_summary()],
                            "description": "成功摘要或统一错误摘要。", "x-description-zh": "成功摘要或统一错误摘要。"}
    if isinstance(props.get("data"), dict) and props["data"].get("description") != "成功业务 data 或错误 null。":
        props["data"] = {"anyOf": [success_data, {"type": "null", "description": "错误响应没有业务 data。", "x-description-zh": "错误响应没有业务 data。"}],
                         "description": "成功业务 data 或错误 null。", "x-description-zh": "成功业务 data 或错误 null。"}
    if not (isinstance(props.get("error"), dict) and props["error"].get("description") == "统一错误对象。"):
        props["error"] = {"anyOf": [{"type": "null", "description": "成功响应没有 error。", "x-description-zh": "成功响应没有 error。"}, error_object()],
                          "description": "统一错误对象。", "x-description-zh": "统一错误对象。"}
    branch = {
            "x-response-branch-contract": "generated",
            "if": {"properties": {"ok": {"const": True}}, "required": ["ok"]},
            "then": {"properties": {"summary": success_summary, "data": success_data, "error": {"type": "null"}}},
            "else": {"properties": {"summary": error_summary(), "data": {"type": "null"}, "error": error_object()}},
        }
    all_of = list(out.get("allOf", []))
    if all_of and isinstance(all_of[-1], dict) and (all_of[-1].get("x-response-branch-contract") == "generated" or "if" in all_of[-1]):
        all_of[-1] = branch
    else:
        all_of.append(branch)
    out["allOf"] = all_of
    out["x-response-branches"] = "ok=true uses success summary/data and error=null; ok=false uses the common diagnostic response."
    mark_dynamic(out)
    return out


def mark_dynamic(node: Any) -> None:
    """Every intentional extension point must say why it is dynamic."""
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" and node.get("additionalProperties") is True:
        node.setdefault("description", "由运行时 type/source 决定的扩展对象。")
        node.setdefault("x-description-zh", node["description"])
        node.setdefault("x-dynamic-contract", "这是显式动态扩展点；调用方必须依据 type/source 或 action response guide 解释字段。")
    if node.get("type") == "array" and "items" not in node:
        node["items"] = dynamic_item("response items")
    for child in node.get("properties", {}).values():
        mark_dynamic(child)
    if isinstance(node.get("items"), dict):
        mark_dynamic(node["items"])
    for key in ("oneOf", "anyOf", "allOf"):
        for child in node.get(key, []):
            mark_dynamic(child)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    errors: list[str] = []
    for spec in json.loads(SPECS.read_text(encoding="utf-8"))["actions"]:
        if spec.get("status") == "removed":
            continue
        # These protocol responses have stricter family generators which are
        # their canonical source; never layer compact-example inference over
        # them.
        if spec["name"].startswith("axi.") or spec["name"] == "apb.statistics":
            continue
        schema_path = ROOT / spec["schemas"]["response"]
        example_path = ROOT / spec["examples"]["response"][0]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_path.read_text(encoding="utf-8"))
        expected = update(schema, example)
        if schema != expected:
            if args.check:
                errors.append(f"{schema_path.relative_to(ROOT)}: response contract is not synced")
            else:
                schema_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("\n".join(errors))
        return 1
    print("response contracts are synced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
