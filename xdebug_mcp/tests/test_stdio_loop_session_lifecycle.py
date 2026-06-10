"""Lifecycle tests for XdebugLoopSession failure handling (fake process).

Verifies:
- open failure when process exits before ready
- query failure when process crashes mid-request
- backend SESSION_DEAD → SESSION_LOST
- ordinary errors do NOT tear down session
- stale alive open recovery
- reopen after SESSION_LOST
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from xdebug_mcp.launchers import DirectLauncher
from xdebug_mcp.loop_session import XdebugLoopSession
from xdebug_mcp.session_manager import McpSessionManager
from xdebug_lsf.protocol import JsonlProcess


# ---------------------------------------------------------------------------
# fake --stdio-loop scripts
# ---------------------------------------------------------------------------


def _make_fake_script(path: Path, lines: list[str]) -> str:
    path.write_text("#!/usr/bin/env python3\n" + "\n".join(lines) + "\n")
    path.chmod(0o755)
    return str(path)


def _fake_loop_script(dirpath: Path, fail_open: bool = False, fail_query: bool = False) -> str:
    return _make_fake_script(dirpath / "fake_xdebug", [
        "import json, sys, os",
        "",
        f"_fail_open = {fail_open}",
        f"_fail_query = {fail_query}",
        "",
        "if _fail_open:",
        '    sys.stderr.write("fake xdebug exiting before ready")',
        "    sys.exit(1)",
        "",
        'print(json.dumps({"type":"ready","protocol":"xdebug-stdio-loop","version":1,"pid":os.getpid()}))',
        "sys.stdout.flush()",
        "",
        "_handled_open = False",
        "",
        "for line in sys.stdin:",
        "    line = line.strip()",
        "    if not line: continue",
        "    try: req = json.loads(line)",
        "    except Exception: continue",
        '    rid = req.get("request_id", req.get("id", "unknown"))',
        '    action = req.get("action", "")',
        "",
        '    if action == "session.open":',
        "        _handled_open = True",
        "",
        '    if action == "stdio.quit":',
        "        sys.exit(0)",
        "",
        '    if _fail_query and _handled_open and action != "session.open":',
        '        sys.stderr.write("fake xdebug crashing")',
        "        sys.exit(1)",
        "",
        '    wants_json = req.get("output", {}).get("format") == "json"',
        "    if wants_json:",
        '        result = {"ok": True, "action": action, "summary": {"echo": action}}',
        '        rsp = {"id": rid, "ok": True, "payload_format": "json", "json": result}',
        "    else:",
        '        xout = "@xdebug." + action + ".v1\\n"',
        '        rsp = {"id": rid, "ok": True, "payload_format": "xout", "xout": xout}',
        "    print(json.dumps(rsp))",
        "    sys.stdout.flush()",
    ])


def _fake_loop_dead_session(dirpath: Path) -> str:
    return _make_fake_script(dirpath / "fake_dead", [
        "import json, sys, os",
        "",
        'print(json.dumps({"type":"ready","protocol":"xdebug-stdio-loop","version":1,"pid":os.getpid()}))',
        "sys.stdout.flush()",
        "",
        "for line in sys.stdin:",
        "    line = line.strip()",
        "    if not line: continue",
        "    try: req = json.loads(line)",
        "    except Exception: continue",
        '    rid = req.get("request_id", req.get("id", "unknown"))',
        '    action = req.get("action", "")',
        "",
        '    if action == "stdio.quit":',
        "        sys.exit(0)",
        '    if action == "session.open":',
        '        result = {"ok": True, "action": "session.open",',
        '                  "summary": {"session_id": "dead_test", "mode": "combined"}}',
        '        rsp = {"id": rid, "ok": True, "payload_format": "json", "json": result}',
        "    else:",
        '        rsp = {"id": rid, "ok": False,',
        '               "error": {"code": "SESSION_DEAD", "message": "backend session is dead"}}',
        "    print(json.dumps(rsp))",
        "    sys.stdout.flush()",
    ])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _new_session(fake_bin: str, alias: str = "test") -> XdebugLoopSession:
    return XdebugLoopSession(
        alias=alias, fsdb="t.fsdb", daidir=None,
        launcher=DirectLauncher(), xdebug_bin=fake_bin,
        startup_timeout_sec=3.0, request_timeout_sec=3.0,
    )


def _cleanup(s: XdebugLoopSession):
    try:
        if s.state == "alive":
            s.close()
        else:
            s.abort("test cleanup", source="test")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestOpenFailure:
    def test_exit_before_ready(self, tmp_path):
        fake = _fake_loop_script(tmp_path, fail_open=True)
        s = _new_session(fake)
        r = s.open()
        assert not r.get("ok"), r
        assert r["error"]["code"] == "SESSION_OPEN_FAILED"
        assert s.state == "dead"
        assert s.process_alive() is False

    def test_no_session_after_failure(self, tmp_path):
        fake = _fake_loop_script(tmp_path, fail_open=True)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake
        r = mgr.open_session("doomed", fsdb="test.fsdb")
        assert not r.get("ok")
        assert "doomed" not in mgr.sessions


class TestQueryFailure:
    def test_crash_mid_query(self, tmp_path):
        fake = _fake_loop_script(tmp_path, fail_query=True)
        s = _new_session(fake)
        s.open()
        assert s.state == "alive"

        r = s.query("value.at", {"signal": "x"})
        assert not r.get("ok"), r
        assert r["error"]["code"] == "SESSION_LOST"
        assert r["error"]["terminal_source"] in ("transport", "unexpected")
        assert s.state == "dead"


class TestBackendSessionDead:
    def test_backend_returns_session_dead(self, tmp_path):
        fake = _fake_loop_dead_session(tmp_path)
        s = _new_session(fake)
        s.open()
        assert s.state == "alive"

        r = s.query("value.at", {"signal": "x"}, output_format="json")
        assert not r.get("ok")
        assert r["error"]["code"] == "SESSION_LOST"
        assert r["error"]["terminal_source"] == "backend_response"
        assert r["error"]["backend_response"] is not None
        assert s.state == "dead"


class TestOrdinaryError:
    def test_signal_not_found_preserves_session(self, tmp_path):
        fake = _fake_loop_script(tmp_path)
        s = _new_session(fake)
        s.open()

        # Simulate a non-terminal error by monkey-patching _call_raw
        def fake_call_raw(req, timeout=None):
            return {
                "id": req["request_id"],
                "ok": False,
                "error": {"code": "SIGNAL_NOT_FOUND", "message": "nope"},
            }
        orig = s._call_raw
        s._call_raw = fake_call_raw
        try:
            r = s.query("value.at", {"signal": "x"}, output_format="json")
            assert not r.get("ok")
            assert r["error"]["code"] == "SIGNAL_NOT_FOUND"
            assert s.state == "alive"
        finally:
            s._call_raw = orig


class TestManagerEvict:
    def test_dead_session_evicted_after_query(self, tmp_path):
        fake = _fake_loop_dead_session(tmp_path)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake
        mgr.open_session("evict_me", fsdb="test.fsdb")
        assert "evict_me" in mgr.sessions

        r = mgr.query("evict_me", "value.at", {"signal": "x"}, output_format="json")
        assert "SESSION_LOST" in str(r)
        assert "evict_me" not in mgr.sessions
        assert mgr.default_session is None

    def test_stale_alive_recovery(self, tmp_path):
        fake = _fake_loop_script(tmp_path)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake

        # First open
        mgr.open_session("stale_test", fsdb="test.fsdb")
        s = mgr.sessions["stale_test"]
        # Kill the process underneath
        s.handle.terminate()
        time.sleep(0.5)
        assert not s.process_alive()
        # Still marked alive in manager
        assert s.state == "alive"

        # Reopen same name — should succeed
        r = mgr.open_session("stale_test", fsdb="test.fsdb")
        assert r.get("ok"), r
        assert mgr.sessions["stale_test"].process_alive()

    def test_close_dead_session(self, tmp_path):
        fake = _fake_loop_script(tmp_path)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake
        mgr.open_session("close_me", fsdb="test.fsdb")
        s = mgr.sessions["close_me"]
        s.handle.terminate()
        s.state = "dead"

        r = mgr.close_session("close_me")
        assert r.get("ok"), r
        assert "close_me" not in mgr.sessions
        assert r.get("previous_state") == "dead"


class TestReopenAfterLost:
    def test_reopen_after_session_lost(self, tmp_path):
        fake = _fake_loop_dead_session(tmp_path)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake

        mgr.open_session("reopen_me", fsdb="test.fsdb")
        mgr.query("reopen_me", "value.at", {"signal": "x"}, output_format="json")
        assert "reopen_me" not in mgr.sessions

        # Now create a working fake and reopen
        fake2 = _fake_loop_script(tmp_path)
        mgr.xdebug_bin = fake2
        r = mgr.open_session("reopen_me", fsdb="test.fsdb")
        assert r.get("ok"), r
        assert "reopen_me" in mgr.sessions


class TestXoutFormatOnLost:
    def test_session_lost_in_json_even_with_xout_default(self, tmp_path):
        """When output_format=xout but session is dead, error still returns as dict."""
        s = _new_session(_fake_loop_script(tmp_path))
        r = s.query("value.at", {"signal": "x"})
        # Session not opened — should return dict error, not string
        assert isinstance(r, dict)
        assert not r.get("ok")
        assert r["error"]["code"] == "SESSION_DEAD"


# ---------------------------------------------------------------------------
# timeout helpers
# ---------------------------------------------------------------------------


def _fake_slow_script(dirpath: Path) -> str:
    """Fake xdebug that sleeps forever on any query (triggering timeout)."""
    return _make_fake_script(dirpath / "fake_slow", [
        "import json, sys, os, time",
        "",
        'print(json.dumps({"type":"ready","protocol":"xdebug-stdio-loop","version":1,"pid":os.getpid()}))',
        "sys.stdout.flush()",
        "",
        "for line in sys.stdin:",
        "    line = line.strip()",
        "    if not line: continue",
        "    try: req = json.loads(line)",
        "    except Exception: continue",
        '    rid = req.get("request_id", req.get("id", "unknown"))',
        '    action = req.get("action", "")',
        "",
        '    if action == "stdio.quit":',
        "        sys.exit(0)",
        "",
        '    if action == "session.open":',
        '        result = {"ok": True, "action": "session.open",',
        '                  "summary": {"session_id": "slow_test", "mode": "combined"}}',
        '        rsp = {"id": rid, "ok": True, "payload_format": "json", "json": result}',
        "        print(json.dumps(rsp))",
        "        sys.stdout.flush()",
        "    else:",
        "        # Sleep long enough to trigger timeout",
        "        time.sleep(99999)",
    ])


class TestTimeoutSessionLost:
    """Verify that query timeout results in SESSION_LOST and manager eviction."""

    def test_timeout_during_query(self, tmp_path):
        fake = _fake_slow_script(tmp_path)
        mgr = McpSessionManager(mode="direct")
        mgr.xdebug_bin = fake
        mgr.request_timeout_sec = 0.5  # short timeout

        r = mgr.open_session("slow", fsdb="test.fsdb")
        assert r.get("ok"), r
        assert "slow" in mgr.sessions
        assert mgr.sessions["slow"].state == "alive"

        # This query will timeout because fake script sleeps forever
        r = mgr.query("slow", "value.at", {"signal": "x"}, output_format="json")
        assert not r.get("ok"), r
        assert r["error"]["code"] == "SESSION_LOST"
        assert r["error"]["terminal_source"] == "transport"

        # Manager must have evicted the dead session
        assert "slow" not in mgr.sessions
        assert mgr.default_session is None
