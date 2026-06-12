"""xsva CLI — argparse 入口。

命令（对齐 spec 第五章）：
  xsva list    --file <file>
  xsva scan    --file <file>
  xsva lint    --file <file>
  xsva explain --file <file> --property <name> [--json] [--markdown] [--strict]
  xsva parse   --file <file> --property <name> --emit surface-ir|sequence-ir|timeline-ir

Exit code (对齐 spec 5.7):
  0 = success, 1 = parse error, 2 = unsupported in strict mode,
  3 = property not found, 4 = file error, 5 = internal error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from xsva.ir.diagnostics import DiagnosticBag
from xsva.ir.surface import SurfaceIR
from xsva.ir.timeline import TimelineIR
from xsva.parser.property_parser import PropertyParser
from xsva.parser.scanner import Scanner
from xsva.lower.surface_to_sequence import lower_surface_to_sequence
from xsva.lower.sequence_to_timeline import lower_sequence_to_timeline
from xsva.explain.text import render_timeline_text
from xsva.explain.markdown import render_timeline_markdown

EXIT_SUCCESS = 0
EXIT_PARSE_ERROR = 1
EXIT_UNSUPPORTED_STRICT = 2
EXIT_PROPERTY_NOT_FOUND = 3
EXIT_FILE_ERROR = 4
EXIT_INTERNAL_ERROR = 5


def _read_file(filepath: str) -> str:
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"xsva error: file not found: {filepath}", file=sys.stderr)
        sys.exit(EXIT_FILE_ERROR)
    except OSError as e:
        print(f"xsva error: cannot read file: {filepath}: {e}", file=sys.stderr)
        sys.exit(EXIT_FILE_ERROR)


def _find_property(results: list, name: str):
    for ir in results:
        if ir.name == name:
            return ir
    print(f"xsva error: property not found: {name}", file=sys.stderr)
    sys.exit(EXIT_PROPERTY_NOT_FOUND)


def _parse_and_lower(args):
    """通用：读取文件→解析→lowering→返回 timeline + surface。"""
    text = _read_file(args.file)
    diag = DiagnosticBag()
    scanner = Scanner(text, file=args.file)
    parser = PropertyParser(scanner, diag)
    results = parser.parse_file()
    surface_ir = _find_property(results, args.property)
    seq_ir = lower_surface_to_sequence(surface_ir, diag)
    timeline = lower_sequence_to_timeline(seq_ir, surface_ir=surface_ir, diag=diag)
    return timeline, surface_ir, diag


def _parse_surface_only(args):
    """仅解析到 SurfaceIR。"""
    text = _read_file(args.file)
    diag = DiagnosticBag()
    scanner = Scanner(text, file=args.file)
    parser = PropertyParser(scanner, diag)
    results = parser.parse_file()
    return _find_property(results, args.property), diag


# ── 命令实现 ──

def cmd_list(args: argparse.Namespace) -> None:
    text = _read_file(args.file)
    scanner = Scanner(text, file=args.file)
    parser = PropertyParser(scanner, DiagnosticBag())
    items = parser.list_properties()

    properties = [i for i in items if i["type"] == "property"]
    assertions = [i for i in items if i["type"] in ("assert", "assume", "cover")]

    print("Properties:")
    for p in properties:
        print(f"  {p['name']}")

    print("Assertions:")
    for a in assertions:
        label_str = f" ({a['label']})" if a.get("label") else ""
        print(f"  {a.get('label', '')}{':' if a.get('label') else ''} {a['type']} property ({a['name']}){label_str if not a.get('label') else ''}")


def cmd_scan(args: argparse.Namespace) -> None:
    text = _read_file(args.file)
    scanner = Scanner(text, file=args.file)
    parser = PropertyParser(scanner, DiagnosticBag())
    stats = parser.scan_statistics()
    stats["file"] = args.file

    print(f"File: {stats['file']}")
    print(f"Property blocks: {stats.get('property_blocks', 0)}")
    print(f"Inline assertions: {stats.get('inline_assertions', 0)}")
    print("Operators:")
    op_names = {
        "|->": "|->", "|=>": "|=>", "##": "##N", "[*": "[*]", "[=": "[=]",
        "[->": "[->]", "first_match": "first_match", "throughout": "throughout",
        "intersect": "intersect", "within": "within",
        "$past": "$past", "$rose": "$rose", "$fell": "$fell",
        "$stable": "$stable", "$changed": "$changed",
    }
    operators = stats.get("operators", {})
    for op_key, op_label in op_names.items():
        count = operators.get(op_key, 0)
        if count > 0:
            print(f"  {op_label:20s} {count}")


def cmd_lint(args: argparse.Namespace) -> None:
    from xsva.lint import lint_timeline

    text = _read_file(args.file)
    scanner = Scanner(text, file=args.file)
    parser = PropertyParser(scanner, DiagnosticBag())
    results = parser.parse_file()

    if not args.property:
        # Lint all properties
        all_diags: list = []
        for ir in results:
            seq = lower_surface_to_sequence(ir)
            timeline = lower_sequence_to_timeline(seq, surface_ir=ir)
            all_diags.extend(lint_timeline(timeline, surface_ir=ir))

        _print_diagnostics(all_diags)
    else:
        surface = _find_property(results, args.property)
        seq = lower_surface_to_sequence(surface)
        timeline = lower_sequence_to_timeline(seq, surface_ir=surface)
        diags = lint_timeline(timeline, surface_ir=surface)
        _print_diagnostics(diags)


def cmd_explain(args: argparse.Namespace) -> None:
    try:
        timeline, surface, diag = _parse_and_lower(args)
    except SystemExit:
        raise  # 重新抛出（file error, property not found 等）
    except Exception as e:
        print(f"xsva error: parse failed: {e}", file=sys.stderr)
        sys.exit(EXIT_PARSE_ERROR)

    if args.strict and timeline.lowering_status.value != "exact":
        print("xsva error: strict mode cannot produce a fully precise explanation "
              "for this advanced sequence", file=sys.stderr)
        for d in diag.diagnostics:
            print(f"  [{d.severity}] {d.code}: {d.message}", file=sys.stderr)
        sys.exit(EXIT_UNSUPPORTED_STRICT)

    if args.json:
        _output_json(timeline, diag)
    elif args.markdown:
        print(render_timeline_markdown(timeline))
    else:
        print(render_timeline_text(timeline))


def cmd_parse(args: argparse.Namespace) -> None:
    try:
        surface, _ = _parse_surface_only(args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"xsva error: parse failed: {e}", file=sys.stderr)
        sys.exit(EXIT_PARSE_ERROR)

    if args.emit == "surface-ir":
        output = _serialize_surface_ir(surface)
    elif args.emit == "sequence-ir":
        seq_ir = lower_surface_to_sequence(surface)
        output = _serialize_sequence_ir(seq_ir)
    elif args.emit == "timeline-ir":
        seq_ir = lower_surface_to_sequence(surface)
        timeline = lower_sequence_to_timeline(seq_ir, surface_ir=surface)
        output = _serialize_timeline_ir(timeline)
    else:
        print(f"xsva error: unknown emit target: {args.emit}", file=sys.stderr)
        sys.exit(EXIT_INTERNAL_ERROR)

    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))


# ── 序列化 helpers ──

def _output_json(timeline: TimelineIR, diag: DiagnosticBag) -> None:
    output = {
        "tool": "xsva",
        "command": "explain",
        "result": _serialize_timeline_ir(timeline),
        "diagnostics": [asdict(d) for d in diag.diagnostics],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))


def _serialize_timeline_ir(timeline: TimelineIR) -> dict[str, Any]:
    return {
        "schema_version": timeline.schema_version,
        "property": timeline.property_name,
        "kind": timeline.kind,
        "clock": {"edge": timeline.clock.edge, "signal": timeline.clock.signal},
        "disable_expr": timeline.disable_expr,
        "trigger": {
            "cycle": timeline.trigger.cycle,
            "expr": timeline.trigger.expr,
            "captures": [{"var": c.var, "value_expr": c.value_expr,
                          "relative_cycle": c.relative_cycle} for c in timeline.trigger.captures],
        },
        "obligations": [
            {"id": ob.id, "kind": ob.kind.value, "expr": ob.expr,
             "has_window": ob.has_window,
             "window": {"start": ob.window.start, "end": ob.window.end, "unbounded": ob.window.unbounded} if ob.window else None,
             "depends_on_captures": ob.depends_on_captures,
             "requirement": ob.requirement,
             "failure_condition": ob.failure_condition}
            for ob in timeline.obligations
        ],
        "match_paths": [
            {"id": p.id, "description": p.description,
             "obligations": [ob.kind.value for ob in p.obligations]}
            for p in timeline.match_paths
        ],
        "failure_conditions": [fc.condition for fc in timeline.failure_conditions],
        "semantic_notes": [
            {"kind": n.kind, "expr": n.expr, "text": n.text}
            for n in timeline.semantic_notes
        ],
        "diagnostics": [asdict(d) for d in timeline.diagnostics],
    }


def _serialize_surface_ir(surface: SurfaceIR) -> dict[str, Any]:
    output = asdict(surface)
    output.pop("lowering_status", None)
    return output


def _serialize_sequence_ir(seq_ir) -> dict[str, Any]:
    return {
        "name": seq_ir.name,
        "nodes": [
            {"kind": n.kind.value, "expr": n.expr.raw if n.expr else None,
             "delay": {"min": n.min_delay, "max": n.max_delay, "unbounded": n.unbounded}
             if n.min_delay > 0 or n.max_delay > 0 else None,
             "children_count": len(n.children)}
            for n in seq_ir.nodes
        ],
    }


def _print_diagnostics(diags: list) -> None:
    if not diags:
        print("No issues found.")
        return
    for d in diags:
        print(f"[{d.severity}] {d.code}: {d.message}")


# ── main ──

def main() -> None:
    parser = argparse.ArgumentParser(prog="xsva", description="SystemVerilog Assertion 语义编译工具")
    subparsers = parser.add_subparsers(dest="command")

    # list
    list_p = subparsers.add_parser("list", help="列出文件中所有 property/assertion")
    list_p.add_argument("--file", required=True, help="SVA 源文件路径")

    # scan
    scan_p = subparsers.add_parser("scan", help="扫描语法构造分布")
    scan_p.add_argument("--file", required=True, help="SVA 源文件路径")

    # lint
    lint_p = subparsers.add_parser("lint", help="静态规则检查")
    lint_p.add_argument("--file", required=True, help="SVA 源文件路径")
    lint_p.add_argument("--property", default=None, help="property 名称（可选，不指定则检查全部）")

    # explain
    explain_p = subparsers.add_parser("explain", help="生成 property 解释")
    explain_p.add_argument("--file", required=True, help="SVA 源文件路径")
    explain_p.add_argument("--property", required=True, help="property 名称")
    explain_p.add_argument("--json", action="store_true", help="输出 JSON 格式")
    explain_p.add_argument("--markdown", action="store_true", help="输出 Markdown 格式")
    explain_p.add_argument("--strict", action="store_true", help="strict 模式：unsupported 时报错退出")

    # parse
    parse_p = subparsers.add_parser("parse", help="输出 IR JSON")
    parse_p.add_argument("--file", required=True, help="SVA 源文件路径")
    parse_p.add_argument("--property", required=True, help="property 名称")
    parse_p.add_argument("--emit", required=True,
                         choices=["surface-ir", "sequence-ir", "timeline-ir"],
                         help="输出 IR 层级")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(EXIT_SUCCESS)

    try:
        dispatch = {
            "list": cmd_list,
            "scan": cmd_scan,
            "lint": cmd_lint,
            "explain": cmd_explain,
            "parse": cmd_parse,
        }
        dispatch[args.command](args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"xsva internal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(EXIT_INTERNAL_ERROR)
