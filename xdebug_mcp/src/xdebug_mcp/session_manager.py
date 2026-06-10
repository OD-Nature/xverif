"""McpSessionManager — multi-session lifecycle for xdebug loop sessions."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from xdebug_lsf.bsub import BsubRunner

from .launchers import DirectLauncher, Launcher, LsfLauncher, default_xdebug_bin
from .loop_session import XdebugLoopSession

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


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

        # LSF session queue
        self._session_queue = os.environ.get("XDEBUG_LSF_SESSION_QUEUE", "interactive")
        self._session_resource = os.environ.get("XDEBUG_LSF_SESSION_RESOURCE")

        # Launcher
        if self.mode == "direct":
            self.launcher: Launcher = DirectLauncher()
        elif self.mode == "lsf":
            bsub_cmd = os.environ.get("XDEBUG_LSF_BSUB")
            # fake LSF support
            if os.environ.get("XDEBUG_MCP_FAKE_LSF") == "1" and not bsub_cmd:
                import sys
                bsub_cmd = f"{sys.executable} -m xdebug_lsf.fake_bsub"
            self.launcher = LsfLauncher(BsubRunner(bsub_cmd))
        else:
            raise ValueError(f"unsupported XDEBUG_MCP_BACKEND: {self.mode}")

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
        reuse: bool = True,
        reopen: bool = False,
        make_default: bool = True,
        **kwargs: Any,
    ) -> Json:
        if name in self.sessions:
            existing = self.sessions[name]
            if existing.state == "alive":
                if existing.process_alive():
                    return _error("SESSION_EXISTS", f"session already exists: {name}")
                existing.abort("stale alive session process is not running", source="stale_open")
                self._evict_session(existing)

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
            reuse=reuse,
            reopen=reopen,
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
        args: Optional[Json] = None,
        output_format: str = "xout",
        **kwargs: Any,
    ) -> Any:
        key = session or self.default_session
        if not key:
            return _error("SESSION_REQUIRED", "provide session or call xdebug_session_open first")
        s = self.sessions.get(key)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {key}")
        rsp = s.query(
            action=action,
            args=args,
            target=kwargs.get("target"),
            limits=kwargs.get("limits"),
            output=kwargs.get("output"),
            output_format=output_format,
        )
        if s.state == "dead":
            self._evict_session(s)
        return rsp

    def close_session(self, session: str) -> Json:
        s = self.sessions.get(session)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        old_state = s.state
        if s.state == "alive":
            result = s.close()
        else:
            s.abort(f"close requested for non-alive session: {old_state}", source="close_dead")
            result = {"ok": True, "closed": s.public_json(), "previous_state": old_state}
        self._evict_session(s)
        return {"ok": True, "closed": s.public_json(), "default_session": self.default_session, "previous_state": old_state}

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
    # session eviction
    # ------------------------------------------------------------------

    def _evict_session(self, s: XdebugLoopSession) -> None:
        """Remove all mappings for a dead/lost session."""
        self.sessions.pop(s.alias, None)
        if s.session_id:
            self.sessions.pop(s.session_id, None)
        for key, value in list(self.sessions.items()):
            if value is s:
                self.sessions.pop(key, None)
        if self.default_session in (s.alias, s.session_id):
            self.default_session = None

    # ------------------------------------------------------------------
    # backward-compat aliases (old server_legacy calls these)
    # ------------------------------------------------------------------

    def session_open(self, name: str, fsdb: str, **kwargs: Any) -> Json:
        return self.open_session(name=name, fsdb=fsdb, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self.list_sessions()

    def session_use(self, session: str) -> Json:
        return self.use_session(session)

    def session_close(self, session: str) -> Json:
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
