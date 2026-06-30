from __future__ import annotations

import csv
import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .errors import XcovError

Json = Dict[str, Any]

DEFAULT_LIMITS = {
    "tests.list": 1000,
    "metrics.list": None,
    "scope.children": 100,
    "scope.search": 100,
    "scope.summary": 100,
    "code_coverage.summary": 100,
    "code_coverage.holes": 100,
    "function_coverage.summary": 100,
    "function_coverage.holes": 100,
    "source.map": 100,
    "source.annotate": 100,
    "assert.summary": 100,
}

REGEX_HINT_CHARS = ("[", "]", "{", "}", "^", "$", "(", ")", "|", "+")


def query_args(args: Json) -> Json:
    query = dict(args.get("query") or {})
    query.setdefault("include_patterns", [])
    query.setdefault("exclude_patterns", [])
    query.setdefault("match_field", "full_name")
    query.setdefault("pattern_mode", "glob")
    query.setdefault("case_sensitive", True)
    if query.get("pattern_mode") != "glob":
        raise XcovError("REGEX_NOT_SUPPORTED", "only glob wildcard patterns are supported",
                        pattern_mode=query.get("pattern_mode"))
    for pat in list(query["include_patterns"]) + list(query["exclude_patterns"]):
        if any(ch in str(pat) for ch in REGEX_HINT_CHARS):
            raise XcovError("REGEX_NOT_SUPPORTED", "only glob wildcard patterns are supported",
                            pattern=pat, supported="*,?")
    mf = query.get("match_field")
    if not isinstance(mf, str) or not mf:
        raise XcovError("INVALID_QUERY_FIELD",
                        "match_field must be a single non-empty string, e.g. 'full_name' or 'name'",
                        match_field=mf)
    return query


def filters_summary(query: Json) -> Json:
    return {
        "include": query.get("include_patterns") or [],
        "exclude": query.get("exclude_patterns") or [],
        "match_field": query.get("match_field") or "full_name",
    }


def _field_value(item: Json, field: str) -> str | None:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    if field == "file":
        value = evidence.get("file") or item.get("file")
    else:
        value = item.get(field)
    return str(value) if value is not None else None


def filter_items(items: Iterable[Json], query: Json) -> List[Json]:
    include = [str(p) for p in (query.get("include_patterns") or [])]
    exclude = [str(p) for p in (query.get("exclude_patterns") or [])]
    field = str(query.get("match_field") or "full_name")
    case_sensitive = bool(query.get("case_sensitive", True))

    def norm(s: str) -> str:
        return s if case_sensitive else s.lower()

    def match_any(patterns: List[str], value: str) -> bool:
        if not patterns:
            return False
        nval = norm(value) if value else ""
        for pat in patterns:
            if fnmatch.fnmatchcase(nval, norm(pat)):
                return True
        return False

    rows: List[Json] = []
    for item in items:
        value = _field_value(item, field)
        if value is None:
            continue
        if include and not match_any(include, value):
            continue
        if exclude and match_any(exclude, value):
            continue
        rows.append(item)
    return rows


def sort_items(items: List[Json], sort: Json | None) -> List[Json]:
    if not sort:
        return items
    key = str(sort.get("by") or "name")
    reverse = str(sort.get("order") or "asc") == "desc"

    def item_key(item: Json):
        value = item.get(key)
        if value is None and key in ("file", "line"):
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            value = evidence.get(key)
        return (value is None, value)

    return sorted(items, key=item_key, reverse=reverse)


def limit_args(action: str, args: Json) -> Json:
    default = DEFAULT_LIMITS.get(action, 100)
    limits = dict(args.get("limits") or {})
    if "max_items" not in limits:
        limits["max_items"] = default
    limits.setdefault("overflow", "truncate")
    max_items = limits.get("max_items")
    if max_items is not None and (not isinstance(max_items, int) or max_items < 0):
        raise XcovError("INVALID_LIMIT", "limits.max_items must be a non-negative integer")
    if limits["overflow"] not in ("truncate", "error", "to_file", "summary_only"):
        raise XcovError("INVALID_LIMIT", "unsupported limits.overflow",
                        overflow=limits["overflow"])
    return limits


def output_args(args: Json, default_mode: str = "inline") -> Json:
    output = dict(args.get("output") or {})
    output.setdefault("response_format", "xout")
    output.setdefault("mode", default_mode)
    output.setdefault("artifact_format", "json")
    output.setdefault("path", None)
    output.setdefault("allow_absolute_path", False)
    if output["mode"] not in ("inline", "file", "both", "summary_only"):
        raise XcovError("SCHEMA_INVALID", "unsupported output.mode", mode=output["mode"])
    if output["artifact_format"] not in ("json", "ndjson", "csv", "md"):
        raise XcovError("EXPORT_FORMAT_UNSUPPORTED", "unsupported artifact format",
                        artifact_format=output["artifact_format"])
    return output


def resolve_artifact_path(path: str, allow_absolute_path: bool = False) -> str:
    raw = Path(path)
    if raw.is_absolute():
        if not allow_absolute_path:
            raise XcovError("OUTPUT_PATH_UNSAFE",
                            "absolute output.path requires output.allow_absolute_path=true",
                            path=path)
        return str(raw)
    if any(part == ".." for part in raw.parts):
        raise XcovError("OUTPUT_PATH_UNSAFE", "output.path must not contain '..'",
                        path=path)
    return str(Path(".xverif") / "xcov_exports" / raw)


def write_artifact(path: str, fmt: str, items: List[Json],
                   allow_absolute_path: bool = False) -> str:
    resolved = resolve_artifact_path(path, allow_absolute_path=allow_absolute_path)
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        if fmt == "json":
            with open(resolved, "w", encoding="utf-8") as fh:
                json.dump(items, fh, ensure_ascii=False, indent=2, sort_keys=True)
        elif fmt == "ndjson":
            with open(resolved, "w", encoding="utf-8") as fh:
                for item in items:
                    fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        elif fmt == "csv":
            keys = sorted({k for item in items for k in item if k != "evidence"})
            keys += ["file", "line"]
            with open(resolved, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=keys)
                writer.writeheader()
                for item in items:
                    row = {k: item.get(k) for k in keys}
                    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
                    row["file"] = evidence.get("file")
                    row["line"] = evidence.get("line")
                    writer.writerow(row)
        elif fmt == "md":
            with open(resolved, "w", encoding="utf-8") as fh:
                fh.write("| metric | type | full_name | covered | coverable | file | line |\n")
                fh.write("|---|---|---|---:|---:|---|---:|\n")
                for item in items:
                    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
                    fh.write(
                        f"| {item.get('metric','')} | {item.get('type','')} | "
                        f"{item.get('full_name','')} | {item.get('covered','')} | "
                        f"{item.get('coverable','')} | {evidence.get('file','')} | "
                        f"{evidence.get('line','')} |\n"
                    )
    except OSError as exc:
        raise XcovError("OUTPUT_WRITE_FAILED", str(exc), path=resolved) from exc
    return resolved


def apply_output(action: str, args: Json, items: List[Json],
                 default_mode: str = "inline") -> Tuple[Json, List[Json], List[str]]:
    limits = limit_args(action, args)
    output = output_args(args, default_mode)
    matched = len(items)
    max_items = limits.get("max_items")
    overflow = limits.get("overflow")
    mode = output.get("mode")
    warnings: List[str] = []
    note = None
    output_path = output.get("path")
    should_write = mode == "file" or mode == "both" or overflow == "to_file"
    truncated = bool(max_items is not None and matched > max_items)
    if overflow == "error" and truncated:
        raise XcovError("INVALID_LIMIT", "result exceeds limits.max_items",
                        matched_count=matched, max_items=max_items)
    if should_write:
        if not output_path:
            raise XcovError("OUTPUT_PATH_REQUIRED", "output.path is required")
        output_path = write_artifact(str(output_path), str(output["artifact_format"]), items,
                                     allow_absolute_path=bool(output.get("allow_absolute_path")))
        note = f"full result written to {output_path}"
    if mode in ("file", "summary_only") or overflow == "summary_only":
        inline: List[Json] = []
    elif max_items is None:
        inline = items
    else:
        inline = items[:max_items]
    summary = {
        "matched_count": matched,
        "returned": len(inline),
        "truncated": truncated,
        "output_mode": mode,
        "output_path": output_path,
        "artifact_format": output.get("artifact_format"),
    }
    if note:
        summary["note"] = note
    return summary, inline, warnings


def coverage_pct(covered: Any, coverable: Any) -> float | None:
    try:
        c = float(covered)
        t = float(coverable)
    except Exception:
        return None
    if t == 0:
        return None
    return round(c / t * 100.0, 4)
