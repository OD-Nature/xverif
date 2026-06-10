"""Verify backend wiring — XDebugMcpBackend uses McpSessionManager."""

from xdebug_mcp.backend import XDebugMcpBackend
from xdebug_mcp.session_manager import McpSessionManager


def test_backend_uses_session_manager():
    backend = XDebugMcpBackend(mode="direct")
    assert isinstance(backend._sessions, McpSessionManager)


def test_lsf_mode_rejected():
    import pytest
    from xdebug_mcp.session_manager import McpSessionManager
    with pytest.raises(ValueError, match="unsupported"):
        McpSessionManager(mode="invalid")
