#!/usr/bin/env python3
"""Generate checked-in xverif references from canonical runtime metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


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
        "| Action | Status | Category | Requires | Purposes | Use for | Do not use for | Preferred alternative | Required inputs | 中文说明 | English description | Request schema | Example |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    entries = [entry for entry in payload["actions"] if entry.get("status") != "removed"]
    for entry in entries:
        request_schema = entry.get("schemas", {}).get("request")
        schema = "xdebug/" + request_schema if request_schema else "-"
        examples = entry.get("examples", {}).get("request", [])
        example = "xdebug/" + examples[0] if examples else "-"
        lines.append(
            f"| `{entry['name']}` | {entry.get('status', '-')} | {entry.get('category', '-')} | "
            f"{entry.get('requires', '-')} | {', '.join(entry.get('purposes', [])) or '-'} | "
            f"{'; '.join(entry.get('use_for', [])) or '-'} | "
            f"{'; '.join(entry.get('do_not_use_for', [])) or '-'} | "
            f"{json.dumps(entry.get('preferred_alternative', {}), ensure_ascii=False)} | "
            f"{_required(entry)} | {entry.get('description_zh', '-')} | {entry.get('description_en', '-')} | "
            f"`{schema}` | `{example}` |"
        )
    lines.extend([
        "",
        f"共 {len(entries)} 个当前公开 action。主流程见 [xdebug capability](../capabilities/xdebug.md)。",
        "",
    ])
    return "\n".join(lines)


def surface_examples() -> str:
    source = yaml.safe_load(EXAMPLES.read_text(encoding="utf-8"))
    examples = source.get("examples", []) if isinstance(source, dict) else []
    if not examples or not isinstance(examples[0], dict):
        raise ValueError(f"{EXAMPLES} must contain at least one example object")
    example = examples[0]
    action = str(example["action"])
    session = str(example["session"])
    args = example["args"]
    if not isinstance(args, dict):
        raise ValueError(f"{EXAMPLES} example args must be an object")
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
