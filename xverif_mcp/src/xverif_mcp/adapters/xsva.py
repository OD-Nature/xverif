"""Stateless xsva adapter - SVA semantic analysis."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from xverif_mcp.errors import error_payload
from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()

from xsva.cli import (_serialize_sequence_ir, _serialize_surface_ir,
                      _serialize_timeline_ir)
from xsva.explain.markdown import render_timeline_markdown
from xsva.explain.text import render_timeline_text
from xsva.ir.diagnostics import DiagnosticBag
from xsva.lower.sequence_to_timeline import lower_sequence_to_timeline
from xsva.lower.surface_to_sequence import lower_surface_to_sequence
from xsva.parser.property_parser import PropertyParser
from xsva.parser.scanner import Scanner


def _read_file(file: str) -> str:
    return Path(file).read_text(encoding="utf-8")


def _parser(file: str) -> PropertyParser:
    text = _read_file(file)
    return PropertyParser(Scanner(text, file=file), DiagnosticBag())


def _surface(file: str, property: str):
    parser = _parser(file)
    for ir in parser.parse_file():
        if ir.name == property:
            return ir
    raise ValueError(f"property not found: {property}")


def _timeline(file: str, property: str):
    diag = DiagnosticBag()
    text = _read_file(file)
    parser = PropertyParser(Scanner(text, file=file), diag)
    for surface in parser.parse_file():
        if surface.name == property:
            seq = lower_surface_to_sequence(surface, diag)
            timeline = lower_sequence_to_timeline(seq, surface_ir=surface,
                                                  diag=diag)
            return timeline, diag
    raise ValueError(f"property not found: {property}")


def _diag_list(diag: DiagnosticBag) -> list[dict[str, Any]]:
    return [asdict(d) for d in diag.diagnostics]


def _list_text(items: list[dict[str, Any]]) -> str:
    properties = [i for i in items if i["type"] == "property"]
    assertions = [i for i in items if i["type"] in ("assert", "assume", "cover")]
    lines = ["Properties:"]
    lines.extend(f"  {p['name']}" for p in properties)
    lines.append("Assertions:")
    for item in assertions:
        label = item.get("label", "")
        if label:
            lines.append(f"  {label}: {item['type']} property ({item['name']})")
        else:
            lines.append(f"   {item['type']} property ({item['name']})")
    return "\n".join(lines) + "\n"


def _scan_text(stats: dict[str, Any]) -> str:
    lines = [
        f"File: {stats['file']}",
        f"Property blocks: {stats.get('property_blocks', 0)}",
        f"Inline assertions: {stats.get('inline_assertions', 0)}",
        "Operators:",
    ]
    op_names = {
        "|->": "|->", "|=>": "|=>", "##": "##N", "[*": "[*]",
        "[=": "[=]", "[->": "[->]", "first_match": "first_match",
        "throughout": "throughout", "intersect": "intersect",
        "within": "within", "$past": "$past", "$rose": "$rose",
        "$fell": "$fell", "$stable": "$stable", "$changed": "$changed",
    }
    operators = stats.get("operators", {})
    for op_key, op_label in op_names.items():
        count = operators.get(op_key, 0)
        if count > 0:
            lines.append(f"  {op_label:20s} {count}")
    return "\n".join(lines) + "\n"


def _error(exc: Exception) -> dict:
    return error_payload("XSVA_ERROR", str(exc))


def sva_list(file: str, output_format: str = "json") -> Any:
    """List all property/assertion names in a SVA source file."""
    try:
        items = _parser(file).list_properties()
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return {"ok": True, "file": file, "items": items}
    return _list_text(items)


def sva_scan(file: str, output_format: str = "json") -> Any:
    """Scan syntax constructs in a SVA source file."""
    try:
        stats = _parser(file).scan_statistics()
        stats["file"] = file
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return {"ok": True, "stats": stats}
    return _scan_text(stats)


def sva_parse(file: str, property: str, emit: str = "timeline-ir",
              output_format: str = "json") -> Any:
    """Parse a SVA property into IR (surface-ir/sequence-ir/timeline-ir)."""
    del output_format
    try:
        surface = _surface(file, property)
        if emit == "surface-ir":
            return _serialize_surface_ir(surface)
        seq = lower_surface_to_sequence(surface)
        if emit == "sequence-ir":
            return _serialize_sequence_ir(seq)
        if emit == "timeline-ir":
            timeline = lower_sequence_to_timeline(seq, surface_ir=surface)
            return _serialize_timeline_ir(timeline)
        return error_payload("XSVA_BAD_EMIT", f"unknown emit target: {emit}")
    except Exception as exc:
        return _error(exc)


def sva_explain(file: str, property: str, strict: bool = False,
                output_format: str = "xout") -> Any:
    """Generate a human-readable explanation of a SVA property."""
    try:
        timeline, diag = _timeline(file, property)
        if strict and timeline.lowering_status.value != "exact":
            return error_payload(
                "XSVA_UNSUPPORTED_STRICT",
                "strict mode cannot produce a fully precise explanation",
                diagnostics=_diag_list(diag),
            )
        if output_format == "json":
            return {
                "tool": "xsva",
                "command": "explain",
                "result": _serialize_timeline_ir(timeline),
                "diagnostics": _diag_list(diag),
            }
        if output_format == "markdown":
            return render_timeline_markdown(timeline)
        return render_timeline_text(timeline)
    except Exception as exc:
        return _error(exc)
