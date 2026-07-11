from __future__ import annotations

import pytest

from xverif_loop.wrapper import LoopWrapperService
from xverif_mcp.server import xverif_cov_query, xverif_debug_query


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


@pytest.mark.parametrize("action", ["session.open", "session.status", "session.close"])
def test_cov_query_rejects_native_session_action_with_cov_guidance(action: str) -> None:
    rsp = xverif_cov_query(session_id="cov_a", action=action, args={})
    assert rsp["ok"] is False
    error = rsp["error"]
    assert error["code"] == "NATIVE_SESSION_ACTION_FORBIDDEN"
    expected = {
        "session.open": "xverif_cov_session_open",
        "session.status": "xverif_cov_session_doctor",
        "session.close": "xverif_cov_session_close",
    }
    assert error["correct_example"]["tool"] == expected[action]
    assert "xverif_cov_query" in error["example_note"]
    assert "xverif_debug_query" not in error["example_note"]


def test_loop_wrapper_cov_query_rejects_native_session_action() -> None:
    service = LoopWrapperService(mode="direct", xdebug_bin="/bin/false", xcov_bin="/bin/false")
    rsp = service.dispatch(
        {
            "id": "q1",
            "method": "cov.query",
            "params": {"session": "cov_a", "action": "session.gc", "args": {}},
        }
    )
    assert rsp["ok"] is False
    error = rsp["error"]
    assert error["code"] == "NATIVE_SESSION_ACTION_FORBIDDEN"
    assert error["correct_example"]["tool"] == "xverif_cov_session_gc"
