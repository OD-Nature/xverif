from __future__ import annotations

from xverif_loop.wrapper import LoopWrapperService
from xverif_mcp.server import xverif_debug_query


def test_debug_query_rejects_native_session_action() -> None:
    rsp = xverif_debug_query(session_id="case_a", action="session.close", args={})
    assert rsp["ok"] is False
    error = rsp["error"]
    assert error["code"] == "NATIVE_SESSION_ACTION_FORBIDDEN"
    assert error["error_layer"] == "wrapper"
    assert error["correct_example"]["tool"] == "xverif_debug_session_close"


def test_loop_wrapper_rejects_native_session_action() -> None:
    service = LoopWrapperService(mode="direct", xdebug_bin="/bin/false", xcov_bin="/bin/false")
    rsp = service.dispatch(
        {
            "id": "q0",
            "method": "debug.query",
            "params": {"session": "case_a", "action": "session.open", "args": {}},
        }
    )
    assert rsp["ok"] is False
    error = rsp["error"]
    assert error["code"] == "NATIVE_SESSION_ACTION_FORBIDDEN"
    assert error["error_layer"] == "wrapper"
    assert error["correct_example"]["tool"] == "xverif_debug_session_open"
