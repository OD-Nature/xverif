"""LoopSession — single --stdio-loop process backed session."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from xverif_loop.lsf.protocol import JsonlProcess, ProtocolError
from xverif_loop.logging import log_session_event

from xverif_loop.config import default_xdebug_bin, startup_timeout, request_timeout, close_timeout
from xverif_loop.sessions.launchers import LaunchConfig, Launcher
from xverif_loop.sessions.session_errors import response_says_session_terminal
from xverif_mcp.xdebug_errors import translate_native_example_for_query, xout_error

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


def _error(code: str, message: str, **extra: Any) -> Json:
    err: Json = {"code": code, "message": message}
    err.update(extra)
    return {"ok": False, "error": err}


def _extract_session_id(response: Json) -> Optional[str]:
    for key in ("summary", "data", "session"):
        value = response.get(key)
        if isinstance(value, dict):
            sid = value.get("session_id") or value.get("id")
            if isinstance(sid, str) and sid:
                return sid
    return None


def _trace_id(alias: str, request_id: str) -> str:
    return f"mcp-{_safe_name(alias)}-{request_id}"


@dataclass
class XdebugLoopSession:
    alias: str
    fsdb: Optional[str]
    daidir: Optional[str]
    launcher: Launcher
    xdebug_bin: str = field(default_factory=default_xdebug_bin)
    backend: str = "xdebug"
    api_version: str = "xdebug.v1"
    ready_protocol: str = "xdebug-stdio-loop"
    target_key: str = "fsdb"
    recovery_tool: str = "xverif_debug_session_open"
    queue: Optional[str] = None
    resource: Optional[str] = None
    job_name: Optional[str] = None
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
        log_session_event(self.alias, "session.abort.begin", False,
                          backend=self.backend, launcher=self.launcher.mode,
                          session_id=self.session_id, reason=reason,
                          source=source, state=self.state)
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
        log_session_event(self.alias, "session.abort.end", cleanup.get("subprocess") != "cleanup_failed",
                          backend=self.backend, launcher=self.launcher.mode,
                          session_id=self.session_id, cleanup=cleanup,
                          job_id=getattr(handle, "job_id", None) if handle else None,
                          job_name=getattr(handle, "job_name", None) if handle else None)
        return cleanup

    def _session_lost_error(self, message: str, *, source: str,
                             backend_response: Optional[Json] = None,
                             cleanup: Optional[Json] = None) -> Json:
        # Build recovery hint — for timeouts, include contextual advice
        if source == "transport" and "timeout" in message.lower():
            reason = (
                "session lost due to timeout — "
                "possible causes: large FSDB / deep trace / complex query, "
                "or LSF queue congestion delaying job start. "
                "If caused by large data, try narrowing time_range or limits. "
                "If caused by LSF queue delay, consider increasing "
                "XVERIF_MCP_STARTUP_TIMEOUT_SEC (session open, default 180s) "
                "or XVERIF_MCP_REQUEST_TIMEOUT_SEC (query, default 360s). "
                "Close or gc the stale session, then open a new session before retrying."
            )
        else:
            reason = "session is no longer reusable; close or gc it before opening a new session"

        return _error("SESSION_LOST", message, alias=self.alias,
                       session_id=self.session_id, mode=self.launcher.mode,
                       terminal_source=source, backend_response=backend_response,
                       cleanup=cleanup or self.last_cleanup,
                       recovery_hint={
                           "action": self.recovery_tool,
                           "reason": reason,
                           "env_vars": {
                               "XVERIF_MCP_STARTUP_TIMEOUT_SEC":
                                   "session open timeout (default 180s)",
                               "XVERIF_MCP_REQUEST_TIMEOUT_SEC":
                                   "query timeout (default 360s)",
                           },
                       })

    def open(self) -> Json:
        if self.state not in ("new", "closed", "dead"):
            return _error("SESSION_EXISTS", f"session already opened: {self.alias}")
        t0 = time.monotonic()
        log_session_event(self.alias, "session.open.begin", True,
                          backend=self.backend, launcher=self.launcher.mode,
                          fsdb=self.fsdb, daidir=self.daidir,
                          queue=self.queue, resource=self.resource,
                          job_name=self.job_name)
        cfg = LaunchConfig(alias=self.alias, xdebug_bin=self.xdebug_bin,
                           backend=self.backend,
                           tool_bin=self.xdebug_bin,
                           queue=self.queue, resource=self.resource,
                           job_name=self.job_name,
                           startup_timeout_sec=self.startup_timeout_sec)
        self.handle = self.launcher.start(cfg)
        try:
            ready = self.handle.wait_ready(self.ready_protocol, self.startup_timeout_sec)
            self.pid = int(ready.get("pid") or 0)
            open_req: Json = {
                "request_id": f"open-{_safe_name(self.alias)}",
                "api_version": self.api_version, "action": "session.open",
                "target": {},
                "args": {"name": self.alias},
                "output": {"response_format": "json"} if self.backend == "xcov"
                else {"format": "json"},
            }
            open_req["trace_id"] = _trace_id(self.alias, open_req["request_id"])
            if self.backend == "xdebug":
                open_req["args"]["transport"] = "uds"
            if self.fsdb:
                open_req["target"][self.target_key] = self.fsdb
            if self.daidir:
                open_req["target"]["daidir"] = self.daidir
            rsp = self._call_raw(open_req, timeout=self.startup_timeout_sec)
            if not rsp.get("ok"):
                self.state = "dead"
                log_session_event(self.alias, "session.open.end", False,
                                  backend=self.backend, launcher=self.launcher.mode,
                                  elapsed_ms=int((time.monotonic() - t0) * 1000),
                                  response=rsp)
                return rsp
            payload = rsp.get("json", rsp)
            self.session_id = _extract_session_id(payload)
            if not self.session_id:
                self.state = "dead"
                cleanup = self.abort("backend did not return session_id",
                                     source="open")
                return _error(
                    "BACKEND_SESSION_ID_MISSING",
                    "backend session.open response did not include session_id",
                    cleanup=cleanup,
                    backend_response=payload,
                )
            self.state = "alive"
            log_session_event(self.alias, "session.open.end", True,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id, pid=self.pid,
                              elapsed_ms=int((time.monotonic() - t0) * 1000),
                              job_id=getattr(self.handle, "job_id", None) if self.handle else None,
                              job_name=getattr(self.handle, "job_name", None) if self.handle else None)
            return {"ok": True, "session": self.public_json()}
        except Exception as e:
            cleanup = self.abort(str(e), source="open")
            log_session_event(self.alias, "session.open.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              elapsed_ms=int((time.monotonic() - t0) * 1000),
                              error=str(e), cleanup=cleanup)
            return _error("SESSION_OPEN_FAILED", str(e), cleanup=cleanup)

    def close(self, force: bool = False) -> Json:
        log_session_event(self.alias, "session.close.begin", True,
                          backend=self.backend, launcher=self.launcher.mode,
                          session_id=self.session_id, force=force,
                          state=self.state)
        cleanup: Json = {
            "backend_close": "skipped",
            "stdio_quit": "skipped",
            "terminate": "skipped",
        }
        errors: Json = {}
        if self.handle and self.state == "alive" and self.session_id and not force:
            try:
                req = {
                    "request_id": f"close-{_safe_name(self.alias)}",
                    "trace_id": _trace_id(self.alias, f"close-{_safe_name(self.alias)}"),
                    "api_version": self.api_version, "action": "session.close",
                    "target": {"session_id": self.session_id},
                    "output": {"response_format": "json"} if self.backend == "xcov"
                    else {"format": "json"},
                }
                self._call_raw(req, timeout=close_timeout())
                cleanup["backend_close"] = "ok"
            except Exception as exc:
                cleanup["backend_close"] = "failed"
                errors["backend_close"] = str(exc)
            try:
                req = {
                    "request_id": f"quit-{_safe_name(self.alias)}",
                    "trace_id": _trace_id(self.alias, f"quit-{_safe_name(self.alias)}"),
                    "api_version": self.api_version, "action": "stdio.quit",
                }
                self._call_raw(req, timeout=close_timeout() / 2)
                cleanup["stdio_quit"] = "ok"
            except Exception as exc:
                if not self.process_alive():
                    cleanup["stdio_quit"] = "ok_process_exited"
                else:
                    cleanup["stdio_quit"] = "failed"
                    errors["stdio_quit"] = str(exc)
        elif force:
            cleanup["backend_close"] = "force_skipped"
            cleanup["stdio_quit"] = "force_skipped"
        if self.handle:
            try:
                self.launcher.terminate(self.handle)
                cleanup["terminate"] = "ok"
            except Exception as exc:
                cleanup["terminate"] = "failed"
                errors["terminate"] = str(exc)
        self.last_cleanup = cleanup
        if errors:
            cleanup["errors"] = errors
            log_session_event(self.alias, "session.close.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id, state=self.state,
                              cleanup=cleanup)
            return _error(
                "SESSION_CLEANUP_PARTIAL_FAILURE",
                "session cleanup failed; retry close or inspect cleanup details",
                cleanup=cleanup,
                session=self.public_json(),
            )
        self.state = "closed"
        log_session_event(self.alias, "session.close.end", True,
                          backend=self.backend, launcher=self.launcher.mode,
                          session_id=self.session_id, state=self.state,
                          cleanup=cleanup)
        return {"ok": True, "closed": self.public_json(), "cleanup": cleanup}

    def query(self, action: str, args: Optional[Json] = None,
              target: Optional[Json] = None, limits: Optional[Json] = None,
              output: Optional[Json] = None, output_format: str = "xout") -> Any:
        if self.state != "alive" or not self.session_id:
            return _error("SESSION_DEAD", f"session is not alive: {self.alias}")
        self._seq += 1
        req: Json = {
            "request_id": f"{_safe_name(self.alias)}-{self._seq}",
            "api_version": self.api_version, "action": action,
        }
        req["trace_id"] = _trace_id(self.alias, req["request_id"])
        if args:
            req["args"] = args
        req["target"] = {"session_id": self.session_id}
        if limits:
            req["limits"] = limits
        req["output"] = dict(output or {})
        if output_format in ("json", "envelope"):
            if self.backend == "xcov":
                req["output"]["response_format"] = "json"
            else:
                req["output"]["format"] = "json"
        try:
            log_session_event(self.alias, "query.begin", True,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"],
                              trace_id=req["trace_id"], action=action)
            rsp = self._call_raw(req)
        except ProtocolError as exc:
            cleanup = self.abort(str(exc), source="transport")
            log_session_event(self.alias, "query.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"], action=action,
                              terminal_source="transport", cleanup=cleanup,
                              error=str(exc))
            return self._session_lost_error(
                f"{self.backend} stdio-loop transport lost: {exc}",
                source="transport", cleanup=cleanup)
        except OSError as exc:
            cleanup = self.abort(str(exc), source="io")
            log_session_event(self.alias, "query.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"], action=action,
                              terminal_source="io", cleanup=cleanup,
                              error=str(exc))
            return self._session_lost_error(
                f"{self.backend} stdio-loop io error: {exc}",
                source="io", cleanup=cleanup)
        except Exception as exc:
            cleanup = self.abort(str(exc), source="unexpected")
            log_session_event(self.alias, "query.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"], action=action,
                              terminal_source="unexpected", cleanup=cleanup,
                              error=str(exc))
            return self._session_lost_error(
                f"{self.backend} stdio-loop unexpected failure: {exc}",
                source="unexpected", cleanup=cleanup)
        if response_says_session_terminal(rsp):
            cleanup = self.abort(
                f"backend reported terminal session after action {action}",
                source="backend_response")
            log_session_event(self.alias, "query.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"], action=action,
                              terminal_source="backend_response",
                              backend_response=rsp, cleanup=cleanup)
            return self._session_lost_error(
                f"{self.backend} backend reported terminal session after action {action}",
                source="backend_response", backend_response=rsp, cleanup=cleanup)
        if not rsp.get("ok"):
            log_session_event(self.alias, "query.end", False,
                              backend=self.backend, launcher=self.launcher.mode,
                              session_id=self.session_id,
                              request_id=req["request_id"], action=action,
                              response=rsp)
            if self.backend == "xdebug":
                backend_response = rsp.get("json") if isinstance(rsp.get("json"), dict) else {
                    "ok": False,
                    "action": action,
                    "error": rsp.get("error", {}),
                }
                shaped = translate_native_example_for_query(
                    backend_response,
                    session_id=self.alias,
                )
                if output_format == "xout":
                    return xout_error(shaped)
                if output_format == "json":
                    return shaped
                if output_format == "envelope":
                    out = dict(rsp)
                    out["json"] = shaped
                    out["error"] = shaped.get("error", rsp.get("error", {}))
                    return out
            return rsp
        log_session_event(self.alias, "query.end", True,
                          backend=self.backend, launcher=self.launcher.mode,
                          session_id=self.session_id,
                          request_id=req["request_id"], action=action)
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
                      "daidir": self.daidir,
                      "state": self.state, "mode": self.launcher.mode,
                      "backend": self.backend}
        if self.fsdb:
            out[self.target_key] = self.fsdb
        if self.queue: out["queue"] = self.queue
        if self.resource: out["resource"] = self.resource
        if self.job_name: out["job_name"] = self.job_name
        if h and getattr(h, "job_id", None): out["job_id"] = h.job_id
        if self.pid: out["pid"] = self.pid
        return out
