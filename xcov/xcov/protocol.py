from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from .errors import XcovError

Json = Dict[str, Any]

API_VERSION = "xcov.v1"


def parse_request(text: str) -> Json:
    try:
        req = json.loads(text)
    except Exception as exc:
        raise XcovError("INVALID_JSON", str(exc)) from exc
    if not isinstance(req, dict):
        raise XcovError("SCHEMA_INVALID", "request must be a JSON object")
    if req.get("api_version") != API_VERSION:
        raise XcovError("API_VERSION_UNSUPPORTED", "api_version must be xcov.v1")
    action = req.get("action")
    if not isinstance(action, str) or not action:
        raise XcovError("SCHEMA_INVALID", "action is required")
    target = req.setdefault("target", {})
    if not isinstance(target, dict):
        raise XcovError("SCHEMA_INVALID", "target must be an object")
    args = req.setdefault("args", {})
    if not isinstance(args, dict):
        raise XcovError("SCHEMA_INVALID", "args must be an object")
    req.setdefault("request_id", "req-unknown")
    return req


def response_format(req: Json) -> str:
    out = req.get("output")
    if isinstance(out, dict):
        return str(out.get("response_format") or "xout")
    args = req.get("args", {})
    if isinstance(args, dict):
        output = args.get("output", {})
        if isinstance(output, dict):
            return str(output.get("response_format") or "xout")
    return "xout"


def ok_response(req: Json, summary: Optional[Json] = None, data: Optional[Json] = None,
                warnings: Optional[List[str]] = None) -> Json:
    s = dict(summary or {})
    s.setdefault("matched_count", 0)
    s.setdefault("returned", 0)
    s.setdefault("truncated", False)
    s.setdefault("output_path", None)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "request_id": req.get("request_id", "req-unknown"),
        "action": req.get("action", ""),
        "summary": s,
        "data": data or {},
        "warnings": warnings or [],
    }


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_scalar(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _flatten_item(item: Json) -> Json:
    flat: Json = {}
    evidence = item.get("evidence")
    for key, value in item.items():
        if key == "evidence" and isinstance(evidence, dict):
            if evidence.get("file") is not None:
                flat["file"] = evidence.get("file")
            if evidence.get("line") is not None:
                flat["line"] = evidence.get("line")
            continue
        if key == "evidence_source" and isinstance(value, dict):
            for src_key, src_value in value.items():
                flat[f"evidence_source.{src_key}"] = src_value
            continue
        if key == "branch_mask" and isinstance(value, dict):
            for mk, mv in value.items():
                flat[f"branch_mask.{mk}"] = mv
            continue
        if key in ("toggle_0_to_1", "toggle_1_to_0") and isinstance(value, dict):
            for tk, tv in value.items():
                flat[f"{key}.{tk}"] = tv
            continue
        if key in ("annotations", "bits") and isinstance(value, list):
            flat[f"{key}_count"] = len(value)
            continue
        flat[key] = value
    return flat


def _keyvals(item: Json) -> str:
    return " ".join(f"{key}={_scalar(value)}" for key, value in _flatten_item(item).items())


def _table_columns(rows: List[Json]) -> List[str]:
    columns: List[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def _render_table(items: Iterable[Json], indent: str) -> List[str]:
    rows = [_flatten_item(item) for item in items]
    if not rows:
        return []
    columns = _table_columns(rows)
    values = [{key: _scalar(row.get(key)) for key in columns} for row in rows]
    widths = {
        key: max(len(key), *(len(row[key]) for row in values))
        for key in columns
    }

    def line(row: Dict[str, str] | None = None) -> str:
        cells = []
        for key in columns:
            text = key if row is None else row[key]
            cells.append(text.ljust(widths[key]))
        return indent + "  ".join(cells).rstrip()

    return [line(None), *(line(row) for row in values)]


def _project_rows(items: Iterable[Json], columns: List[str]) -> List[Json]:
    rows: List[Json] = []
    for item in items:
        rows.append({key: item.get(key) for key in columns})
    return rows


SCOPE_SUMMARY_ITEM_COLUMNS = ["name", "full_name", "covered", "coverable", "missing", "coverage_pct"]
SCOPE_CHILDREN_ITEM_COLUMNS = ["name", "full_name", "coverage_pct"]
SCOPE_METRIC_PCT_FIELDS = [
    ("line", "line_pct"),
    ("toggle", "toggle_pct"),
    ("branch", "branch_pct"),
    ("condition", "condition_pct"),
    ("fsm", "fsm_pct"),
    ("assert", "assert_pct"),
    ("functional", "functional_pct"),
]


def _render_scope_summary(items: List[Json]) -> List[str]:
    lines = ["", "items:"]
    lines.extend(_render_table(_project_rows(items, SCOPE_SUMMARY_ITEM_COLUMNS), "  "))
    coverage_rows: List[Json] = []
    include_scope = len(items) > 1
    for item in items:
        for metric, field in SCOPE_METRIC_PCT_FIELDS:
            pct = item.get(field)
            if pct is None:
                continue
            row: Json = {"metric": metric, "coverage_pct": pct}
            if include_scope:
                row = {"full_name": item.get("full_name"), **row}
            coverage_rows.append(row)
    if coverage_rows:
        lines.extend(["", "coverage:"])
        lines.extend(_render_table(coverage_rows, "  "))
    return lines


def _render_scope_children(items: List[Json]) -> List[str]:
    return ["", "items:", *_render_table(_project_rows(items, SCOPE_CHILDREN_ITEM_COLUMNS), "  ")]


def render_xout(rsp: Json) -> str:
    rid = rsp.get("request_id", "req-unknown")
    action = rsp.get("action", "")
    status = "ok" if rsp.get("ok") else "error"
    lines = [
        f"XOUT_BEGIN request_id={rid} action={action}",
        f"@xcov.v1 {status} action={action} request_id={rid}",
        "",
    ]
    if rsp.get("ok"):
        lines.append("summary:")
        for key, value in rsp.get("summary", {}).items():
            lines.append(f"  {key}: {_scalar(value)}")
        data = rsp.get("data", {})
        filters = data.get("filters") if isinstance(data, dict) else None
        if isinstance(filters, dict):
            lines.extend(["", "filters:"])
            for key, value in filters.items():
                lines.append(f"  {key}: {_scalar(value)}")
        sections = data.get("sections") if isinstance(data, dict) else None
        if isinstance(sections, dict):
            lines.extend(["", "sections:"])
            for key, value in sections.items():
                if isinstance(value, list):
                    lines.append(f"  {key}:")
                    if all(isinstance(item, dict) for item in value):
                        lines.extend(_render_table(value, "    "))
                    else:
                        for item in value:
                            lines.append(f"    - {_scalar(item)}")
                elif isinstance(value, dict):
                    lines.append(f"  {key}: {_keyvals(value)}")
                else:
                    lines.append(f"  {key}: {_scalar(value)}")
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list):
            if action == "scope.summary" and all(isinstance(item, dict) for item in items):
                lines.extend(_render_scope_summary(items))
            elif action == "scope.children" and all(isinstance(item, dict) for item in items):
                lines.extend(_render_scope_children(items))
            else:
                lines.extend(["", "items:"])
                if all(isinstance(item, dict) for item in items):
                    lines.extend(_render_table(items, "  "))
                else:
                    for item in items:
                        lines.append(f"  - {_scalar(item)}")
    else:
        lines.append("error:")
        for key, value in rsp.get("error", {}).items():
            lines.append(f"  {key}: {_scalar(value)}")
    warnings = rsp.get("warnings") or []
    if warnings:
        lines.extend(["", "warnings:"])
        for warning in warnings:
            lines.append(f"  - {_scalar(warning)}")
    lines.extend(["", f"XOUT_END request_id={rid}"])
    return "\n".join(lines) + "\n"


def json_dumps(obj: Json) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
