"""Stateless xloc adapter - UVM log location resolver."""
from __future__ import annotations

from typing import Any, Optional, Set

from xverif_mcp.errors import error_payload
from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()

from xloc.mapfile import find_map_file, iter_loc_ids, load_map
from xloc.resolver import context_payload, render_payload, resolve_payload
from xloc.stats import render_stats, stats_payload


def _error(action: str, exc: Exception) -> dict:
    return error_payload("XLOC_ERROR", str(exc), action=action)


def _annotate_text(log_path: str, map_path: Optional[str] = None) -> str:
    if map_path is None:
        map_path = find_map_file(log_path)
    entries = load_map(map_path) if map_path else {}
    seen: Set[str] = set()
    lines: list[str] = []
    with open(log_path, "r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            for loc_id in iter_loc_ids(line):
                if loc_id in seen:
                    continue
                seen.add(loc_id)
                entry = entries.get(loc_id, {})
                filepath = entry.get("file", "?")
                line_num = entry.get("line", "?")
                lines.append(f"[loc] {loc_id} -> {filepath}:{line_num}\n")
            lines.append(line)
    return "".join(lines)


def loc_resolve(loc_id: str, map_path: str,
                output_format: str = "json") -> Any:
    """Resolve a loc_id (L_XXXXXXXX) to source file:line."""
    try:
        payload = resolve_payload(loc_id, map_path)
    except Exception as exc:
        payload = _error("resolve", exc)
    if output_format == "json":
        return payload
    return render_payload(payload)


def loc_context(loc_id: str, map_path: str, before: int = 20,
                after: int = 20, output_format: str = "xout") -> Any:
    """Resolve a loc_id and show surrounding source lines."""
    try:
        payload = context_payload(loc_id, map_path, before, after)
    except Exception as exc:
        payload = _error("context", exc)
    if output_format == "json":
        return payload
    return render_payload(payload)


def loc_stats(log_path: str, map_path: Optional[str] = None,
              top: int = 20, output_format: str = "json") -> Any:
    """Count loc_id frequency in a simulation log."""
    try:
        payload = stats_payload(log_path, map_path, top)
    except Exception as exc:
        payload = _error("stats", exc)
    if output_format == "json":
        return payload
    return render_stats(payload)


def loc_annotate(log_path: str, map_path: Optional[str] = None,
                 output_format: str = "xout") -> Any:
    """Insert location hints into a simulation log."""
    del output_format
    try:
        return _annotate_text(log_path, map_path)
    except Exception as exc:
        return _error("annotate", exc)
