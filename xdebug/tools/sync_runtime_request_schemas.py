#!/usr/bin/env python3
"""Sync strict runtime request schemas for xdebug actions."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from sync_action_schema_hints import PARAM_DESCRIPTIONS


XDEBUG_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = XDEBUG_ROOT / "specs" / "actions" / "actions.yaml"
REQUEST_EXAMPLES = XDEBUG_ROOT / "examples" / "requests"


ADDITIONAL_ARG_SCHEMAS: dict[str, dict[str, Any]] = {
    "action": {"type": "string"},
    "analysis": {"type": "string", "enum": ["latency", "osd", "pending"]},
    "address": {"type": "string"},
    "addr": {"type": "string"},
    "aggregate": {"type": "object"},
    "aggregate_only": {"type": "boolean"},
    "auth_token": {"type": "string"},
    "bind": {"type": "string"},
    "bind_host": {"type": "string"},
    "channel": {"type": "string"},
    "clk_period": {"type": "string"},
    "config": {"type": "object"},
    "context_lines": {"type": "integer"},
    "data": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
    "dependency_types": {"type": "array", "items": {"type": "string"}},
    "dynamic": {"type": "boolean"},
    "edge": {"type": "string", "enum": ["posedge", "negedge", "dual"]},
    "events": {"type": "boolean"},
    "field_scope": {"type": "string"},
    "group_by": {"type": "array"},
    "host": {"type": "string"},
    "include_alias_candidates": {"type": "boolean"},
    "include_compat_fields": {"type": "boolean"},
    "include_control": {"type": "boolean"},
    "include_parity": {"type": "boolean"},
    "include_preview": {"type": "boolean"},
    "include_statement_only": {"type": "boolean"},
    "id": {"type": "string"},
    "last": {"type": "boolean"},
    "line_limit": {"type": "integer", "minimum": 1},
    "method": {"type": "string", "enum": ["top_n", "threshold"]},
    "limits": {"type": "object"},
    "protocol_query": {
        "type": "object",
        "properties": {
            "line_limit": {"type": "integer", "minimum": 1},
            "index": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
        "description": "Protocol query controls; use 1-based query.index and query.line_limit; legacy quantity fields are rejected.",
    },
    "match": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "op": {"type": "string", "enum": ["==", "!=", "<", "<=", ">", ">=", "range"]},
            "value": {"type": "string"},
            "lo": {"type": "string"},
            "hi": {"type": "string"},
            "mask": {"type": "string"},
            "field_scope": {"type": "string", "enum": ["beat", "stable", "any"]},
        },
        "required": ["field"],
        "additionalProperties": False,
    },
    "max_depth": {"type": "integer"},
    "max_edges": {"type": "integer"},
    "max_events": {"type": "integer", "minimum": 1},
    "max_rows": {"type": "integer"},
    "max_samples": {"type": "integer", "minimum": 1},
    "name_pattern": {"type": "string"},
    "no_statement_only": {"type": "boolean"},
    "note": {"type": "string"},
    "origin": {"type": "string"},
    "output": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "file_format": {"type": "string"},
            "verbose": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "packet_index": {"type": "integer"},
    "path": {"type": "string"},
    "role": {"type": "string"},
    "rules": {"oneOf": [{"type": "array"}, {"type": "object"}]},
    "sample_point": {"type": "string", "enum": ["before", "after"]},
    "slice_hint": {"type": "object"},
    "source": {"type": "string"},
    "symbol": {"type": "string"},
    "time_range": {
        "type": "object",
        "properties": {
            "begin": {"type": "string"},
            "end": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "time_unit": {"type": "string", "enum": ["auto", "fs", "ps", "ns", "us", "ms", "s"]},
    "threshold": {"type": "string"},
    "top_n": {"type": "integer", "minimum": 1},
    "transport": {"type": "string", "enum": ["uds", "tcp", "file"]},
    "verbose": {"type": "boolean"},
    "value_format": {
        "type": "string",
        "enum": ["hex", "bin", "dec"],
        "description": "仅控制响应中信号值的显示格式；不影响采样、时间或导出文件格式。",
    },
}


EXTRA_ARGS_BY_ACTION: dict[str, set[str]] = {
    "actions": {"output"},
    "apb.cursor": {"direction"},
    "apb.config.list": {"name"},
    "apb.config.load": {"config", "config_path"},
    "apb.query": {"direction", "address", "addr", "query", "last"},
    "apb.transfer_window": {"line_limit", "time_range"},
    "axi.analysis": {"analysis", "direction", "line_limit"},
    "axi.channel_stall": {"channel", "line_limit", "rules", "time_range"},
    "axi.config.list": {"name"},
    "axi.config.load": {"config", "config_path"},
    "axi.cursor": {"direction"},
    "axi.export": {"output", "time_range"},
    "axi.latency_outlier": {"direction", "line_limit", "method", "output", "threshold", "time_range", "top_n"},
    "axi.outstanding_timeline": {"direction", "line_limit", "time_range"},
    "axi.query": {"direction", "address", "addr", "id", "query", "last", "output"},
    "axi.request_response_pair": {"direction", "line_limit", "time_range", "output"},
    "batch": {"mode"},
    "counter.statistics": {"edge", "line_limit", "max_samples", "sample_point"},
    "detect_abnormal": {"line_limit", "time_range", "value_format"},
    "event.config.list": {"line_limit", "name"},
    "event.config.load": {"config_path"},
    "event.export": {
        "aggregate",
        "events",
        "edge",
        "group_by",
        "line_limit",
        "max_events",
        "max_samples",
        "mode",
        "name",
        "output",
        "rst_n",
        "sample_point",
        "time_range",
    },
    "event.find": {
        "aggregate",
        "events",
        "edge",
        "group_by",
        "line_limit",
        "max_samples",
        "mode",
        "name",
        "rst_n",
        "sample_point",
        "time_range",
    },
    "expr.eval_at": {"edge", "sample_point", "time_range"},
    "expr.normalize": {"line_limit", "no_statement_only", "role", "signal"},
    "handshake.inspect": {"data", "edge", "line_limit", "rules", "sample_point", "time_range"},
    "list.delete": {"index"},
    "list.diff": {"value_format"},
    "list.export": {"line_limit", "output", "time_range"},
    "list.show": {"name"},
    "sampled_pulse.inspect": {
        "edge",
        "line_limit",
        "payloads",
        "rules",
        "sample_point",
        "time_range",
    },
    "scope.list": {"kind", "max_depth", "name_pattern", "recursive"},
    "session.close": set(),
    "session.doctor": set(),
    "session.gc": set(),
    "session.kill": set(),
    "session.list": set(),
    "session.open": {"bind", "bind_host", "host", "port", "session_id", "transport"},
    "signal.changes": {"aggregate_only", "line_limit", "mode", "time_range", "value_format"},
    "signal.stability": {"conditions", "mode", "signals", "time_range"},
    "signal.statistics": {"clock", "conditions", "edge", "line_limit", "max_samples", "mode", "sample_point", "signals", "time_range"},
    "source.context": {"context_lines", "symbol", "output"},
    "stream.config.load": {"config", "config_path", "file", "mode"},
    "stream.config.list": {"name", "output"},
    "stream.export": {"channel", "line_limit", "output", "time_range"},
    "stream.query": {"channel", "field_scope", "line_limit", "match", "packet_index", "time_range"},
    "stream.show": set(),
    "stream.validate": {"channel", "line_limit", "time_range"},
    "trace.active_driver": {
        "limits",
    },
    "trace.active_driver_chain": set(),
    "trace.driver": {"line_limit", "no_statement_only", "role"},
    "trace.load": {"line_limit", "no_statement_only", "role"},
    "value.at": {"edge", "sample_point", "slice_hint", "value_format"},
    "value.batch_at": {"edge", "sample_point", "slice_hint", "value_format"},
    "list.value_at": {"edge", "format", "sample_point", "value_format"},
    "verify.conditions": {"edge", "sample_point", "signals", "value_format"},
    "window.verify": {"edge", "line_limit", "max_samples", "sample_point", "signals", "time_range"},
}


ENGINE_FORWARD_TIME_UNIT_EXCLUDE = {
    "actions",
    "batch",
    "schema",
    "session.close",
    "session.gc",
    "session.kill",
    "session.list",
    "session.open",
}


ARGS_REQUIRED_EXCEPTIONS = {
    "session.close",
    "session.kill",
}


TOP_LEVEL_PROPERTIES: dict[str, dict[str, Any]] = {
    "api_version": {"type": "string", "enum": ["xdebug.v1"]},
    "request_id": {"type": "string"},
    "id": {"type": "string"},
    "trace_id": {"type": "string"},
    "span_id": {"type": "string"},
    "parent_span_id": {"type": "string"},
    "action": {"type": "string"},
    "target": {"type": "object"},
    "args": {"type": "object"},
    "limits": {"type": "object"},
    "auth_token": {"type": "string"},
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def action_specs() -> list[dict[str, Any]]:
    return load_json(SPEC_PATH)["actions"]


def required_related_args(spec: dict[str, Any]) -> set[str]:
    keys = set(spec.get("required_args", []))
    for group in spec.get("required_arg_groups", []):
        keys.update(group)
    for conditional in spec.get("conditional_required_args", []):
        keys.update(conditional.get("when", {}).keys())
        keys.update(conditional.get("required", []))
    return keys


def example_args(action: str) -> set[str]:
    path = REQUEST_EXAMPLES / f"{action}.basic.json"
    if not path.exists():
        return set()
    data = load_json(path)
    args = data.get("args", {})
    return set(args) if isinstance(args, dict) else set()


def collect_arg_schemas(specs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    arg_schemas: dict[str, dict[str, Any]] = {}
    for spec in specs:
        for kind in ("request",):
            path = XDEBUG_ROOT / spec["schemas"][kind]
            if not path.exists():
                continue
            schema = load_json(path)
            props = schema.get("properties", {}).get("args", {}).get("properties", {})
            if isinstance(props, dict):
                for key, value in props.items():
                    if key not in arg_schemas:
                        arg_schemas[key] = copy.deepcopy(value)
    for key, value in ADDITIONAL_ARG_SCHEMAS.items():
        arg_schemas.setdefault(key, copy.deepcopy(value))
    # Keep generic channel open for stream/APB-style uses; action-specific
    # channel enums are applied in sync_schema().
    arg_schemas["channel"] = copy.deepcopy(ADDITIONAL_ARG_SCHEMAS["channel"])
    arg_schemas["match"] = copy.deepcopy(ADDITIONAL_ARG_SCHEMAS["match"])
    arg_schemas["output"] = copy.deepcopy(ADDITIONAL_ARG_SCHEMAS["output"])
    arg_schemas["time_range"] = copy.deepcopy(ADDITIONAL_ARG_SCHEMAS["time_range"])

    arg_schemas["checks"] = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"type": "string", "enum": ["unknown_xz", "glitch", "stuck"]},
                "min_pulse_width": {"type": "string"},
                "min_duration": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "description": "detect_abnormal checks. Each item must be an object with type; string shorthand is not supported.",
    }
    arg_schemas["direction"] = {"type": "string", "enum": ["write", "read", "all"]}
    arg_schemas["format"] = {
        "type": "string",
        "enum": [
            "h",
            "hex",
            "b",
            "bin",
            "binary",
            "d",
            "dec",
            "decimal",
            "array_indexed",
            "json",
            "tsv",
            "csv",
            "u64bin",
        ],
    }
    arg_schemas["kind"] = {"type": "string"}
    arg_schemas["mode"] = {"type": "string"}
    arg_schemas["op"] = {"type": "string", "enum": ["begin", "next", "prev", "pre", "last"]}
    arg_schemas["port"] = {"type": "integer"}
    arg_schemas["query"] = {"oneOf": [{"type": "string"}, {"type": "object"}]}
    arg_schemas["vld"] = {"oneOf": [{"type": "string"}, {"type": "object"}]}
    return arg_schemas


def allowed_args_for_spec(spec: dict[str, Any]) -> set[str]:
    action = spec["name"]
    keys = set(example_args(action))
    keys.update(required_related_args(spec))
    keys.update(EXTRA_ARGS_BY_ACTION.get(action, set()))
    if spec.get("handler_kind") == "engine_forward" and action not in ENGINE_FORWARD_TIME_UNIT_EXCLUDE:
        keys.add("time_unit")
    return keys


def sync_schema(schema: dict[str, Any], spec: dict[str, Any], arg_schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    action = spec["name"]
    updated = copy.deepcopy(schema)
    updated["type"] = "object"
    updated["required"] = ["api_version", "action"]
    if spec.get("required_args") and action not in ARGS_REQUIRED_EXCEPTIONS:
        updated["required"].append("args")

    properties = updated.setdefault("properties", {})
    for key in list(properties):
        if key not in TOP_LEVEL_PROPERTIES:
            del properties[key]
    for key, value in TOP_LEVEL_PROPERTIES.items():
        properties.setdefault(key, copy.deepcopy(value))
    properties["action"] = {"type": "string", "enum": [action]}
    if spec.get("required_target"):
        updated["required"].append("target")
        properties["target"] = {
            "type": "object",
            "required": list(spec["required_target"]),
            "properties": {
                "session_id": {"type": "string", "description": PARAM_DESCRIPTIONS["session_id"]},
            },
            "additionalProperties": False,
        }
    else:
        properties.setdefault("target", copy.deepcopy(TOP_LEVEL_PROPERTIES["target"]))

    args = properties.setdefault("args", {"type": "object"})
    args["type"] = "object"
    args["required"] = list(spec.get("required_args", []))
    selected_props: dict[str, Any] = {}
    for key in sorted(allowed_args_for_spec(spec)):
        if key not in arg_schemas:
            raise ValueError(f"{action}: missing schema template for args.{key}")
        selected_props[key] = copy.deepcopy(arg_schemas[key])
        if key in PARAM_DESCRIPTIONS:
            selected_props[key].setdefault("description", PARAM_DESCRIPTIONS[key])
    if action in ("apb.query", "axi.query") and "query" in selected_props:
        selected_props["query"] = copy.deepcopy(arg_schemas["protocol_query"])
        if "direction" in selected_props:
            selected_props["direction"] = {"type": "string", "enum": ["write", "read"]}
    if action == "axi.analysis" and "analysis" in selected_props:
        selected_props["analysis"] = copy.deepcopy(ADDITIONAL_ARG_SCHEMAS["analysis"])
    if action == "axi.query" and "query" in selected_props:
        selected_props["query"] = {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "line_limit": {"type": "integer", "minimum": 1},
                        "index": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["channel", "handshake_time"],
                    "properties": {
                        "channel": {"type": "string", "enum": ["aw", "w", "b", "ar", "r"]},
                        "handshake_time": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ],
            "description": "Select transactions by 1-based index/line_limit, or exactly match an AXI channel handshake time.",
        }
    if action in {"axi.query", "axi.request_response_pair", "axi.latency_outlier"} and "output" in selected_props:
        selected_props["output"] = {
            "type": "object",
            "properties": {
                "include_data": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
            "description": "AXI payload display controls; beat data is omitted unless include_data is true.",
        }
    if action == "list.export" and "format" in selected_props:
        selected_props["format"] = {
            "type": "string",
            "enum": ["u64bin"],
            "description": "list.export input format. The response manifest uses versioned format u64bin.v1.",
        }
    if action == "list.export" and "output" in selected_props:
        selected_props["output"]["properties"]["file_format"] = {
            "type": "string",
            "enum": ["u64bin"],
            "description": "list.export file format; response manifest uses versioned format u64bin.v1.",
        }
    if action == "axi.export" and "output" in selected_props:
        selected_props["output"]["properties"]["file_format"] = {
            "type": "string",
            "enum": ["tsv", "csv"],
            "description": "axi.export file format.",
        }
    if action == "event.export" and "output" in selected_props:
        selected_props["output"]["properties"]["file_format"] = {
            "type": "string",
            "enum": ["json"],
            "description": "event.export file format.",
        }
    if action == "stream.export":
        if "output" in selected_props:
            selected_props["output"]["properties"]["file_format"] = {
                "type": "string",
                "enum": ["tsv", "csv", "xout"],
                "description": "stream.export file format.",
            }
        if "kind" in selected_props:
            selected_props["kind"] = {
                "type": "string",
                "enum": ["transfer", "packet", "packet_beats"],
                "description": "导出或查询的结果类型。",
            }
    if action == "value.batch_at" and "signals" in selected_props:
        selected_props["signals"] = {
            "type": "array",
            "items": {"type": "string"},
            "description": PARAM_DESCRIPTIONS["signals"],
        }
    if action in {"verify.conditions", "window.verify"} and "conditions" in selected_props:
        selected_props["conditions"] = {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expr"],
                "properties": {
                    "expr": {
                        "type": "string",
                        "description": "Expression using aliases from args.signals.",
                    },
                    "name": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["always", "eventually", "never"],
                    },
                },
                "additionalProperties": False,
            },
            "description": PARAM_DESCRIPTIONS["conditions"],
        }
    if action == "axi.channel_stall" and "channel" in selected_props:
        selected_props["channel"] = {
            "type": "string",
            "enum": ["aw", "w", "b", "ar", "r"],
            "description": "AXI channel to inspect.",
        }
    if action == "scope.list":
        selected_props["kind"] = {
            "type": "string",
            "enum": ["all", "scope", "signal"],
            "description": "只返回 scope、signal，或两者都返回。",
        }
    if action == "handshake.inspect":
        selected_props["rules"] = {
            "type": "object",
            "properties": {
                "max_wait_cycles": {"type": "integer", "minimum": 0},
                "check_data_stable_when_stalled": {"type": "boolean"},
                "require_valid_hold_until_handshake": {"type": "boolean", "default": True},
                "ready_without_valid": {
                    "type": "string",
                    "enum": ["summary", "intervals", "all"],
                    "default": "summary",
                },
            },
            "additionalProperties": False,
        }
    if action == "sampled_pulse.inspect":
        selected_props["rules"] = {
            "type": "object",
            "properties": {
                "payload_changed_without_sampled_valid": {
                    "type": "string",
                    "enum": ["off", "summary", "all"],
                    "default": "summary",
                }
            },
            "additionalProperties": False,
        }
    if action == "event.find":
        selected_props["mode"] = {
            "type": "string",
            "enum": ["first", "last", "all"],
            "default": "first",
        }
    if action == "event.export":
        selected_props["mode"] = {"type": "string", "enum": ["export"], "default": "export"}
    args["properties"] = selected_props
    args["additionalProperties"] = False
    groups = spec.get("required_arg_groups", [])
    if groups:
        args["anyOf"] = [{"required": list(group)} for group in groups]
    else:
        args.pop("anyOf", None)
    conditionals = spec.get("conditional_required_args", [])
    if conditionals:
        args["allOf"] = [
            {
                "if": {"properties": {key: {"const": value} for key, value in conditional.get("when", {}).items()}},
                "then": {"required": list(conditional.get("required", []))},
            }
            for conditional in conditionals
        ]
    else:
        args.pop("allOf", None)
    if action == "axi.query":
        query_constraints = [
            {
                "if": {
                    "required": ["query"],
                    "properties": {"query": {"required": ["channel"]}},
                },
                "then": {
                    "not": {
                        "anyOf": [
                            {"required": [key]}
                            for key in ("direction", "address", "addr", "id", "last")
                        ]
                    }
                },
            },
            {"not": {"required": ["address", "addr"]}},
        ]
        args["allOf"] = list(args.get("allOf", [])) + query_constraints
    if action == "event.find":
        args["allOf"] = list(args.get("allOf", [])) + [
            {
                "anyOf": [
                    {"required": ["mode"], "properties": {"mode": {"const": "all"}}},
                    {"not": {"required": ["line_limit"]}},
                ]
            }
        ]
    if action == "event.config.list":
        args["allOf"] = list(args.get("allOf", [])) + [
            {"not": {"required": ["name", "line_limit"]}}
        ]
    if action == "expr.normalize":
        args["allOf"] = list(args.get("allOf", [])) + [
            {"anyOf": [{"required": ["signal"]}, {"not": {"required": ["line_limit"]}}]}
        ]
    if action in {"list.export", "stream.export"}:
        args["allOf"] = list(args.get("allOf", [])) + [
            {
                "if": {
                    "required": ["output"],
                    "properties": {
                        "output": {
                            "required": ["path"],
                            "properties": {"path": {"type": "string", "minLength": 1}},
                        }
                    },
                },
                "then": {"not": {"required": ["line_limit"]}},
            }
        ]
    if action == "axi.analysis":
        args["allOf"] = list(args.get("allOf", [])) + [
            {
                "anyOf": [
                    {"required": ["analysis"], "properties": {"analysis": {"const": "pending"}}},
                    {"not": {"required": ["line_limit"]}},
                ]
            }
        ]
    updated.pop("anyOf", None)
    updated.pop("allOf", None)
    updated.pop("oneOf", None)
    updated["additionalProperties"] = False
    return updated


def sync(check: bool, selected_actions: set[str] | None = None) -> list[str]:
    specs = [spec for spec in action_specs() if spec.get("status") != "removed"]
    arg_schemas = collect_arg_schemas(specs)
    errors: list[str] = []

    for spec in specs:
        if selected_actions and spec["name"] not in selected_actions:
            continue
        path = XDEBUG_ROOT / spec["schemas"]["request"]
        schema = load_json(path)
        try:
            updated = sync_schema(schema, spec, arg_schemas)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if schema != updated:
            if check:
                errors.append(f"{spec['schemas']['request']}: runtime request schema is not synced")
            else:
                path.write_text(dump_json(updated), encoding="utf-8")
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only check, do not update files")
    parser.add_argument("--action", action="append", default=[], help="sync only the named action; repeatable")
    args = parser.parse_args(argv)

    errors = sync(check=args.check, selected_actions=set(args.action) or None)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("runtime request schemas are synced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
