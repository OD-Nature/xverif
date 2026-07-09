"""Stateful xdebug adapter for design/wave sessions."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from xverif_mcp.config import (default_xdebug_bin, mcp_backend,
                                startup_timeout, request_timeout)
from xverif_mcp.sessions.session_manager import McpSessionManager

Json = Dict[str, Any]


class XverifDebugAdapter:
    def __init__(self, mode: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None) -> None:
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

    def actions(self) -> Json:
        return self._one_shot({"api_version": "xdebug.v1", "action": "actions"})

    def schema(self, action: str, kind: str = "request") -> Json:
        return self._one_shot({"api_version": "xdebug.v1", "action": "schema",
                               "args": {"action": action, "kind": kind}})

    def request(self, request: dict, output_format: str = "json") -> Any:
        from xverif_mcp.runner import StatelessCliRunner
        runner = StatelessCliRunner()
        req = dict(request)
        req.setdefault("api_version", "xdebug.v1")
        req.setdefault("output", {})
        wants_json = output_format in ("json", "envelope")
        if isinstance(req["output"], dict):
            if wants_json:
                req["output"].setdefault("format", "json")
            else:
                req["output"].pop("format", None)
        raw = runner._run_raw("xdebug", ["-"], json.dumps(req))
        if output_format == "xout":
            if raw["exit_code"] != 0:
                if raw["stdout"].lstrip().startswith("@xdebug."):
                    return raw["stdout"]
                from xverif_mcp.errors import cli_failed
                return cli_failed("xdebug", raw["exit_code"], raw["stdout"],
                                  raw["stderr"])
            return raw["stdout"]
        try:
            payload = json.loads(raw["stdout"])
        except Exception:
            return {"ok": False, "error": {"code": "BAD_JSON",
                                            "message": raw["stdout"],
                                            "stderr": raw["stderr"]}}
        return payload

    def _one_shot(self, req: Json) -> Json:
        from xverif_mcp.runner import StatelessCliRunner
        req = dict(req)
        req.setdefault("output", {})
        if isinstance(req["output"], dict):
            req["output"]["format"] = "json"
        return StatelessCliRunner().run_json("xdebug", ["--json", "-"],
                                              json.dumps(req))

    def session_open(self, name: str, **kwargs: Any) -> Json:
        return self._sessions.open_session(name=name, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self._sessions.list_sessions()

    def session_close(self, key: str) -> Json:
        return self._sessions.close_session(key)

    def close_all(self) -> None:
        self._sessions.close_all()

    def query(self, **kwargs: Any) -> Any:
        return self._sessions.query(**kwargs)
