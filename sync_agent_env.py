#!/usr/bin/env python3
"""Sync current environment variables into agent project settings."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple


TARGETS = {
    "claude": Path(".claude/settings.json"),
    "claude-local": Path(".claude/settings.local.json"),
    "codex": Path(".codex/config.toml"),
}


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge current env output into Claude Code or Codex project settings. "
            "Existing variables that are not present in the current env are kept."
        )
    )
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        required=True,
        help="settings file to update",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="project root to update; defaults to the current directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the target path and merge size without writing files",
    )
    return parser.parse_args(argv)


def current_env() -> Dict[str, str]:
    return dict(os.environ)


def read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a top-level JSON object")
    return data


def sync_claude(path: Path, env: Mapping[str, str], dry_run: bool) -> Tuple[int, int]:
    data = read_json_object(path)
    existing_env = data.get("env", {})
    if not isinstance(existing_env, dict):
        raise ValueError(f"{path} field 'env' must be a JSON object")

    merged = {str(key): str(value) for key, value in existing_env.items()}
    before = dict(merged)
    merged.update(env)
    data["env"] = dict(sorted(merged.items()))

    changed = sum(1 for key, value in env.items() if before.get(key) != value)
    added = sum(1 for key in env if key not in before)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changed, added


def toml_string(value: str) -> str:
    return json.dumps(value)


def toml_key(value: str) -> str:
    return json.dumps(value)


def render_toml_set_table(values: Mapping[str, str]) -> List[str]:
    lines = ["[shell_environment_policy.set]\n"]
    for key in sorted(values):
        lines.append(f"{toml_key(str(key))} = {toml_string(str(values[key]))}\n")
    return lines


def find_explicit_table(lines: List[str], table_name: str) -> Optional[Tuple[int, int]]:
    header_re = re.compile(r"^\s*\[" + re.escape(table_name) + r"\]\s*(?:#.*)?$")
    any_header_re = re.compile(r"^\s*\[.*\]\s*(?:#.*)?$")
    start = None
    for index, line in enumerate(lines):
        if header_re.match(line):
            if start is not None:
                raise ValueError(f"duplicate TOML table: [{table_name}]")
            start = index
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any_header_re.match(lines[index]):
            end = index
            break
    return start, end


def strip_toml_comment_suffix(text: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "#":
            return text[:index].rstrip()
    return text.rstrip()


def parse_toml_key(text: str, path: Path, line_number: int) -> str:
    text = text.strip()
    if not text:
        raise ValueError(f"{path}:{line_number}: missing TOML key")
    if text.startswith('"'):
        try:
            key, end = json.JSONDecoder().raw_decode(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid quoted TOML key: {exc}") from exc
        if not isinstance(key, str):
            raise ValueError(f"{path}:{line_number}: quoted TOML key must decode to a string")
        if text[end:].strip():
            raise ValueError(f"{path}:{line_number}: unsupported dotted or compound TOML key")
        return key
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    raise ValueError(f"{path}:{line_number}: unsupported TOML key syntax: {text!r}")


def parse_toml_string(text: str, path: Path, line_number: int) -> str:
    text = text.strip()
    if not text.startswith('"'):
        raise ValueError(f"{path}:{line_number}: only double-quoted string TOML values are supported")
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line_number}: invalid TOML string value: {exc}") from exc
    if not isinstance(value, str):
        raise ValueError(f"{path}:{line_number}: TOML value must be a string")
    rest = text[end:].strip()
    if rest and not rest.startswith("#"):
        raise ValueError(f"{path}:{line_number}: unsupported trailing TOML content")
    return value


def parse_toml_set_table(
    path: Path,
    lines: List[str],
    table_range: Optional[Tuple[int, int]],
) -> Dict[str, str]:
    if table_range is None:
        return {}

    start, end = table_range
    values: Dict[str, str] = {}
    for index in range(start + 1, end):
        line_number = index + 1
        raw_line = lines[index]
        content = raw_line.strip()
        if not content or content.startswith("#"):
            continue
        if content.startswith("["):
            raise ValueError(f"{path}:{line_number}: nested TOML tables are not supported here")

        statement = strip_toml_comment_suffix(raw_line).strip()
        if not statement:
            continue
        if "=" not in statement:
            raise ValueError(f"{path}:{line_number}: expected KEY = \"VALUE\"")

        key_text, value_text = statement.split("=", 1)
        key = parse_toml_key(key_text, path, line_number)
        if key in values:
            raise ValueError(f"{path}:{line_number}: duplicate key in shell_environment_policy.set: {key}")
        values[key] = parse_toml_string(value_text, path, line_number)
    return values


def sync_codex(path: Path, env: Mapping[str, str], dry_run: bool) -> Tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = text.splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not valid UTF-8: {exc}") from exc

    table_range = find_explicit_table(lines, "shell_environment_policy.set")
    existing_set = parse_toml_set_table(path, lines, table_range)

    merged = {str(key): str(value) for key, value in existing_set.items()}
    before = dict(merged)
    merged.update(env)

    rendered = render_toml_set_table(merged)
    changed = sum(1 for key, value in env.items() if before.get(key) != value)
    added = sum(1 for key in env if key not in before)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        if table_range is None:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            if lines and any(line.strip() for line in lines):
                lines.append("\n")
            lines.extend(rendered)
        else:
            start, end = table_range
            replacement = rendered
            if end < len(lines) and replacement[-1].strip():
                replacement.append("\n")
            lines[start:end] = replacement
        path.write_text("".join(lines), encoding="utf-8")
    return changed, added


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    target_path = root / TARGETS[args.target]
    env = current_env()

    try:
        if args.target in {"claude", "claude-local"}:
            changed, added = sync_claude(target_path, env, args.dry_run)
        elif args.target == "codex":
            changed, added = sync_codex(target_path, env, args.dry_run)
        else:
            raise AssertionError(f"unhandled target: {args.target}")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    action = "would update" if args.dry_run else "updated"
    print(
        f"{action} {target_path} with {len(env)} env vars "
        f"({changed} changed, {added} added)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
