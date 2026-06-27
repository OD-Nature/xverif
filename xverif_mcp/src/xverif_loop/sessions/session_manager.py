"""McpSessionManager — multi-session lifecycle for stdio-loop backends."""

from __future__ import annotations

import getpass
import os
import re
import uuid as _uuid
from typing import Any, Dict, Optional

from xverif_loop.lsf.bsub import BsubRunner

from xverif_loop.config import (
    default_xdebug_bin,
    fake_lsf_enabled,
    loop_backend,
    startup_timeout,
    request_timeout,
)
from xverif_loop.logging import log_server_event, log_session_event
from xverif_loop.sessions.launchers import DirectLauncher, Launcher, LsfLauncher
from xverif_loop.sessions.loop_session import XdebugLoopSession

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


def _valid_session_name(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", s or ""))


def _error(code: str, message: str) -> Json:
    return {"ok": False, "error": {"code": code, "message": message}}


class McpSessionManager:
    def __init__(self, mode: Optional[str] = None, xdebug_bin: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None,
                 backend: str = "xdebug", api_version: str = "xdebug.v1",
                 ready_protocol: str = "xdebug-stdio-loop",
                 target_key: str = "fsdb",
                 recovery_tool: str = "xverif_debug_session_open") -> None:
        if startup_timeout_sec is None:
            startup_timeout_sec = startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = request_timeout()
        self.mode = mode or loop_backend()
        self.xdebug_bin = xdebug_bin or default_xdebug_bin()
        self.backend = backend
        self.api_version = api_version
        self.ready_protocol = ready_protocol
        self.target_key = target_key
        self.recovery_tool = recovery_tool
        self.startup_timeout_sec = startup_timeout_sec
        self.request_timeout_sec = request_timeout_sec
        self._session_queue = os.environ.get("XVERIF_LSF_SESSION_QUEUE", "interactive")
        self._session_resource = os.environ.get("XVERIF_LSF_SESSION_RESOURCE")
        if self.mode == "direct":
            self.launcher: Launcher = DirectLauncher()
        elif self.mode == "lsf":
            bsub_cmd = os.environ.get("XVERIF_LSF_BSUB")
            if fake_lsf_enabled() and not bsub_cmd:
                import sys
                bsub_cmd = f"{sys.executable} -m xverif_loop.lsf.fake_bsub"
            self.launcher = LsfLauncher(BsubRunner(bsub_cmd))
        else:
            raise ValueError(f"unsupported loop backend: {self.mode}")
        self._job_prefix = (
            f"xverif_{_safe_name(getpass.getuser())}_{os.getpid()}_"
            f"{_uuid.uuid4().hex[:8]}"
        )
        self.sessions: Dict[str, XdebugLoopSession] = {}
        log_server_event("manager.init", True, backend=self.backend,
                         launcher=self.mode, xdebug_bin=self.xdebug_bin)

    def open_session(self, name: str, fsdb: Optional[str] = None,
                     daidir: Optional[str] = None,
                     queue: Optional[str] = None, resource: Optional[str] = None,
                     **kwargs: Any) -> Json:
        if not _valid_session_name(name):
            log_session_event(name, "manager.open.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              error_code="INVALID_SESSION_NAME")
            return _error(
                "INVALID_SESSION_NAME",
                "session name must start with an ASCII letter and contain only "
                "ASCII letters, digits, and underscores, with maximum length 64",
            )
        if not fsdb and not daidir:
            log_session_event(name, "manager.open.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              error_code="RESOURCE_REQUIRED")
            return _error("RESOURCE_REQUIRED", "provide fsdb or daidir")
        if name in self.sessions:
            existing = self.sessions[name]
            if existing.state == "alive":
                if existing.process_alive():
                    log_session_event(name, "manager.open.rejected", False,
                                      backend=self.backend, launcher=self.mode,
                                      error_code="SESSION_ID_EXISTS")
                    return _error("SESSION_ID_EXISTS",
                                  f"session id already exists: {name}")
                log_session_event(name, "manager.open.rejected", False,
                                  backend=self.backend, launcher=self.mode,
                                  error_code="SESSION_STALE")
                return _error("SESSION_STALE",
                              "session id exists but is stale: "
                              f"{name}; close it explicitly before opening again")
        job_name = None
        actual_queue = queue or (self._session_queue if self.mode == "lsf" else None)
        actual_resource = resource or (self._session_resource if self.mode == "lsf" else None)
        if self.mode == "lsf":
            job_name = f"{self._job_prefix}_{_safe_name(self.backend)}_{_safe_name(name)}"
        log_session_event(name, "manager.open.begin", True,
                          backend=self.backend, launcher=self.mode,
                          fsdb=fsdb, daidir=daidir,
                          queue=actual_queue, resource=actual_resource,
                          job_name=job_name)
        session = XdebugLoopSession(
            alias=name, fsdb=fsdb, daidir=daidir, launcher=self.launcher,
            xdebug_bin=self.xdebug_bin, queue=actual_queue,
            resource=actual_resource, job_name=job_name,
            startup_timeout_sec=self.startup_timeout_sec,
            request_timeout_sec=self.request_timeout_sec,
            backend=self.backend, api_version=self.api_version,
            ready_protocol=self.ready_protocol, target_key=self.target_key,
            recovery_tool=self.recovery_tool)
        result = session.open()
        if not result.get("ok"):
            log_session_event(name, "manager.open.end", False,
                              backend=self.backend, launcher=self.mode,
                              response=result)
            return result
        self.sessions[name] = session
        if session.session_id:
            self.sessions[session.session_id] = session
        log_session_event(name, "manager.open.end", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=session.session_id,
                          public=session.public_json())
        return {"ok": True, "session": session.public_json()}

    def query(self, session: Optional[str], action: str,
              args: Optional[Json] = None, output_format: str = "xout",
              **kwargs: Any) -> Any:
        if not session:
            log_session_event("adhoc", "manager.query.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              action=action, error_code="SESSION_REQUIRED")
            return _error("SESSION_REQUIRED",
                          "explicit session is required")
        key = session
        s = self.sessions.get(key)
        if not s:
            log_session_event(key, "manager.query.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              action=action, error_code="SESSION_NOT_FOUND")
            return _error("SESSION_NOT_FOUND", f"session not found: {key}")
        log_session_event(s.alias, "manager.query.begin", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, action=action)
        rsp = s.query(action=action, args=args,
                       limits=kwargs.get("limits"), output=kwargs.get("output"),
                       output_format=output_format)
        if s.state == "dead":
            self._evict_session(s)
        log_session_event(s.alias, "manager.query.end",
                          not (isinstance(rsp, dict) and not rsp.get("ok", True)),
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, action=action,
                          response=rsp if isinstance(rsp, dict) else None)
        return rsp

    def close_session(self, session: str) -> Json:
        s = self.sessions.get(session)
        if not s:
            log_session_event(session, "manager.close.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              error_code="SESSION_NOT_FOUND")
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        old_state = s.state
        if s.state == "alive":
            rsp = s.close()
        else:
            cleanup = s.abort(f"close requested for non-alive session: {old_state}",
                              source="close_dead")
            rsp = {"ok": True, "closed": s.public_json(), "cleanup": cleanup}
        if not rsp.get("ok", True):
            log_session_event(s.alias, "manager.close.end", False,
                              backend=self.backend, launcher=self.mode,
                              session_id=s.session_id, previous_state=old_state,
                              response=rsp)
            return rsp
        self._evict_session(s)
        log_session_event(s.alias, "manager.close.end", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, previous_state=old_state)
        rsp["previous_state"] = old_state
        return rsp

    def list_sessions(self) -> Json:
        seen = set()
        rows = []
        for s in self.sessions.values():
            if id(s) in seen:
                continue
            seen.add(id(s))
            rows.append(s.public_json())
        log_server_event("manager.list", True, backend=self.backend,
                         launcher=self.mode, session_count=len(rows))
        return {"ok": True, "sessions": rows}

    def _evict_session(self, s: XdebugLoopSession) -> None:
        log_session_event(s.alias, "manager.evict", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, state=s.state)
        self.sessions.pop(s.alias, None)
        if s.session_id:
            self.sessions.pop(s.session_id, None)
        for key, value in list(self.sessions.items()):
            if value is s:
                self.sessions.pop(key, None)

    def session_open(self, name: str, fsdb: Optional[str] = None,
                     **kwargs: Any) -> Json:
        return self.open_session(name=name, fsdb=fsdb, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self.list_sessions()

    def session_close(self, session: str) -> Json:
        return self.close_session(session)

    def close_all(self) -> None:
        seen = set()
        for s in list(self.sessions.values()):
            if id(s) in seen:
                continue
            seen.add(id(s))
            try:
                if s.state == "alive":
                    s.close()
                else:
                    s.abort(
                        f"manager shutdown for non-alive session: {s.state}",
                        source="manager_close_all",
                    )
            except Exception:
                try:
                    s.abort("manager shutdown cleanup failed",
                            source="manager_close_all")
                except Exception:
                    pass
        self.sessions.clear()
