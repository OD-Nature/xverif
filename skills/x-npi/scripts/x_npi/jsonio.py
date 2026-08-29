"""Small JSON response helpers for x-npi example scripts."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterable, IO, List, Tuple


Json = Dict[str, Any]


def ok(action: str, data: Json | None = None, summary: Json | None = None, **extra: Any) -> Json:
    out: Json = {"ok": True, "action": action}
    if summary is not None:
        out["summary"] = summary
    if data is not None:
        out["data"] = data
    out.update(extra)
    return out


def error(action: str, code: str, message: str, **extra: Any) -> Json:
    out: Json = {"ok": False, "action": action, "error": {"code": code, "message": message}}
    if extra:
        out["error"].update(extra)
    return out


def print_json(obj: Any, stream: IO[str] | None = None) -> None:
    target = stream or sys.stdout
    json.dump(obj, target, indent=2, sort_keys=True)
    target.write("\n")
    target.flush()


def split_limited(rows: Iterable[Any], limit: int | None) -> Tuple[List[Any], bool]:
    data = list(rows)
    if limit is None or limit < 0 or len(data) <= limit:
        return data, False
    return data[:limit], True
