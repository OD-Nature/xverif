"""Stateless CLI runner for non-session tools (xbit, xentry, xloc, xberif, xsva)."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Union

from .config import default_tool_path, default_timeout
from .errors import cli_failed, bad_json, tool_timeout

Json = Dict[str, Any]


class StatelessCliRunner:
    def __init__(self, timeout_sec: Optional[float] = None) -> None:
        self.timeout_sec = timeout_sec or default_timeout()

    def tool_path(self, tool: str) -> str:
        return default_tool_path(tool)

    def run_json(
        self,
        tool: str,
        argv: List[str],
        input_text: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Json:
        raw = self._run_raw(tool, argv, input_text, timeout_sec, extra_env)
        if raw["exit_code"] != 0 and not raw["stdout"].strip():
            return cli_failed(tool, raw["exit_code"], raw["stdout"], raw["stderr"])
        try:
            payload = json.loads(raw["stdout"])
        except Exception:
            return bad_json(tool, raw["stdout"], raw["stderr"])
        if isinstance(payload, dict):
            return payload
        return bad_json(tool, raw["stdout"], raw["stderr"])

    def run_text(
        self,
        tool: str,
        argv: List[str],
        input_text: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Union[str, Json]:
        raw = self._run_raw(tool, argv, input_text, timeout_sec, extra_env)
        if raw["exit_code"] != 0:
            return cli_failed(tool, raw["exit_code"], raw["stdout"], raw["stderr"])
        return raw["stdout"]

    def _run_raw(
        self,
        tool: str,
        argv: List[str],
        input_text: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> dict:
        cmd = [self.tool_path(tool)] + argv
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        try:
            proc = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout_sec or self.timeout_sec,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "",
                    "stderr": f"timed out after {timeout_sec or self.timeout_sec:g}s"}
        except OSError as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr}
