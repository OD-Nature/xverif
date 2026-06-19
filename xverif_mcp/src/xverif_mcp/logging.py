"""Structured NDJSON logging for xverif MCP stateful backends."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


Json = Dict[str, Any]

_COUNTER = 0


def _safe_name(s: Optional[str], max_len: int = 64) -> str:
    import re
    x = re.sub(r"[^A-Za-z0-9_]", "_", s or "").strip("_")
    return (x or "adhoc")[:max_len]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _event_id() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"{time.time_ns():x}-{os.getpid()}-{_COUNTER}"


def log_root() -> Path:
    configured = os.environ.get("XVERIF_MCP_LOG_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ.get("HOME", "/tmp")) / ".xverif" / "mcp"


def server_log_path() -> Path:
    return log_root() / "logs" / "server.ndjson"


def session_log_path(alias: Optional[str], name: str) -> Path:
    return log_root() / "sessions" / _safe_name(alias) / f"{name}.ndjson"


def argv_hash(argv: Iterable[str]) -> str:
    h = 1469598103934665603
    for item in argv:
        for b in item.encode("utf-8", errors="replace"):
            h ^= b
            h *= 1099511628211
            h &= 0xFFFFFFFFFFFFFFFF
        h ^= 0
        h *= 1099511628211
        h &= 0xFFFFFFFFFFFFFFFF
    return f"{h:x}"


def _path_key(key: str) -> bool:
    return (
        key in {"fsdb", "daidir", "dbdir", "file_dir", "socket_path", "path", "log_path"}
        or "_path" in key
        or "_dir" in key
    )


def _path_mode() -> str:
    mode = os.environ.get("XDEBUG_LOG_PATH_MODE")
    if mode:
        return mode
    redact = os.environ.get("XDEBUG_LOG_REDACT")
    if redact and redact != "0":
        return "hash"
    return "full"


def _redact_path(value: str) -> str:
    mode = _path_mode()
    if mode == "basename":
        return Path(value).name
    if mode == "hash":
        return f"<path:{argv_hash([value])}>"
    return value


def _sanitize(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        return _redact_path(value) if _path_key(key) else value
    if isinstance(value, list):
        return [_sanitize(item, key) for item in value[:200]]
    if isinstance(value, dict):
        out: Json = {}
        for k, v in list(value.items())[:200]:
            out[str(k)] = _sanitize(v, str(k))
        return out
    return value


def _append(path: Path, event: Json) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _base(phase: str, ok: bool, **fields: Any) -> Json:
    event: Json = {
        "ts": _now(),
        "event_id": _event_id(),
        "pid": os.getpid(),
        "layer": "mcp",
        "component": "xverif-mcp",
        "phase": phase,
        "ok": ok,
    }
    for key, value in fields.items():
        if value is not None:
            event[key] = _sanitize(value, key)
    return event


def log_server_event(phase: str, ok: bool = True, **fields: Any) -> None:
    _append(server_log_path(), _base(phase, ok, **fields))


def log_session_event(alias: Optional[str], phase: str, ok: bool = True, **fields: Any) -> None:
    _append(session_log_path(alias, "session"), _base(phase, ok, alias=_safe_name(alias), **fields))


def log_stdio_event(alias: Optional[str], phase: str, ok: bool = True, **fields: Any) -> None:
    _append(session_log_path(alias, "stdio"), _base(phase, ok, alias=_safe_name(alias), **fields))


def log_lsf_event(alias: Optional[str], phase: str, ok: bool = True, **fields: Any) -> None:
    _append(session_log_path(alias, "lsf"), _base(phase, ok, alias=_safe_name(alias), **fields))
