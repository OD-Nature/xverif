"""Unified config / path resolution for xverif-mcp."""
from __future__ import annotations

import os


def repo_root() -> str:
    return os.environ.get("XVERIF_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../..")
    )


def default_xdebug_bin() -> str:
    return os.path.join(repo_root(), "tools", "xdebug")


def default_tool_path(tool: str) -> str:
    return os.path.join(repo_root(), "tools", tool)


def mcp_backend() -> str:
    return os.environ.get("XVERIF_MCP_BACKEND", "direct")


def enable_write() -> bool:
    return os.environ.get("XVERIF_MCP_ENABLE_WRITE", "0") == "1"


def default_timeout() -> float:
    return float(os.environ.get("XVERIF_MCP_TIMEOUT_SEC", "120"))
