#!/usr/bin/env python3
"""Validate an xwiki verification LLM wiki.

The wiki root is normally provided by XWIKI_DIR. This script intentionally
uses only the Python standard library so it can run from Codex or Claude hooks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

ENV_NAME = "XWIKI_DIR"
REQUIRED_FRONTMATTER = ("type", "title", "description", "object_type")
OBJECT_TYPES = {"de", "dv", "de_issue", "dv_issue"}
RESERVED_NAMES = {"index.md", "log.md"}
INDEX_DIR = "_index"
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+(?:\s+\"[^\"]*\")?)\)")
LOG_HEADING_RE = re.compile(r"^##\s+(?:\[\d{4}-\d{2}-\d{2}\]|\d{4}-\d{2}-\d{2})(?:\s|$)")
LOCAL_ABSOLUTE_RE = re.compile(r"^(?:/|~[/\\]|[A-Za-z]:[/\\])")


@dataclass
class Finding:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_wiki_dir(args: argparse.Namespace) -> tuple[Path | None, list[Finding]]:
    raw = args.wiki_dir or os.environ.get(ENV_NAME, "")
    if not raw.strip():
        return None, [
            Finding(
                "XWIKI_DIR_MISSING",
                ENV_NAME,
                f"{ENV_NAME} is not set; ask the user for the xwiki wiki path.",
            )
        ]
    path = Path(raw).expanduser()
    if not path.is_absolute() and args.root:
        path = Path(args.root).expanduser().resolve() / path
    path = path.resolve()
    if not path.exists() or not path.is_dir():
        return path, [Finding("WIKI_DIR_INVALID", str(path), "wiki directory does not exist")]
    return path, []


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _hook_file_path(data: dict[str, Any], root: Path | None) -> Path | None:
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    return path.resolve()


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    if not text.startswith("---\n"):
        return None
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end < 0:
        return None
    raw = text[4:end]
    body = text[end + len(marker) :]
    meta: dict[str, str] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "-")) and current_key:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        meta[current_key] = value.strip().strip("\"'")
    return meta, body


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _is_external_link(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "mailto:", "#", "data:"))


def _clean_link_target(target: str) -> str:
    target = target.strip()
    if " " in target and target.count('"') >= 2:
        target = target.split(" ", 1)[0]
    target = target.split("#", 1)[0].split("?", 1)[0]
    return unquote(target)


def _link_exists(source: Path, target: str) -> bool:
    raw = _clean_link_target(target)
    if not raw:
        return True
    candidate = (source.parent / raw).resolve()
    if candidate.is_dir():
        return (candidate / "index.md").exists()
    if candidate.exists():
        return True
    if not candidate.suffix and candidate.with_suffix(".md").exists():
        return True
    return False


def _validate_links(root: Path, path: Path, text: str, findings: list[Finding]) -> None:
    for match in LINK_RE.finditer(text):
        target = _clean_link_target(match.group(1))
        if not target or _is_external_link(target):
            continue
        rel_path = _rel(path, root)
        if target.lower().startswith("file://"):
            findings.append(Finding("LINK_FILE_URI", rel_path, f"file URI link is forbidden: {target}"))
            continue
        if LOCAL_ABSOLUTE_RE.match(target):
            findings.append(Finding("LINK_ABSOLUTE_PATH", rel_path, f"absolute local link is forbidden: {target}"))
            continue
        if not _link_exists(path, target):
            findings.append(Finding("LINK_BROKEN", rel_path, f"link target does not exist: {target}"))


def _validate_log(root: Path, path: Path, text: str, findings: list[Finding]) -> None:
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    rel_path = _rel(path, root)
    if not headings:
        findings.append(Finding("LOG_DATE_HEADING_MISSING", rel_path, "log.md must contain dated ## entries"))
        return
    for line in headings:
        if not LOG_HEADING_RE.match(line):
            findings.append(Finding("LOG_DATE_HEADING_INVALID", rel_path, f"invalid log heading: {line}"))


def _validate_markdown_frontmatter(root: Path, path: Path, text: str, findings: list[Finding]) -> None:
    rel_path = _rel(path, root)
    parsed = _parse_frontmatter(text)
    if parsed is None:
        findings.append(Finding("FRONTMATTER_MISSING", rel_path, "markdown file must start with YAML frontmatter"))
        return
    meta, _body = parsed
    for key in REQUIRED_FRONTMATTER:
        if not meta.get(key):
            findings.append(Finding("FRONTMATTER_FIELD_MISSING", rel_path, f"missing required frontmatter field: {key}"))
    object_type = meta.get("object_type", "")
    if object_type and object_type not in OBJECT_TYPES:
        allowed = ", ".join(sorted(OBJECT_TYPES))
        findings.append(Finding("OBJECT_TYPE_INVALID", rel_path, f"object_type must be one of: {allowed}"))
    in_deprecated_dir = rel_path.startswith("archive/") or rel_path.startswith("deprecated/")
    is_deprecated = meta.get("deprecated", "").lower() == "true"
    if in_deprecated_dir and not is_deprecated:
        findings.append(Finding("DEPRECATED_FLAG_MISSING", rel_path, "archive/deprecated pages require deprecated: true"))
    if is_deprecated and not meta.get("deprecated_reason"):
        findings.append(Finding("DEPRECATED_REASON_MISSING", rel_path, "deprecated pages require deprecated_reason"))


def validate_wiki(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    index = root / "index.md"
    log = root / "log.md"
    if not index.exists():
        findings.append(Finding("INDEX_MISSING", "index.md", "index.md is required"))
    if not log.exists():
        findings.append(Finding("LOG_MISSING", "log.md", "log.md is required"))

    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding("UTF8_INVALID", _rel(path, root), "markdown file must be UTF-8"))
            continue
        _validate_markdown_frontmatter(root, path, text, findings)
        if path.name == "log.md" and path.parent == root:
            _validate_log(root, path, text, findings)
        _validate_links(root, path, text, findings)
    return findings


def _payload(ok: bool, wiki_dir: Path | None, findings: list[Finding]) -> dict[str, Any]:
    return {
        "ok": ok,
        "schema_version": "xwiki.validation.v1",
        "wiki_dir": str(wiki_dir) if wiki_dir is not None else None,
        "error_count": len(findings),
        "errors": [finding.as_dict() for finding in findings],
    }


def _print_cli(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload["ok"]:
        print("ok")
        return
    for error in payload["errors"]:
        print(f"error: {error['code']}: {error['path']}: {error['message']}", file=sys.stderr)


def _print_claude_stop(payload: dict[str, Any]) -> None:
    if payload["ok"]:
        print(json.dumps({"decision": "approve", "systemMessage": "xwiki wiki validation passed"}, ensure_ascii=False))
        return
    reason = "; ".join(f"{e['code']} {e['path']}: {e['message']}" for e in payload["errors"][:8])
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "xwiki wiki validation failed: " + reason,
                "systemMessage": "Fix the xwiki LLM wiki before stopping.",
            },
            ensure_ascii=False,
        )
    )


def _print_claude_file(payload: dict[str, Any]) -> None:
    if payload["ok"]:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    },
                    "systemMessage": "xwiki wiki validation passed",
                },
                ensure_ascii=False,
            )
        )
        return
    reason = "; ".join(f"{e['code']} {e['path']}: {e['message']}" for e in payload["errors"][:8])
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                },
                "systemMessage": "xwiki wiki validation failed: " + reason,
            },
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an xwiki verification LLM wiki")
    parser.add_argument("--wiki-dir", help=f"Wiki root. Defaults to ${ENV_NAME}.")
    parser.add_argument("--root", help="Project root for resolving relative --wiki-dir and hook file paths.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--hook", choices=("none", "claude-stop", "claude-file"), default="none")
    args = parser.parse_args(argv)

    project_root = Path(args.root).expanduser().resolve() if args.root else Path.cwd().resolve()
    wiki_dir, findings = _resolve_wiki_dir(args)

    if args.hook == "claude-file":
        data = _read_stdin_json()
        target = _hook_file_path(data, project_root)
        if wiki_dir is not None and (target is None or target.suffix != ".md" or not _is_under(target, wiki_dir)):
            _print_claude_file(_payload(True, wiki_dir, []))
            return 0

    if wiki_dir is not None and not findings:
        findings = validate_wiki(wiki_dir)
    payload = _payload(not findings, wiki_dir, findings)

    if args.hook == "claude-stop":
        _print_claude_stop(payload)
        return 0
    if args.hook == "claude-file":
        _print_claude_file(payload)
        return 0
    _print_cli(payload, args.format)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
