from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Set


DEFAULT_VOLATILE_KEYS = {
    "pid",
    "ppid",
    "elapsed_ms",
    "elapsed_us",
    "started_at",
    "ended_at",
    "created_at",
    "updated_at",
    "timestamp",
    "socket_path",
    "job_id",
}


@dataclass(frozen=True)
class NormalizeOptions:
    volatile_keys: Set[str] = field(
        default_factory=lambda: set(DEFAULT_VOLATILE_KEYS)
    )
    path_replacements: Mapping[str, str] = field(default_factory=dict)
    unordered_list_paths: Set[str] = field(default_factory=set)


_TMP_PATH = re.compile(
    re.escape(str(Path(tempfile.gettempdir()))) + r"/[A-Za-z0-9_.-]+"
)


def _normalize_string(value: str, replacements: Mapping[str, str]) -> str:
    normalized = value
    for source, target in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        normalized = normalized.replace(str(Path(source)), target)
    return _TMP_PATH.sub("<tmp>", normalized)


def _stable_list_key(value: Any) -> str:
    return repr(value)


def normalize_response(
    value: Any,
    options: NormalizeOptions | None = None,
    *,
    _path: Sequence[str] = (),
) -> Any:
    opts = options or NormalizeOptions()
    path_text = ".".join(_path)
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in sorted(value):
            if key in opts.volatile_keys:
                continue
            out[key] = normalize_response(
                value[key], opts, _path=tuple(_path) + (str(key),)
            )
        return out
    if isinstance(value, list):
        rows = [
            normalize_response(item, opts, _path=tuple(_path) + ("[]",))
            for item in value
        ]
        if path_text in opts.unordered_list_paths:
            return sorted(rows, key=_stable_list_key)
        return rows
    if isinstance(value, str):
        return _normalize_string(value, opts.path_replacements)
    return value
