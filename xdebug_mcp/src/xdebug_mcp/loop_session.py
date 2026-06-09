"""XdebugLoopSession — single --stdio-loop process backed session."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from xdebug_lsf.protocol import JsonlProcess

from .launchers import LaunchConfig, Launcher, default_xdebug_bin

Json = Dict[str, Any]


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _error(code: str, message: str) -> Json:
    return {"ok": False, "error": {"code": code, "message": message}}


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
    startup_timeout_sec: float = 60.0
    request_timeout_sec: float = 120.0

    # managed state
    session_id: Optional[str] = None
    state: str = "new"
    handle: Optional[JsonlProcess] = None
    pid: Optional[int] = None
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------------
    # open / close
    # ------------------------------------------------------------------

    def open(self) -> Json:
        if self.state not in ("new", "closed", "dead"):
            return _error("SESSION_EXISTS", f"session already opened: {self.alias}")

        cfg = LaunchConfig(
            alias=self.alias,
            xdebug_bin=self.xdebug_bin,
            queue=self.queue,
            resource=self.resource,
            job_name=self.job_name,
            startup_timeout_sec=self.startup_timeout_sec,
        )
        self.handle = self.launcher.start(cfg)

        try:
            ready = self.handle.wait_ready("xdebug-stdio-loop", self.startup_timeout_sec)
            self.pid = int(ready.get("pid") or 0)

            # Send session.open
            open_req: Json = {
                "request_id": f"open-{_safe_name(self.alias)}",
                "api_version": "xdebug.v1",
                "action": "session.open",
                "target": {"fsdb": self.fsdb},
                "args": {"name": self.alias, "transport": "uds"},
                "output": {"format": "json"},
            }
            if self.daidir:
                open_req["target"]["daidir"] = self.daidir

            rsp = self._call_raw(open_req, timeout=self.startup_timeout_sec)
            if not rsp.get("ok"):
                self.state = "dead"
                return rsp

            payload = rsp.get("json", rsp)
            self.session_id = _extract_session_id(payload, self.alias)
            self.state = "alive"
            return {"ok": True, "session": self.public_json()}
        except Exception as e:
            self.state = "dead"
            self.close(force=True)
            return _error("SESSION_OPEN_FAILED", str(e))

    def close(self, force: bool = False) -> Json:
        if self.handle and self.state == "alive" and self.session_id and not force:
            try:
                self._call_raw({
                    "request_id": f"close-{_safe_name(self.alias)}",
                    "api_version": "xdebug.v1",
                    "action": "session.close",
                    "target": {"session_id": self.session_id},
                    "output": {"format": "json"},
                }, timeout=10.0)
            except Exception:
                pass
            try:
                self._call_raw({
                    "request_id": f"quit-{_safe_name(self.alias)}",
                    "api_version": "xdebug.v1",
                    "action": "stdio.quit",
                }, timeout=5.0)
            except Exception:
                pass

        if self.handle:
            try:
                self.launcher.terminate(self.handle)
            except Exception:
                pass

        self.state = "closed"
        return {"ok": True, "closed": self.public_json()}

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    def query(self, action: str, args: Optional[Json], output_format: str) -> Any:
        if self.state != "alive" or not self.session_id:
            return _error("SESSION_DEAD", f"session is not alive: {self.alias}")

        self._seq += 1
        req: Json = {
            "request_id": f"{_safe_name(self.alias)}-{self._seq}",
            "api_version": "xdebug.v1",
            "action": action,
            "target": {"session_id": self.session_id},
            "args": args or {},
        }
        if output_format in ("json", "envelope"):
            req["output"] = {"format": "json"}

        rsp = self._call_raw(req)
        if not rsp.get("ok"):
            return rsp
        if output_format == "xout":
            return rsp.get("xout", "")
        if output_format == "json":
            return rsp.get("json", rsp)
        if output_format == "envelope":
            return rsp
        return _error("INVALID_OUTPUT_FORMAT", f"unsupported: {output_format}")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _call_raw(self, req: Json, timeout: Optional[float] = None) -> Json:
        if not self.handle:
            return _error("SESSION_PROCESS_MISSING", "no loop process")
        with self._lock:
            return self.handle.request(req, timeout or self.request_timeout_sec)

    # ------------------------------------------------------------------
    # public info
    # ------------------------------------------------------------------

    def public_json(self) -> Json:
        h = self.handle
        out: Json = {
            "alias": self.alias,
            "session_id": self.session_id,
            "fsdb": self.fsdb,
            "daidir": self.daidir,
            "state": self.state,
            "mode": self.launcher.mode,
        }
        if self.queue:
            out["queue"] = self.queue
        if self.resource:
            out["resource"] = self.resource
        if self.job_name:
            out["job_name"] = self.job_name
        if h and getattr(h, "job_id", None):
            out["job_id"] = h.job_id
        if self.pid:
            out["pid"] = self.pid
        return out
