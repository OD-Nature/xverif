"""Stateful xdebug adapter for design/wave sessions."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from xverif_mcp.config import (default_xdebug_bin, mcp_backend,
                                startup_timeout, request_timeout)
from xverif_mcp.sessions.session_manager import McpSessionManager
from xverif_loop.config import configure_mcp_environment
from xverif_loop.logging import configure_mcp_logging

Json = Dict[str, Any]


class XverifDebugAdapter:
    def __init__(self, mode: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None) -> None:
        configure_mcp_environment()
        configure_mcp_logging()
        if startup_timeout_sec is None:
            startup_timeout_sec = startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = request_timeout()
        self.mode = mode or mcp_backend()
        self._sessions = McpSessionManager(
            mode=self.mode, xdebug_bin=default_xdebug_bin(),
            startup_timeout_sec=startup_timeout_sec,
            request_timeout_sec=request_timeout_sec)

    def ping(self) -> str:
        return "pong"

    def actions(self, verbose: bool = False) -> Json:
        args: Json = {"output": {"verbose": True}} if verbose else {}
        return self._one_shot({"api_version": "xdebug.v1", "action": "actions", "args": args})

    def schema(self, action: str, kind: str = "request") -> Json:
        return self._one_shot({"api_version": "xdebug.v1", "action": "schema",
                               "args": {"action": action, "kind": kind}})

    def _one_shot(self, req: Json) -> Json:
        from xverif_mcp.runner import StatelessCliRunner
        req = dict(req)
        return StatelessCliRunner().run_json("xdebug", ["--json", "-"],
                                              json.dumps(req))

    def session_open(self, name: str, **kwargs: Any) -> Json:
        return self._sessions.open_session(name=name, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self._sessions.list_sessions(**kwargs)

    def session_close(self, key: str) -> Json:
        return self._sessions.close_session(key)

    def session_doctor(self, key: str, verbose: bool = False) -> Json:
        return self._sessions.doctor_session(key, verbose=verbose)

    def session_kill(self, key: str) -> Json:
        return self._sessions.kill_session(key)

    def session_gc(self, verbose: bool = False) -> Json:
        return self._sessions.gc_sessions(verbose=verbose)

    def close_all(self) -> None:
        self._sessions.close_all()

    def query(self, **kwargs: Any) -> Any:
        return self._sessions.query(**kwargs)
