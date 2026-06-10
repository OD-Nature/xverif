"""Terminal session error detection for xdebug loop sessions.

Distinguishes between ordinary action errors (SIGNAL_NOT_FOUND, …) that
should NOT tear down a session, and terminal session errors (SESSION_DEAD,
PROTOCOL_POISONED, …) that require immediate cleanup.
"""

from __future__ import annotations

from typing import Any, Dict

Json = Dict[str, Any]

# ---------------------------------------------------------------------------
# terminal error codes — any of these means the session is unrecoverable
# ---------------------------------------------------------------------------

TERMINAL_SESSION_ERROR_CODES = {
    "SESSION_DEAD",
    "SESSION_LOST",
    "SESSION_CLOSED",
    "SESSION_NOT_OPEN",
    "BACKEND_SESSION_DEAD",
    "BACKEND_SESSION_LOST",
    "DESIGN_CONTEXT_LOST",
    "FSDB_CONTEXT_LOST",
    "DATABASE_CONTEXT_LOST",
    "PROTOCOL_POISONED",
}

# ---------------------------------------------------------------------------
# terminal backend states — when a response carries session.state == one of
# these, we treat the session as dead.
# ---------------------------------------------------------------------------

TERMINAL_BACKEND_STATES = {
    "dead",
    "lost",
    "closed",
    "not_open",
    "poisoned",
}


def error_code(rsp: Json) -> str:
    """Extract the ``error.code`` from a (possibly nested) xdebug response."""
    err = rsp.get("error")
    if isinstance(err, dict):
        code = err.get("code")
        if isinstance(code, str):
            return code
    return ""


def _session_state_is_terminal(obj: Json) -> bool:
    session = obj.get("session")
    if isinstance(session, dict):
        state = session.get("state")
        if isinstance(state, str) and state in TERMINAL_BACKEND_STATES:
            return True
    return False


def response_says_session_terminal(rsp: Json) -> bool:
    """Check whether *any* layer of a response indicates the session is dead.

    Scans the top-level envelope, ``rsp["json"]`` (the nested xdebug reply
    inside a JSONL envelope), and ``rsp["data"]``.
    """
    if not isinstance(rsp, dict):
        return False

    candidates: list[Json] = [rsp]

    nested = rsp.get("json")
    if isinstance(nested, dict):
        candidates.append(nested)

    data = rsp.get("data")
    if isinstance(data, dict):
        candidates.append(data)

    for obj in candidates:
        if error_code(obj) in TERMINAL_SESSION_ERROR_CODES:
            return True
        if _session_state_is_terminal(obj):
            return True
        deeper = obj.get("data")
        if isinstance(deeper, dict) and _session_state_is_terminal(deeper):
            return True

    return False
