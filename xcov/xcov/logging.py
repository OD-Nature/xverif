from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

Json = Dict[str, Any]

MAX_STRING = 4096
MAX_ARRAY = 64
MAX_OBJECT = 128
MAX_DEPTH = 8
MAX_LINE = 256 * 1024

HEAVY_KEYS = {
    "items", "rows", "raw_rows", "data", "xout", "scopes",
    "metrics_by_scope", "source_text", "trace", "all_events",
}


def enabled() -> bool:
    return str(os.environ.get("XVERIF_XCOV_LOG", "1")).lower() not in {
        "0", "false", "no", "off",
    }


def log_root() -> Path:
    override = os.environ.get("XVERIF_XCOV_LOG_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("HOME", "/tmp")) / ".xverif" / "xcov"


def _safe_session_id(session_id: str | None) -> str:
    raw = session_id or "adhoc"
    out = []
    for ch in raw:
        out.append(ch if ch.isalnum() or ch in "_.-" else "_")
    return "".join(out) or "adhoc"


def public_session_dir(session_id: str | None) -> Path:
    return log_root() / "sessions" / _safe_session_id(session_id)


def public_action_log_path(session_id: str | None) -> Path:
    return public_session_dir(session_id) / "logs" / "actions.ndjson"


def backend_log_path(session_id: str | None, log_name: str) -> Path:
    return (log_root() / "backend" / "sessions" / _safe_session_id(session_id) /
            "logs" / f"{log_name}.ndjson")


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _event_id() -> str:
    counter = getattr(_event_id, "_counter", 0)
    setattr(_event_id, "_counter", counter + 1)
    return f"{int(time.time() * 1000000):x}-{os.getpid()}-{counter:x}"


def sanitize_for_log(value: Any, depth: int = 0) -> Any:
    truncated = {"value": False}
    out = _sanitize(value, depth, truncated)
    if truncated["value"] and isinstance(out, dict):
        out["log_truncated"] = True
    return out


def _sanitize(value: Any, depth: int, truncated: Json) -> Any:
    if depth > MAX_DEPTH:
        truncated["value"] = True
        return "<truncated:depth>"
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            truncated["value"] = True
            return value[:MAX_STRING] + "...<truncated:string>"
        return value
    if isinstance(value, list):
        out = [_sanitize(item, depth + 1, truncated) for item in value[:MAX_ARRAY]]
        if len(value) > MAX_ARRAY:
            truncated["value"] = True
            out.append("<truncated:array>")
        return out
    if isinstance(value, dict):
        out: Json = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= MAX_OBJECT:
                truncated["value"] = True
                out["<truncated>"] = "object"
                break
            if key in HEAVY_KEYS:
                truncated["value"] = True
                out[key] = "<omitted:large-field>"
            else:
                out[key] = _sanitize(item, depth + 1, truncated)
        return out
    return value


def request_summary_for_log(request: Json) -> Json:
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    args = request.get("args") if isinstance(request.get("args"), dict) else {}
    out: Json = {
        "request_id": request.get("request_id"),
        "action": request.get("action", ""),
    }
    keys = ("session_id", "name", "vdb")
    out["target"] = sanitize_for_log({k: target[k] for k in keys if k in target})
    out["arg_keys"] = list(args.keys())
    if "name" in args:
        out["name"] = args["name"]
    if "session_id" in args:
        out["arg_session_id"] = args["session_id"]
    if "limits" in request:
        out["limits"] = sanitize_for_log(request["limits"])
    if "output" in request:
        out["output"] = sanitize_for_log(request["output"])
    if "limits" in args:
        out["args_limits"] = sanitize_for_log(args["limits"])
    if "output" in args:
        out["args_output"] = sanitize_for_log(args["output"])
    return out


def response_summary_for_log(response: Json) -> Json:
    out: Json = {
        "ok": response.get("ok", False),
        "action": response.get("action", ""),
        "request_id": response.get("request_id"),
    }
    if "summary" in response:
        out["summary"] = sanitize_for_log(response["summary"])
    if "meta" in response:
        out["meta"] = sanitize_for_log(response["meta"])
    if response.get("error") is not None:
        out["error"] = sanitize_for_log(response.get("error"))
    return out


def update_session_manifest(session_id: str, session: Json) -> None:
    if not enabled():
        return
    try:
        path = public_session_dir(session_id) / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old: Json = {}
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        now = _now_iso8601()
        manifest = {
            "session_id": session_id or "adhoc",
            "vdb": session.get("vdb"),
            "state": session.get("state"),
            "worker": session.get("worker"),
            "test_count": session.get("test_count"),
            "top_scope_count": session.get("top_scope_count"),
            "created_at": old.get("created_at", now),
            "last_log_at": now,
            "log_path": str(public_action_log_path(session_id)),
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    except Exception:
        pass


def log_action_event(layer: str, session_id: str | None, action: str, phase: str,
                     ok: bool, elapsed_ms: int = 0, context: Json | None = None) -> None:
    event = _base_event(layer, session_id, action, phase, ok, context or {})
    event["elapsed_ms"] = elapsed_ms
    if layer == "public":
        _append_event(public_action_log_path(session_id), event)
    else:
        _append_event(backend_log_path(session_id, "actions"), event)


def log_lifecycle_event(session_id: str | None, phase: str, ok: bool,
                        context: Json | None = None) -> None:
    _append_event(backend_log_path(session_id, "lifecycle"),
                  _base_event("backend", session_id, "", phase, ok, context or {}))


def log_transport_event(session_id: str | None, phase: str, ok: bool,
                        context: Json | None = None) -> None:
    _append_event(backend_log_path(session_id, "transport"),
                  _base_event("backend", session_id, "", phase, ok, context or {}))


def _base_event(layer: str, session_id: str | None, action: str, phase: str,
                ok: bool, context: Json) -> Json:
    return {
        "ts": _now_iso8601(),
        "event_id": _event_id(),
        "pid": os.getpid(),
        "layer": layer,
        "component": "xcov",
        "session_id": session_id or "adhoc",
        "action": action,
        "phase": phase,
        "ok": ok,
        "context": sanitize_for_log(context),
    }


def _append_event(path: Path, event: Json) -> None:
    if not enabled():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        if len(line) > MAX_LINE:
            event = {
                **event,
                "log_truncated": True,
                "context": {"message": "log event exceeded max line size and was truncated"},
            }
            line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
