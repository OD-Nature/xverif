"""XdebugLoopSession — single --stdio-loop process backed session."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from xverif_mcp.lsf.protocol import JsonlProcess, ProtocolError

from xverif_mcp.config import default_xdebug_bin, startup_timeout, request_timeout, close_timeout
from xverif_mcp.sessions.launchers import LaunchConfig, Launcher
from xverif_mcp.sessions.session_errors import response_says_session_terminal

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


def _error(code: str, message: str, **extra: Any) -> Json:
    err: Json = {"code": code, "message": message}
    err.update(extra)
    return {"ok": False, "error": err}


def _extract_session_id(response: Json, fallback: str) -> str:
    for key in ("summary", "data", "session"):
        value = response.get(key)
        if isinstance(value, dict):
            sid = value.get("session_id") or value.get("id")
            if isinstance(sid, str) and sid:
                return sid
    return fallback


@dataclass
class XdebugLoopSession:
    alias: str
    fsdb: str
    daidir: Optional[str]
    launcher: Launcher
    xdebug_bin: str = field(default_factory=default_xdebug_bin)
    queue: Optional[str] = None
    resource: Optional[str] = None
    job_name: Optional[str] = None
    reuse: bool = True
    reopen: bool = False
    startup_timeout_sec: float = field(default_factory=startup_timeout)
    request_timeout_sec: float = field(default_factory=request_timeout)

    session_id: Optional[str] = None
    state: str = "new"
    handle: Optional[JsonlProcess] = None
    pid: Optional[int] = None
    last_error: Optional[str] = None
    last_cleanup: Json = field(default_factory=dict)
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def process_alive(self) -> bool:
        h = self.handle
        if h is None:
            return False
        proc = getattr(h, "proc", None)
        return proc is not None and proc.poll() is None

    def abort(self, reason: str, source: str = "transport") -> Json:
        self.state = "dead"
        self.last_error = reason
        cleanup: Json = {"source": source, "subprocess": "not_started",
                          "lsf_job": "not_applicable"}
        handle = self.handle
        self.handle = None
        if handle is not None:
            try:
                self.launcher.terminate(handle)
                cleanup["subprocess"] = "terminated"
                if getattr(handle, "job_id", None) or getattr(handle, "job_name", None):
                    cleanup["lsf_job"] = "kill_requested"
            except Exception as exc:
                cleanup["subprocess"] = "cleanup_failed"
                cleanup["cleanup_error"] = str(exc)
        self.last_cleanup = cleanup
        return cleanup

    def _session_lost_error(self, message: str, *, source: str,
                             backend_response: Optional[Json] = None,
                             cleanup: Optional[Json] = None) -> Json:
        return _error("SESSION_LOST", message, alias=self.alias,
                       session_id=self.session_id, mode=self.launcher.mode,
                       terminal_source=source, backend_response=backend_response,
                       cleanup=cleanup or self.last_cleanup,
                       recovery_hint={
                           "action": "xverif_session_open",
                           "reason": "session is no longer reusable; reopen explicitly",
                       })

    def open(self) -> Json:
        if self.state not in ("new", "closed", "dead"):
            return _error("SESSION_EXISTS", f"session already opened: {self.alias}")
        cfg = LaunchConfig(alias=self.alias, xdebug_bin=self.xdebug_bin,
                           queue=self.queue, resource=self.resource,
                           job_name=self.job_name,
                           startup_timeout_sec=self.startup_timeout_sec)
        self.handle = self.launcher.start(cfg)
        try:
            ready = self.handle.wait_ready("xdebug-stdio-loop", self.startup_timeout_sec)
            self.pid = int(ready.get("pid") or 0)
            open_req: Json = {
                "request_id": f"open-{_safe_name(self.alias)}",
                "api_version": "xdebug.v1", "action": "session.open",
                "target": {"fsdb": self.fsdb},
                "args": {"name": self.alias, "transport": "uds",
                         "reuse": self.reuse, "reopen": self.reopen},
                "output": {"format": "json"},
            }
            if self.daidir:
                open_req["target"]["daidir"] = self.daidir
            rsp = self._call_raw(open_req, timeout=self.startup_timeout_sec)
            err = rsp.get("error", {})
            if not rsp.get("ok") and err.get("code") != "SESSION_ID_EXISTS":
                self.state = "dead"
                return rsp
            payload = rsp.get("json", rsp)
            self.session_id = _extract_session_id(payload, self.alias)
            self.state = "alive"
            return {"ok": True, "session": self.public_json()}
        except Exception as e:
            cleanup = self.abort(str(e), source="open")
            return _error("SESSION_OPEN_FAILED", str(e), cleanup=cleanup)

    def close(self, force: bool = False) -> Json:
        if self.handle and self.state == "alive" and self.session_id and not force:
            try:
                self._call_raw({
                    "request_id": f"close-{_safe_name(self.alias)}",
                    "api_version": "xdebug.v1", "action": "session.close",
                    "target": {"session_id": self.session_id},
                    "output": {"format": "json"},
                }, timeout=close_timeout())
            except Exception:
                pass
            try:
                self._call_raw({
                    "request_id": f"quit-{_safe_name(self.alias)}",
                    "api_version": "xdebug.v1", "action": "stdio.quit",
                }, timeout=close_timeout() / 2)
            except Exception:
                pass
        if self.handle:
            try:
                self.launcher.terminate(self.handle)
            except Exception:
                pass
        self.state = "closed"
        return {"ok": True, "closed": self.public_json()}

    def query(self, action: str, args: Optional[Json] = None,
              target: Optional[Json] = None, limits: Optional[Json] = None,
              output: Optional[Json] = None, output_format: str = "xout") -> Any:
        if self.state != "alive" or not self.session_id:
            return _error("SESSION_DEAD", f"session is not alive: {self.alias}")
        self._seq += 1
        req: Json = {
            "request_id": f"{_safe_name(self.alias)}-{self._seq}",
            "api_version": "xdebug.v1", "action": action,
        }
        if args:
            req["args"] = args
        if target:
            req["target"] = target
        else:
            req["target"] = {"session_id": self.session_id}
        if limits:
            req["limits"] = limits
        req["output"] = dict(output or {})
        if output_format in ("json", "envelope"):
            req["output"]["format"] = "json"
        try:
            rsp = self._call_raw(req)
        except ProtocolError as exc:
            cleanup = self.abort(str(exc), source="transport")
            return self._session_lost_error(
                f"xdebug stdio-loop transport lost: {exc}",
                source="transport", cleanup=cleanup)
        except OSError as exc:
            cleanup = self.abort(str(exc), source="io")
            return self._session_lost_error(
                f"xdebug stdio-loop io error: {exc}",
                source="io", cleanup=cleanup)
        except Exception as exc:
            cleanup = self.abort(str(exc), source="unexpected")
            return self._session_lost_error(
                f"xdebug stdio-loop unexpected failure: {exc}",
                source="unexpected", cleanup=cleanup)
        if response_says_session_terminal(rsp):
            cleanup = self.abort(
                f"backend reported terminal session after action {action}",
                source="backend_response")
            return self._session_lost_error(
                f"xdebug backend reported terminal session after action {action}",
                source="backend_response", backend_response=rsp, cleanup=cleanup)
        if not rsp.get("ok"):
            return rsp
        if output_format == "xout":
            return rsp.get("xout", "")
        if output_format == "json":
            return rsp.get("json", rsp)
        if output_format == "envelope":
            return rsp
        return _error("INVALID_OUTPUT_FORMAT", f"unsupported: {output_format}")

    def _call_raw(self, req: Json, timeout: Optional[float] = None) -> Json:
        if not self.handle:
            return _error("SESSION_PROCESS_MISSING", "no loop process")
        with self._lock:
            return self.handle.request(req, timeout_sec=timeout or self.request_timeout_sec)

    def public_json(self) -> Json:
        h = self.handle
        out: Json = {"alias": self.alias, "session_id": self.session_id,
                      "fsdb": self.fsdb, "daidir": self.daidir,
                      "state": self.state, "mode": self.launcher.mode}
        if self.queue: out["queue"] = self.queue
        if self.resource: out["resource"] = self.resource
        if self.job_name: out["job_name"] = self.job_name
        if h and getattr(h, "job_id", None): out["job_id"] = h.job_id
        if self.pid: out["pid"] = self.pid
        return out
