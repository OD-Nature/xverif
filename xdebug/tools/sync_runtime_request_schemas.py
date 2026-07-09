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
    "analysis": {"type": "string", "enum": ["latency", "osd", "outstanding"]},
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
    "last": {"type": "boolean"},
    "line_limit": {"type": "integer", "minimum": 1},
    "limits": {"type": "object"},
    "protocol_query": {
        "type": "object",
        "properties": {
            "line_limit": {"type": "integer", "minimum": 1},
            "index": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
        "description": "Protocol query controls; use 1-based query.index and query.line_limit; legacy args.num, args.limit, and query.limit are rejected.",
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
    "max_rows": {"type": "integer"},
    "no_statement_only": {"type": "boolean"},
    "note": {"type": "string"},
    "origin": {"type": "string"},
    "output": {
        "type": "object",
        "required": ["path"],
        "properties": {"path": {"type": "string"}},
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
    "time_unit": {"type": "string", "enum": ["auto", "fs", "ps", "ns", "us", "ms", "s"]},
    "transport": {"type": "string", "enum": ["uds", "tcp", "file"]},
    "verbose": {"type": "boolean"},
}


EXTRA_ARGS_BY_ACTION: dict[str, set[str]] = {
    "apb.cursor": {"direction"},
    "apb.config.load": {"config", "config_path"},
    "apb.query": {"direction", "address", "addr", "query", "last"},
    "apb.transfer_window": {"line_limit", "time_range"},
    "axi.analysis": {"analysis", "direction"},
    "axi.channel_stall": {"channel", "line_limit", "rules", "time_range"},
    "axi.config.load": {"config", "config_path"},
    "axi.cursor": {"direction"},
    "axi.export": {"format", "output", "time_range"},
    "axi.latency_outlier": {"line_limit", "time_range"},
    "axi.outstanding_timeline": {"line_limit", "time_range"},
    "axi.query": {"direction", "address", "addr", "query", "last"},
    "axi.request_response_pair": {"line_limit", "time_range"},
    "batch": {"mode"},
    "counter.statistics": {"edge", "line_limit", "sample_point"},
    "detect_abnormal": {"line_limit", "time_range"},
    "event.config.list": {"line_limit", "name"},
    "event.config.load": {"config_path"},
    "event.export": {
        "aggregate",
        "events",
        "edge",
        "group_by",
        "line_limit",
        "mode",
        "name",
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
        "mode",
        "name",
        "rst_n",
        "sample_point",
        "time_range",
    },
    "expr.eval_at": {"edge", "line_limit", "sample_point", "time_range"},
    "expr.normalize": {"include_statement_only", "line_limit", "no_statement_only", "role", "signal"},
    "handshake.inspect": {"data", "edge", "line_limit", "rules", "sample_point", "time_range"},
    "list.delete": {"index"},
    "list.export": {"line_limit", "output", "time_range"},
    "list.show": {"name"},
    "sampled_pulse.inspect": {
        "edge",
        "line_limit",
        "payloads",
        "sample_point",
        "time_range",
    },
    "scope.list": {"max_depth", "recursive"},
    "session.close": set(),
    "session.doctor": set(),
    "session.gc": set(),
    "session.kill": set(),
    "session.list": set(),
    "session.open": {"bind", "bind_host", "host", "port", "session_id", "transport"},
    "signal.changes": {"aggregate_only", "line_limit", "mode", "time_range"},
    "signal.stability": {"conditions", "line_limit", "mode", "signals", "time_range"},
    "signal.statistics": {"clock", "conditions", "edge", "line_limit", "mode", "sample_point", "signals", "time_range"},
    "source.context": {"context_lines", "symbol"},
    "stream.config.load": {"config", "config_path", "file", "mode"},
    "stream.export": {"channel", "line_limit", "output", "time_range"},
    "stream.query": {"channel", "field_scope", "line_limit", "match", "packet_index", "time_range"},
    "stream.show": set(),
    "stream.validate": {"channel", "line_limit", "time_range"},
    "trace.active_driver": {
        "include_alias_candidates",
        "include_compat_fields",
        "include_control",
        "include_parity",
        "limits",
    },
    "trace.active_driver_chain": set(),
    "trace.driver": {"include_statement_only", "line_limit", "no_statement_only", "role"},
    "trace.load": {"include_statement_only", "line_limit", "no_statement_only", "role"},
    "value.at": {"edge", "sample_point", "slice_hint"},
    "value.batch_at": {"edge", "sample_point", "slice_hint"},
    "list.value_at": {"edge", "format", "sample_point"},
    "verify.conditions": {"edge", "sample_point"},
    "window.verify": {"edge", "line_limit", "sample_point", "time_range"},
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
    "output": {"type": "object"},
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
    if action == "list.export" and "format" in selected_props:
        selected_props["format"] = {
            "type": "string",
            "enum": ["u64bin"],
            "description": "list.export input format. The response manifest uses versioned format u64bin.v1.",
        }
    if action == "stream.export":
        if "format" in selected_props:
            selected_props["format"] = {
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
    if action == "axi.channel_stall" and "channel" in selected_props:
        selected_props["channel"] = {
            "type": "string",
            "enum": ["aw", "w", "b", "ar", "r"],
            "description": "AXI channel to inspect.",
        }
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
    updated.pop("anyOf", None)
    updated.pop("allOf", None)
    updated.pop("oneOf", None)
    updated["additionalProperties"] = False
    return updated


def sync(check: bool) -> list[str]:
    specs = [spec for spec in action_specs() if spec.get("status") != "removed"]
    arg_schemas = collect_arg_schemas(specs)
    errors: list[str] = []

    for spec in specs:
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
    args = parser.parse_args(argv)

    errors = sync(check=args.check)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("runtime request schemas are synced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
