from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .backend import CoverageBackend, FakeCoverageBackend, NpiCoverageBackend
from .errors import XcovError
from .logging import log_lifecycle_event

Json = Dict[str, Any]


@dataclass
class XcovSession:
    session_id: str
    vdb: str
    backend: CoverageBackend
    worker: str
    state: str = "alive"

    def close(self) -> None:
        self.backend.close()
        self.state = "closed"

    def public_json(self) -> Json:
        summary = self.backend.summary()
        return {
            "session_id": self.session_id,
            "state": self.state,
            "vdb": self.vdb,
            "test_count": summary.get("test_count", 0),
            "top_scope_count": summary.get("top_scope_count", 0),
            "worker": self.worker,
        }


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, XcovSession] = {}

    def open(self, vdb: str, name: Optional[str] = None, fake: bool = False,
             reuse: bool = True, reopen: bool = False) -> XcovSession:
        sid = name or "cov0"
        if sid in self.sessions and self.sessions[sid].state == "alive":
            if reopen:
                log_lifecycle_event(sid, "session.open.reopen", True, {"vdb": vdb})
                self.sessions[sid].close()
            elif reuse:
                log_lifecycle_event(sid, "session.open.reuse", True, {"vdb": vdb})
                return self.sessions[sid]
            else:
                log_lifecycle_event(sid, "session.open.exists", False, {"vdb": vdb})
                raise XcovError("SESSION_EXISTS", "session already exists", session_id=sid)
        log_lifecycle_event(sid, "session.open.begin", True, {"vdb": vdb, "fake": fake})
        if fake or vdb == "fake":
            backend: CoverageBackend = FakeCoverageBackend(vdb)
            worker = "fake"
        else:
            backend = NpiCoverageBackend(vdb)
            worker = "npi_python"
        sess = XcovSession(session_id=sid, vdb=vdb, backend=backend, worker=worker)
        self.sessions[sid] = sess
        log_lifecycle_event(sid, "session.open.ok", True, {"vdb": vdb, "worker": worker})
        return sess

    def get(self, session_id: str) -> XcovSession:
        sess = self.sessions.get(session_id)
        if not sess or sess.state != "alive":
            raise XcovError("SESSION_NOT_FOUND", "coverage session not found",
                            session_id=session_id)
        return sess

    def close(self, session_id: str) -> XcovSession:
        sess = self.get(session_id)
        log_lifecycle_event(session_id, "session.close.begin", True, {"vdb": sess.vdb})
        sess.close()
        self.sessions.pop(session_id, None)
        log_lifecycle_event(session_id, "session.close.ok", True, {"vdb": sess.vdb})
        return sess
