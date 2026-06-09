"""McpSessionManager — multi-session lifecycle for xdebug loop sessions."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from xdebug_lsf.bsub import BsubRunner

from .launchers import DirectLauncher, Launcher, LsfLauncher, default_xdebug_bin
from .loop_session import XdebugLoopSession

Json = Dict[str, Any]


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _error(code: str, message: str) -> Json:
    return {"ok": False, "error": {"code": code, "message": message}}


class McpSessionManager:
    def __init__(
        self,
        mode: Optional[str] = None,
        xdebug_bin: Optional[str] = None,
        startup_timeout_sec: float = 60.0,
        request_timeout_sec: float = 120.0,
    ) -> None:
        self.mode = mode or os.environ.get("XDEBUG_MCP_BACKEND", "direct")
        self.xdebug_bin = xdebug_bin or default_xdebug_bin()
        self.startup_timeout_sec = startup_timeout_sec
        self.request_timeout_sec = request_timeout_sec

        # Queues (LSF only)
        self._router_queue = os.environ.get("XDEBUG_LSF_ROUTER_QUEUE", "interactive")
        self._session_queue = os.environ.get("XDEBUG_LSF_SESSION_QUEUE", "interactive")
        self._session_resource = os.environ.get("XDEBUG_LSF_SESSION_RESOURCE")

        # Launcher
        if self.mode == "lsf":
            bsub_cmd = os.environ.get("XDEBUG_LSF_BSUB")
            # fake LSF support
            if os.environ.get("XDEBUG_MCP_FAKE_LSF") == "1" and not bsub_cmd:
                import sys
                bsub_cmd = f"{sys.executable} -m xdebug_lsf.fake_bsub"
            self.launcher: Launcher = LsfLauncher(BsubRunner(bsub_cmd))
        else:
            self.launcher = DirectLauncher()

        # Stable job prefix (LSF only)
        import getpass
        import uuid as _uuid
        self._job_prefix = f"xdebug_{_safe_name(getpass.getuser())}_{os.getpid()}_{_uuid.uuid4().hex[:8]}"

        self.sessions: Dict[str, XdebugLoopSession] = {}
        self.default_session: Optional[str] = None

    # ------------------------------------------------------------------
    # session lifecycle
    # ------------------------------------------------------------------

    def open_session(
        self,
        name: str,
        fsdb: str,
        daidir: Optional[str] = None,
        queue: Optional[str] = None,
        resource: Optional[str] = None,
        make_default: bool = True,
    ) -> Json:
        if name in self.sessions:
            existing = self.sessions[name]
            if existing.state == "alive":
                return _error("SESSION_EXISTS", f"session already exists: {name}")

        job_name = None
        actual_queue = queue or (self._session_queue if self.mode == "lsf" else None)
        actual_resource = resource or (self._session_resource if self.mode == "lsf" else None)
        if self.mode == "lsf":
            job_name = f"{self._job_prefix}_sess_{_safe_name(name)}"

        session = XdebugLoopSession(
            alias=name,
            fsdb=fsdb,
            daidir=daidir,
            launcher=self.launcher,
            xdebug_bin=self.xdebug_bin,
            queue=actual_queue,
            resource=actual_resource,
            job_name=job_name,
            startup_timeout_sec=self.startup_timeout_sec,
            request_timeout_sec=self.request_timeout_sec,
        )

        result = session.open()
        if not result.get("ok"):
            return result

        self.sessions[name] = session
        if session.session_id:
            self.sessions[session.session_id] = session
        if make_default or not self.default_session:
            self.default_session = session.session_id or name

        return {
            "ok": True,
            "session": session.public_json(),
            "default_session": self.default_session,
        }

    def query(
        self,
        session: Optional[str],
        action: str,
        args: Optional[Json],
        output_format: str,
    ) -> Any:
        key = session or self.default_session
        if not key:
            return _error("SESSION_REQUIRED", "provide session or call xdebug_session_open first")
        s = self.sessions.get(key)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {key}")
        return s.query(action, args, output_format)

    def close_session(self, session: str) -> Json:
        s = self.sessions.get(session)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        result = s.close()
        self.sessions.pop(s.alias, None)
        if s.session_id:
            self.sessions.pop(s.session_id, None)
        if self.default_session in (s.alias, s.session_id):
            self.default_session = None
        return {"ok": True, "closed": s.public_json(), "default_session": self.default_session}

    def list_sessions(self) -> Json:
        seen = set()
        rows = []
        for s in self.sessions.values():
            if id(s) in seen:
                continue
            seen.add(id(s))
            rows.append(s.public_json())
        return {"ok": True, "sessions": rows, "default_session": self.default_session}

    def use_session(self, key: str) -> Json:
        s = self.sessions.get(key)
        if not s or s.state != "alive":
            return _error("SESSION_NOT_FOUND", f"session not alive: {key}")
        self.default_session = s.session_id or s.alias
        return {"ok": True, "default_session": self.default_session, "session": s.public_json()}

    # ------------------------------------------------------------------
    # backward-compat aliases (old server_legacy calls these)
    # ------------------------------------------------------------------

    def session_open(self, name, **kwargs):
        return self.open_session(name, **kwargs)

    def session_list(self, **kwargs):
        return self.list_sessions()

    def session_use(self, session):
        return self.use_session(session)

    def session_close(self, session):
        return self.close_session(session)

    # ------------------------------------------------------------------
    # cleanup
    # ------------------------------------------------------------------

    def close_all(self) -> None:
        for s in list(self.sessions.values()):
            try:
                s.close(force=True)
            except Exception:
                pass
        self.sessions.clear()
        self.default_session = None
