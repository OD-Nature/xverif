"""Verify backend wiring — XverifDebugAdapter uses McpSessionManager."""

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.sessions.session_manager import McpSessionManager


def test_backend_uses_session_manager():
    backend = XverifDebugAdapter(mode="direct")
    assert isinstance(backend._sessions, McpSessionManager)


def test_lsf_mode_rejected():
    import pytest
    from xverif_mcp.sessions.session_manager import McpSessionManager
    with pytest.raises(ValueError, match="unsupported"):
        McpSessionManager(mode="invalid")


def test_mcp_adapter_restores_its_config_after_loop_wrapper(monkeypatch):
    from xverif_loop.wrapper import LoopWrapperService
    from xverif_mcp.adapters.xcov import XverifCoverageAdapter

    wrapper = LoopWrapperService(mode="direct", xdebug_bin="xdebug", xcov_bin="xcov")
    monkeypatch.setenv("XVERIF_MCP_BACKEND", "lsf")
    debug = XverifDebugAdapter()
    cov = XverifCoverageAdapter()
    assert wrapper.mode == "direct"
    assert debug.mode == "lsf"
    assert cov.mode == "lsf"
