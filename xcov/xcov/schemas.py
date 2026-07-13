from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

Json = Dict[str, Any]

METRICS = ["line", "toggle", "branch", "condition", "fsm", "assert", "functional"]
FUNCTIONAL_LEVELS = ["covergroup", "coverpoint", "cross", "bin"]
OVERFLOW = ["truncate", "error", "to_file", "summary_only"]
OUTPUT_MODES = ["inline", "file", "both", "summary_only"]
ARTIFACT_FORMATS = ["json", "ndjson", "csv", "md"]
RESPONSE_FORMATS = ["xout", "json"]


def _string() -> Json:
    return {"type": "string"}


def _bool() -> Json:
    return {"type": "boolean"}


def _integer(minimum: int | None = None) -> Json:
    out: Json = {"type": "integer"}
    if minimum is not None:
        out["minimum"] = minimum
    return out


def _number(minimum: float | None = None) -> Json:
    out: Json = {"type": "number"}
    if minimum is not None:
        out["minimum"] = minimum
    return out


def _string_array(values: List[str] | None = None) -> Json:
    items: Json = {"type": "string"}
    if values:
        items["enum"] = values
    return {"type": "array", "items": items}


def _query() -> Json:
    return {
        "type": "object",
        "properties": {
            "include_patterns": _string_array(),
            "exclude_patterns": _string_array(),
            "match_field": _string(),
            "pattern_mode": {"const": "glob"},
            "case_sensitive": _bool(),
        },
        "additionalProperties": True,
    }


def _sort() -> Json:
    return {
        "type": "object",
        "properties": {
            "by": _string(),
            "order": {"enum": ["asc", "desc"]},
            "metric": _string(),
        },
        "additionalProperties": True,
    }


def _limits() -> Json:
    return {
        "type": "object",
        "properties": {
            "max_items": {"anyOf": [_integer(0), {"type": "null"}]},
            "overflow": {"enum": OVERFLOW},
        },
        "additionalProperties": True,
    }


def _output() -> Json:
    return {
        "type": "object",
        "properties": {
            "response_format": {"enum": RESPONSE_FORMATS},
            "mode": {"enum": OUTPUT_MODES},
            "artifact_format": {"enum": ARTIFACT_FORMATS},
            "path": {"anyOf": [_string(), {"type": "null"}]},
            "allow_absolute_path": _bool(),
        },
        "additionalProperties": True,
    }


def _markdown_export_output() -> Json:
    return {
        "type": "object",
        "properties": {
            "response_format": {"enum": RESPONSE_FORMATS},
            "path": {"anyOf": [_string(), {"type": "null"}]},
            "allow_absolute_path": _bool(),
        },
        "additionalProperties": True,
    }


COMMON_ARG_PROPS: Json = {
    "query": _query(),
    "limits": _limits(),
    "output": _output(),
    "sort": _sort(),
    "metrics": _string_array(METRICS),
    "scope": _string(),
    "test": _string(),
}


def _target(required: List[str] | None = None, props: Json | None = None) -> Json:
    properties = {"session_id": _string(), "vdb": _string()}
    if props:
        properties.update(props)
    out: Json = {"type": "object", "properties": properties, "additionalProperties": True}
    if required:
        out["required"] = required
    return out


def _args(required: List[str] | None = None, props: Json | None = None) -> Json:
    properties = deepcopy(COMMON_ARG_PROPS)
    if props:
        properties.update(props)
    out: Json = {"type": "object", "properties": properties, "additionalProperties": True}
    if required:
        out["required"] = required
    return out


def _request(action: str, target: Json | None = None, args: Json | None = None) -> Json:
    return {
        "type": "object",
        "required": ["api_version", "action"],
        "properties": {
            "api_version": {"const": "xcov.v1"},
            "request_id": _string(),
            "action": {"const": action},
            "target": target or _target(),
            "args": args or _args(),
            "limits": _limits(),
            "output": _output(),
        },
        "additionalProperties": True,
    }


def _response(action: str) -> Json:
    return {
        "type": "object",
        "required": ["ok", "api_version", "action", "summary", "data"],
        "properties": {
            "ok": _bool(),
            "api_version": {"const": "xcov.v1"},
            "request_id": _string(),
            "action": {"const": action},
            "summary": {"type": "object", "additionalProperties": True},
            "data": {"type": "object", "additionalProperties": True},
            "warnings": {"type": "array", "items": _string()},
            "error": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }


def _schema_entry(action: str, target: Json | None = None, args: Json | None = None) -> Json:
    return {"request": _request(action, target, args), "response": _response(action)}


SCHEMAS: Dict[str, Json] = {
    "actions": _schema_entry("actions"),
    "schema": _schema_entry("schema", args=_args(["action"], {"action": _string(), "kind": {"enum": ["request", "response"]}})),
    "session.open": _schema_entry(
        "session.open",
        target=_target(["vdb"], {"run_manifest": _string()}),
        args=_args(None, {"name": _string(), "fake": _bool(), "reuse": _bool(), "reopen": _bool()}),
    ),
    "session.status": _schema_entry("session.status", target=_target(["session_id"])),
    "session.close": _schema_entry("session.close", target=_target(["session_id"])),
    "tests.list": _schema_entry("tests.list", target=_target(["session_id"])),
    "metrics.list": _schema_entry("metrics.list", target=_target(["session_id"])),
    "scope.summary": _schema_entry("scope.summary", target=_target(["session_id"])),
    "scope.children": _schema_entry("scope.children", target=_target(["session_id"]), args=_args(None, {"recursive": _bool()})),
    "scope.search": _schema_entry("scope.search", target=_target(["session_id"])),
    "code_coverage.summary": _schema_entry(
        "code_coverage.summary",
        target=_target(["session_id"]),
        args=_args(None, {"group_by": _string()}),
    ),
    "code_coverage.holes": _schema_entry("code_coverage.holes", target=_target(["session_id"])),
    "function_coverage.summary": _schema_entry(
        "function_coverage.summary",
        target=_target(["session_id"]),
        args=_args(None, {"group_by": _string(), "levels": _string_array(FUNCTIONAL_LEVELS)}),
    ),
    "function_coverage.holes": _schema_entry(
        "function_coverage.holes",
        target=_target(["session_id"]),
        args=_args(None, {"levels": _string_array(FUNCTIONAL_LEVELS)}),
    ),
    "source.map": _schema_entry(
        "source.map",
        target=_target(["session_id"]),
        args=_args(["file", "line"], {"file": _string(), "line": _integer(0), "window": _integer(0)}),
    ),
    "source.annotate": _schema_entry(
        "source.annotate",
        target=_target(["session_id"]),
        args=_args(
            ["file", "line"],
            {
                "file": _string(),
                "line": _integer(0),
                "window": _integer(0),
                "include_source_text": _bool(),
                "include_covered": _bool(),
            },
        ),
    ),
    "assert.summary": _schema_entry(
        "assert.summary",
        target=_target(["session_id"]),
        args=_args(None, {"include_instances": _bool(), "include_source": _bool()}),
    ),
    "export.code_coverage": _schema_entry(
        "export.code_coverage",
        target=_target(["session_id"]),
        args=_args(None, {"threshold_pct": _number(0.0), "output": _markdown_export_output()}),
    ),
    "export.function_coverage": _schema_entry(
        "export.function_coverage",
        target=_target(["session_id"]),
        args=_args(None, {
            "covergroup": _string(),
            "threshold_pct": _number(0.0),
            "output": _markdown_export_output(),
        }),
    ),
    "export.assert": _schema_entry(
        "export.assert",
        target=_target(["session_id"]),
        args=_args(None, {"threshold_pct": _number(0.0), "output": _markdown_export_output()}),
    ),
}


def schema_for_action(action: str, kind: str = "request") -> Json:
    entry = SCHEMAS.get(action)
    if not entry:
        raise KeyError(action)
    if kind not in ("request", "response"):
        raise KeyError(kind)
    return deepcopy(entry[kind])


def schema_actions() -> List[str]:
    return sorted(SCHEMAS)
