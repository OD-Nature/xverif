"""McpSessionManager — multi-session lifecycle for stdio-loop backends."""

from __future__ import annotations

import getpass
import os
import re
import threading
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
from xverif_loop.sessions.capabilities import lifecycle_capability

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


def _valid_session_name(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", s or ""))


def _error(code: str, message: str, **extra: Any) -> Json:
    error: Json = {"code": code, "message": message}
    error.update(extra)
    return {"ok": False, "error": error}


def _cleanup_success(operation: str, session: XdebugLoopSession,
                     cleanup: Json, **summary_fields: Any) -> Json:
    stages = dict(cleanup)
    stages["manager_record"] = "evicted"
    stages["tombstone"] = "retained_closed"
    summary: Json = {
        "status": "closed",
        "operation": operation,
        "ownership": "managed",
        "backend": session.backend,
        "alias": session.alias,
        "session_id": session.session_id,
        "cleanup_complete": True,
    }
    summary.update(summary_fields)
    return {
        "ok": True,
        "summary": summary,
        "data": {
            "session": session.public_json(),
            "cleanup": stages,
        },
    }


def _cleanup_failure(response: Json, session: XdebugLoopSession) -> Json:
    error = response.setdefault("error", {})
    error.setdefault("error_layer", "session_manager")
    cleanup = error.setdefault("cleanup", {})
    cleanup["manager_record"] = "evicted"
    cleanup["tombstone"] = "retained_unresolved"
    error["session"] = session.public_json()
    return response


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
        self.tombstones: Dict[str, XdebugLoopSession] = {}
        self._manager_lock = threading.RLock()
        self._opening: set[str] = set()
        log_server_event("manager.init", True, backend=self.backend,
                         launcher=self.mode, xdebug_bin=self.xdebug_bin)

    def open_session(self, name: str, fsdb: Optional[str] = None,
                     daidir: Optional[str] = None,
                     queue: Optional[str] = None, resource: Optional[str] = None,
                     run_manifest: Optional[str] = None,
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
        with self._manager_lock:
            if name in self._opening:
                return _error("SESSION_ID_EXISTS", f"session id is opening: {name}")
            if name in self.sessions:
                existing = self.sessions[name]
                if existing.state == "alive":
                    if existing.process_alive():
                        return _error("SESSION_ID_EXISTS", f"session id already exists: {name}")
                    return _error("SESSION_STALE", "session id exists but is stale: "
                                  f"{name}; close it explicitly before opening again")
            if name in self.tombstones:
                return _error("SESSION_TOMBSTONE_EXISTS",
                              f"session tombstone exists: {name}; inspect doctor and run gc or kill explicitly")
            self._opening.add(name)
        job_name = None
        actual_queue = queue or (self._session_queue if self.mode == "lsf" else None)
        actual_resource = resource or (self._session_resource if self.mode == "lsf" else None)
        if self.mode == "lsf":
            job_name = f"{self._job_prefix}_{_safe_name(self.backend)}_{_safe_name(name)}"
        log_session_event(name, "manager.open.begin", True,
                          backend=self.backend, launcher=self.mode,
                          fsdb=fsdb, daidir=daidir,
                          run_manifest=run_manifest,
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
            recovery_tool=self.recovery_tool, run_manifest=run_manifest)
        try:
            result = session.open()
        finally:
            with self._manager_lock:
                self._opening.discard(name)
        if not result.get("ok"):
            log_session_event(name, "manager.open.end", False,
                              backend=self.backend, launcher=self.mode,
                              response=result)
            return result
        with self._manager_lock:
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
        s = self.sessions.get(session) or self.tombstones.get(session)
        if not s:
            log_session_event(session, "manager.close.rejected", False,
                              backend=self.backend, launcher=self.mode,
                              error_code="SESSION_NOT_FOUND")
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        old_state = s.state
        capability = lifecycle_capability(s.backend)
        if s.state == "alive":
            rsp = s.close()
        elif capability.backend_survives_loop:
            self._evict_session(s)
            return _error(
                "SESSION_CLEANUP_REQUIRED",
                "backend may outlive its loop; use session doctor and exact session kill",
                error_layer="session_manager",
                session=s.public_json(),
            )
        else:
            rsp = s.kill()
        if not rsp.get("ok", True):
            s.state = "cleanup_partial"
            self._evict_session(s, tombstone_state=s.state)
            log_session_event(s.alias, "manager.close.end", False,
                              backend=self.backend, launcher=self.mode,
                              session_id=s.session_id, previous_state=old_state,
                              response=rsp)
            return _cleanup_failure(rsp, s)
        self._evict_session(s, tombstone_state="closed")
        log_session_event(s.alias, "manager.close.end", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, previous_state=old_state)
        return _cleanup_success(
            "close", s, rsp.get("cleanup", {}), previous_state=old_state)

    def list_sessions(self, include_tombstones: bool = False,
                      verbose: bool = False) -> Json:
        seen = set()
        rows = []
        for s in self.sessions.values():
            if id(s) in seen:
                continue
            seen.add(id(s))
            rows.append(s.public_json(verbose=verbose))
        tombstones = []
        if include_tombstones:
            seen_tombstones = set()
            for s in self.tombstones.values():
                if id(s) in seen_tombstones:
                    continue
                seen_tombstones.add(id(s))
                row = s.public_json(verbose=verbose)
                row["tombstone"] = True
                tombstones.append(row)
        log_server_event("manager.list", True, backend=self.backend,
                         launcher=self.mode, session_count=len(rows))
        return {"ok": True,
                "summary": {"active_count": len(rows),
                            "tombstone_count": len(tombstones)},
                "sessions": rows, "tombstones": tombstones}

    def _evict_session(self, s: XdebugLoopSession,
                       tombstone_state: Optional[str] = None) -> None:
        log_session_event(s.alias, "manager.evict", True,
                          backend=self.backend, launcher=self.mode,
                          session_id=s.session_id, state=s.state)
        self.sessions.pop(s.alias, None)
        if s.session_id:
            self.sessions.pop(s.session_id, None)
        for key, value in list(self.sessions.items()):
            if value is s:
                self.sessions.pop(key, None)
        if tombstone_state:
            s.state = tombstone_state
        elif s.state == "dead" and lifecycle_capability(s.backend).backend_survives_loop:
            s.state = "orphan_suspected"
        self.tombstones[s.alias] = s
        if s.session_id:
            self.tombstones[s.session_id] = s

    def doctor_session(self, session: str, verbose: bool = False) -> Json:
        s = self.sessions.get(session) or self.tombstones.get(session)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        return s.doctor(verbose=verbose)

    def kill_session(self, session: str) -> Json:
        s = self.sessions.get(session) or self.tombstones.get(session)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        rsp = s.kill()
        if rsp.get("ok"):
            self._evict_session(s, tombstone_state="closed")
            return _cleanup_success("kill", s, rsp.get("cleanup", {}))
        else:
            self._evict_session(s, tombstone_state=s.state)
            return _cleanup_failure(rsp, s)

    def gc_sessions(self, verbose: bool = False) -> Json:
        removed = []
        unresolved = []
        seen = set()
        for s in list(self.tombstones.values()):
            if id(s) in seen:
                continue
            seen.add(id(s))
            capability = lifecycle_capability(s.backend)
            removable = s.state == "closed" or (
                s.state == "dead" and not capability.backend_survives_loop)
            if removable:
                removed.append(s.public_json(verbose=verbose))
                for key, value in list(self.tombstones.items()):
                    if value is s:
                        self.tombstones.pop(key, None)
            else:
                unresolved.append(s.public_json(verbose=verbose))
        for s in list({id(value): value for value in self.sessions.values()}.values()):
            if s.state == "alive" and not s.process_alive():
                capability = lifecycle_capability(s.backend)
                if capability.backend_survives_loop:
                    unresolved.append(s.public_json(verbose=verbose))
                else:
                    s.state = "closed"
                    self._evict_session(s, tombstone_state="closed")
                    removed.append(s.public_json(verbose=verbose))
                    for key, value in list(self.tombstones.items()):
                        if value is s:
                            self.tombstones.pop(key, None)
        return {
            "ok": True,
            "summary": {
                "status": "gc_completed",
                "operation": "gc",
                "ownership": "managed",
                "backend": self.backend,
                "cleanup_complete": not unresolved,
                "removed_count": len(removed),
                "unresolved_count": len(unresolved),
            },
            "data": {"removed": removed, "unresolved": unresolved},
        }

    def session_open(self, name: str, fsdb: Optional[str] = None,
                     **kwargs: Any) -> Json:
        return self.open_session(name=name, fsdb=fsdb, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self.list_sessions(**kwargs)

    def session_close(self, session: str) -> Json:
        return self.close_session(session)

    def session_doctor(self, session: str, verbose: bool = False) -> Json:
        return self.doctor_session(session, verbose=verbose)

    def session_kill(self, session: str) -> Json:
        return self.kill_session(session)

    def session_gc(self, verbose: bool = False) -> Json:
        return self.gc_sessions(verbose=verbose)

    def close_all(self) -> Json:
        closed = []
        unresolved = []
        seen = set()
        managed = list(self.sessions.values()) + list(self.tombstones.values())
        for s in managed:
            if id(s) in seen:
                continue
            seen.add(id(s))
            try:
                if s.state == "closed":
                    closed.append(s.public_json())
                    continue
                if s.state == "alive":
                    rsp = s.close()
                else:
                    rsp = s.kill()
                if rsp.get("ok"):
                    self._evict_session(s, tombstone_state="closed")
                    closed.append(s.public_json())
                else:
                    self._evict_session(s, tombstone_state=s.state)
                    unresolved.append(s.public_json(verbose=True))
            except Exception as exc:
                try:
                    s.abort(f"manager shutdown cleanup failed: {exc}",
                            source="manager_close_all")
                finally:
                    self._evict_session(s, tombstone_state=s.state)
                    unresolved.append(s.public_json(verbose=True))
        self.sessions.clear()
        return {
            "ok": not unresolved,
            "summary": {
                "closed_count": len(closed),
                "unresolved_count": len(unresolved),
            },
            "closed": closed,
            "unresolved": unresolved,
        }
