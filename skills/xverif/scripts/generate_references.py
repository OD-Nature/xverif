#!/usr/bin/env python3
"""Generate checked-in xverif references from canonical runtime metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "xverif"
ACTION_SPECS = ROOT / "xdebug" / "specs" / "actions" / "actions.yaml"
ACTION_OUTPUT = SKILL / "references" / "generated" / "xdebug-actions.md"
EXAMPLES = SKILL / "specs" / "examples.yaml"
SURFACE_OUTPUT = SKILL / "references" / "generated" / "surface-examples.md"


def _required(entry: dict) -> str:
    parts = list(entry.get("required_args", []))
    groups = entry.get("required_arg_groups", [])
    if groups:
        parts.extend("one of " + "/".join(group) for group in groups)
    return ", ".join(parts) or "以 action schema 为准"


def action_reference() -> str:
    payload = json.loads(ACTION_SPECS.read_text(encoding="utf-8"))
    lines = [
        "# xdebug 全量 Action 索引",
        "",
        "本文件由 `skills/xverif/scripts/generate_references.py` 从 canonical action specs 生成。",
        "用途是保证所有能力可发现；精确参数以 runtime catalog、action-specific schema 和 checked-in example 为准。",
        "",
        "| Action | Category | Requires | Required inputs | Request schema | Example |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in payload["actions"]:
        request_schema = entry.get("schemas", {}).get("request")
        schema = "xdebug/" + request_schema if request_schema else "-"
        examples = entry.get("examples", {}).get("request", [])
        example = "xdebug/" + examples[0] if examples else "-"
        lines.append(
            f"| `{entry['name']}` | {entry.get('category', '-')} | "
            f"{entry.get('requires', '-')} | {_required(entry)} | "
            f"`{schema}` | `{example}` |"
        )
    lines.extend([
        "",
        f"共 {len(payload['actions'])} 个 action。主流程见 [xdebug capability](../capabilities/xdebug.md)。",
        "",
    ])
    return "\n".join(lines)


def surface_examples() -> str:
    # This canonical example is intentionally parsed without a YAML dependency.
    action = "value.batch_at"
    session = "case_a"
    args = {
        "time": "100ns",
        "clock": "top.clk",
        "signals": ["top.u.valid", "top.u.ready", "top.u.full"],
    }
    native = {"api_version": "xdebug.v1", "action": action,
              "target": {"session_id": session}, "args": args}
    mcp = {"tool": "xverif_debug_query", "args": {
        "session_id": session, "action": action, "args": args}}
    loop = {"method": "debug.query", "params": {
        "session": session, "action": action, "args": args}}
    blocks = [
        "# 生成的 Surface 示例", "",
        f"Canonical source: `{EXAMPLES.relative_to(ROOT)}`。", "",
    ]
    for title, value in (("CLI", native), ("MCP", mcp), ("SDK-free loop", loop)):
        blocks.extend([f"## {title}", "", "```json",
                       json.dumps(value, indent=2, ensure_ascii=False), "```", ""])
    return "\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = {ACTION_OUTPUT: action_reference(), SURFACE_OUTPUT: surface_examples()}
    stale = [path for path, text in outputs.items()
             if not path.exists() or path.read_text(encoding="utf-8") != text]
    if args.check:
        if stale:
            print("stale generated references:")
            for path in stale:
                print(path.relative_to(ROOT))
            return 1
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
