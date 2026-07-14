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

    def actions(self, verbose: bool = False,
                category: Optional[list[str]] = None,
                requires: Optional[list[str]] = None,
                purposes: Optional[list[str]] = None,
                keyword: Optional[str] = None) -> Json:
        args: Json = {"output": {"verbose": True}} if verbose else {}
        filters: Json = {}
        if category is not None:
            filters["category"] = category
        if requires is not None:
            filters["requires"] = requires
        if purposes is not None:
            filters["purposes"] = purposes
        if keyword is not None:
            filters["keyword"] = keyword
        if filters:
            args["filter"] = filters
        return self._one_shot({"api_version": "xdebug.v1", "action": "actions", "args": args})

    def schema(self, action: str, kind: str = "request", view: str = "mcp",
               include_examples: bool = True, language: str = "zh") -> Json:
        from xverif_mcp.schema_projection import project
        native = self._one_shot({"api_version": "xdebug.v1", "action": "schema",
                                 "args": {"action": action, "kind": kind}})
        # language currently selects the MCP-facing prose source; native JSON
        # schema stays byte-for-byte stable for CLI/stdio users.
        _ = language
        # The default MCP request view has no response equivalent.  Preserve
        # existing kind="response" discovery calls by selecting response guide
        # when callers omit an explicit view.
        effective_view = "response" if kind == "response" and view == "mcp" else view
        return project(action, kind, effective_view, native, include_examples)

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
