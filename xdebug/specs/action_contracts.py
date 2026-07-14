"""Canonical AI-facing contracts for xdebug public actions.

The action directory owns registration; this module owns the semantics that an
agent needs in order to construct a request.  It deliberately keys overrides
by ``(action, argument)`` rather than bare argument name.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


Json = dict[str, Any]


COMMON_DESCRIPTIONS = {
    "time": "目标采样时间。使用带单位的 canonical 时间字符串；裸数字仅在 time_unit 明确时解释。",
    "time_range": "分析时间窗口；begin/end 为闭区间端点，可分别省略以使用可用波形边界。",
    "time_unit": "仅解释不带单位的时间数字；带单位时间字符串优先，auto 不改变带单位值。",
    "edge": "clock 采样边沿。默认值必须以 schema default 为准；negedge 适合多数 monitor 语义。",
    "sample_point": "posedge 或 dual 采样时的沿前/沿后观察点；它不改变时间范围或 raw 波形。",
    "line_limit": "只限制返回的 evidence 行数，不限制扫描、聚合或 verdict；结果须结合 completeness 字段理解。",
    "signal": "最终叶子信号路径；aggregate 根、数组根或 struct 根不自动展开。",
    "signals": "信号路径列表，或 alias 到信号路径/表达式的映射；表达式中引用 alias 而非再次嵌套路径。",
    "output": "导出目标与显示控制；不同 action 对 path、file_format 和 verbose 的支持以本 action schema 为准。",
    "name": "本 action 所属命名空间中的已保存对象名称；不得假定可跨 cursor/list/protocol config 复用。",
    "mode": "本 action 的处理或返回模式；合法值、默认值和与其它参数的关系由 action-specific 合同定义。",
    "query": "本 action 的查询选择器；不要把其它 action 的 index、channel 或 filter 形态迁入。",
    "rules": "本 action 的协议/检查规则对象；每个 rule 的默认和生效条件见嵌套字段说明。",
    "limits": "执行资源限制；只使用本 action 的顶层 limits properties，不能写入 args.limits。",
}


ACTION_GUIDANCE: dict[str, Json] = {
    "value.at": {
        "use_when": ["需要一个最终叶子信号在单一采样时刻的值。"],
        "do_not_use_when": ["需要原始值变化时间线。", "需要多信号布尔表达式求值。"],
        "alternatives": [
            {"action": "signal.changes", "when": "需要每次原始值变化。"},
            {"action": "expr.eval_at", "when": "需要在同一采样时刻求多信号表达式。"},
        ],
    },
    "signal.changes": {
        "use_when": ["需要一个信号的原始波形变化时间线或聚合变化统计。"],
        "do_not_use_when": ["需要按 clock edge 的协议语义采样。"],
        "alternatives": [{"action": "event.find", "when": "需要按 clock 对表达式采样。"}],
    },
    "event.find": {
        "use_when": ["需要按 clock edge 查找满足表达式的采样事件。"],
        "do_not_use_when": ["需要原始 value-change timeline 或标准 AXI/APB transaction。"],
        "alternatives": [{"action": "signal.changes", "when": "需要原始跳变。"}],
    },
    "handshake.inspect": {
        "use_when": ["需要检查通用 valid-ready transfer、stall 或数据稳定性。"],
        "do_not_use_when": ["需要 AXI/APB 专用 transaction 关联。"],
        "alternatives": [{"action": "axi.query", "when": "接口是标准 AXI。"}],
    },
    "detect_abnormal": {
        "use_when": ["需要在 raw waveform 中检查 X/Z、短脉冲或长时间不变。"],
        "do_not_use_when": ["需要证明 valid-ready 协议违规。"],
        "alternatives": [{"action": "handshake.inspect", "when": "需要协议层 stall 或稳定性结论。"}],
    },
    "stream.query": {
        "use_when": ["已加载通用 stream 配置，需要查询 transfer、stall、packet 或字段。"],
        "do_not_use_when": ["接口是 AXI/APB 且需要其标准专用语义。"],
        "alternatives": [{"action": "event.find", "when": "只需一次性表达式找点。"}],
    },
}


ACTION_ARG_OVERRIDES: dict[tuple[str, str], Json] = {
    ("signal.changes", "mode"): {
        "description": "返回模式：timeline 返回逐变化 evidence；summary 只返回聚合事实。与 aggregate_only 不同时使用。",
        "enum": ["timeline", "summary"], "default": "timeline",
    },
    ("event.find", "mode"): {
        "description": "first/last 返回时间顺序的首/末命中；all 返回多个命中。line_limit 仅能与 all 同用。",
        "enum": ["first", "last", "all"], "default": "first",
    },
    ("event.find", "aggregate"): {
        "description": "事件聚合合同。未提供时返回匹配事件；与 events/group_by 的组合以 constraints 为准。",
        "type": "object", "properties": {"operation": {"type": "string", "enum": ["count"]}},
        "additionalProperties": False,
    },
    ("event.find", "group_by"): {
        "description": "按 signals alias 分组的字段名列表。每项必须引用 args.signals 中的 alias。",
        "type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True,
    },
    ("event.find", "max_samples"): {
        "description": "允许检查的 clock sample 数量上限；耗尽时分析不完整，不是返回行数限制。",
        "type": "integer", "minimum": 1,
    },
    ("event.find", "rst_n"): {
        "description": "低有效 reset 信号路径或 alias；reset asserted 的 sample 不参与事件匹配。",
        "type": "string", "minLength": 1,
    },
    ("handshake.inspect", "rules"): {
        "description": "valid-ready 检查规则；未提供字段使用各自 schema default。",
        "type": "object", "properties": {
            "max_wait_cycles": {"type": "integer", "minimum": 0, "description": "从 valid 被采样为 1 到 handshake 前允许的最大连续等待 cycle 数。"},
            "check_data_stable_when_stalled": {"type": "boolean", "default": False, "description": "仅提供 data 时有效；检查 valid=1、ready=0 期间 data 是否改变。"},
            "require_valid_hold_until_handshake": {"type": "boolean", "default": True, "description": "检查 valid 在首次断言后是否保持到 valid&&ready handshake。"},
            "ready_without_valid": {"type": "string", "enum": ["summary", "intervals", "all"], "default": "summary", "description": "ready=1 且 valid=0 的返回粒度；这是活动统计，不单独等于协议错误。"},
        }, "additionalProperties": False,
    },
    ("handshake.inspect", "data"): {
        "description": "可选 payload 信号路径或路径列表；仅提供时才可检查 stalled-data stability。",
    },
    ("axi.channel_stall", "rules"): {
        "description": "AXI channel stall 阈值规则。",
        "type": "object", "properties": {
            "max_wait_cycles": {"type": "integer", "minimum": 0, "default": 100,
                                "description": "超过该连续 valid&&!ready sample 数才返回 long_stall finding。"},
        }, "additionalProperties": False,
    },
    ("event.export", "group_by"): {
        "description": "按 signals alias 分组的字段名列表。每项必须引用 args.signals 中的 alias。",
        "type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True,
    },
    ("detect_abnormal", "checks"): {
        "description": "要执行的 raw-waveform 检查。省略时执行运行时默认检查集合；字符串 shorthand 不被接受。",
        "type": "array", "minItems": 1, "items": {"description": "一项由 type 判别的 abnormal 检查。", "oneOf": [
            {"type": "object", "description": "unknown_xz 检查项。", "required": ["type"], "properties": {"type": {"const": "unknown_xz", "description": "报告区间内出现的 X/Z。"}}, "additionalProperties": False},
            {"type": "object", "description": "glitch 检查项。", "required": ["type", "min_pulse_width"], "properties": {"type": {"const": "glitch", "description": "选择短脉冲检查。"}, "min_pulse_width": {"type": "string", "description": "报告严格短于该 canonical duration 的脉冲。"}}, "additionalProperties": False},
            {"type": "object", "description": "stuck 检查项。", "required": ["type", "min_duration"], "properties": {"type": {"const": "stuck", "description": "选择长时间不变检查。"}, "min_duration": {"type": "string", "description": "报告持续至少该 canonical duration 的不变区间。"}}, "additionalProperties": False},
        ]},
    },
    ("stream.query", "query"): {
        "description": "查询种类。beat stream 支持 summary、first/last_transfer、transfer_window、first/last_stall、stall_window；packet stream 还支持 first/last_packet、packet_at、packet_window。启用 filter 时可用集合进一步受 packet 边界限制。",
        "type": "string", "enum": ["summary", "first_transfer", "last_transfer", "transfer_window", "first_stall", "last_stall", "stall_window", "first_packet", "last_packet", "packet_at", "packet_window"],
    },
}


def guidance_for(action: str) -> Json:
    return deepcopy(ACTION_GUIDANCE.get(action, {
        "use_when": ["需要执行该 action 的 catalog 所述能力。"],
        "do_not_use_when": ["任务不属于该 action 的公开合同。"],
        "alternatives": [],
    }))


def apply_argument_contract(action: str, name: str, schema: Json) -> Json:
    """Return the action-specific property contract without mutating its input."""
    result = deepcopy(schema)
    override = ACTION_ARG_OVERRIDES.get((action, name))
    if override:
        if "type" in override:
            for key in ("oneOf", "anyOf", "allOf"):
                result.pop(key, None)
        if "oneOf" in override:
            for key in ("type", "properties", "items", "required"):
                result.pop(key, None)
        result.update(deepcopy(override))
    if "description" not in result and name in COMMON_DESCRIPTIONS:
        result["description"] = COMMON_DESCRIPTIONS[name]
    if "x-description-zh" not in result and "description" in result:
        result["x-description-zh"] = result["description"]
    return result


def complete_descriptions(schema: Json, path: str) -> Json:
    """Fill structural descriptions for generated nested fields.

    Action-specific text must be supplied above for semantic fields; this
    keeps generated helper shapes discoverable instead of exposing anonymous
    JSON objects to an agent.
    """
    result = deepcopy(schema)
    if (result.get("type") == "object" or "properties" in result) and "description" not in result:
        result["description"] = f"{path} 的组合参数对象。"
    if result.get("type") == "array" and "description" not in result:
        result["description"] = f"{path} 的有序项目列表。"
    if "description" not in result and result.get("type") in {"string", "integer", "number", "boolean"}:
        result["description"] = f"{path} 的 action-specific 参数值。"
    if "description" in result and "x-description-zh" not in result:
        result["x-description-zh"] = result["description"]
    for key, value in list(result.get("properties", {}).items()):
        if isinstance(value, dict):
            result["properties"][key] = complete_descriptions(value, f"{path}.{key}")
    items = result.get("items")
    if isinstance(items, dict):
        result["items"] = complete_descriptions(items, f"{path}[]")
    for keyword in ("oneOf", "anyOf", "allOf"):
        branches = result.get(keyword)
        if isinstance(branches, list):
            result[keyword] = [complete_descriptions(item, path) if isinstance(item, dict) else item for item in branches]
    return result
