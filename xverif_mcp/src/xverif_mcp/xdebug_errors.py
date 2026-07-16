"""Compatibility exports for MCP callers.

The canonical response-shaping implementation lives in :mod:`xverif_loop` so
the SDK-free loop layer remains independently importable.
"""

from xverif_loop.xdebug_errors import (  # noqa: F401
    FORBIDDEN_NATIVE_SESSION_ACTIONS,
    forbidden_native_session_error,
    is_forbidden_native_session_action,
    translate_native_example_for_query,
    xout_error,
)

__all__ = [
    "FORBIDDEN_NATIVE_SESSION_ACTIONS",
    "forbidden_native_session_error",
    "is_forbidden_native_session_action",
    "translate_native_example_for_query",
    "xout_error",
]
