from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator


FENCED_JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def markdown_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.md"))


def assert_markdown_links(root: Path) -> None:
    failures: list[str] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for raw in MARKDOWN_LINK_RE.findall(text):
            target = raw.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (path.parent / target).exists():
                failures.append(f"{path.relative_to(root)} -> {raw}")
    assert not failures, "broken Markdown links:\n" + "\n".join(failures)


def fenced_json(root: Path) -> Iterator[tuple[Path, dict]]:
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for index, raw in enumerate(FENCED_JSON_RE.findall(text), start=1):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"invalid fenced JSON in {path.relative_to(root)} block {index}: {exc}"
                ) from exc
            if isinstance(payload, dict):
                yield path, payload
