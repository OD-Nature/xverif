"""Unit tests for XdebugLoopSession (fake process)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from xverif_mcp.config import default_xdebug_bin
from xverif_mcp.sessions.launchers import DirectLauncher, LaunchConfig
from xverif_mcp.sessions.loop_session import XdebugLoopSession, _safe_name
from xverif_mcp.sessions.session_manager import McpSessionManager
from xverif_mcp.lsf.protocol import JsonlProcess


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_xdebug_script(tmpdir: Path) -> str:
    """Create a tiny fake xdebug that speaks the --stdio-loop protocol."""
    script = tmpdir / "fake_xdebug"
    script.write_text(r"""#!/usr/bin/env python3
import json, sys, os, time

# ready
print(json.dumps({"type":"ready","protocol":"xdebug-stdio-loop","version":1,"pid":os.getpid()}))
sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue

    rid = req.get("request_id", req.get("id", "unknown"))
    action = req.get("action", "")
    args = req.get("args", {})
    target = req.get("target", {})
    limits = req.get("limits", {})
    output = req.get("output", {})
    wants_json = output.get("format") == "json"

    if action == "stdio.quit":
        rsp = {"id": rid, "ok": True, "payload_format": "json", "json": {"ok": True, "action": "stdio.quit"}}
        print(json.dumps(rsp))
        sys.stdout.flush()
        sys.exit(0)

    if action == "session.open":
        name = args.get("name", "unknown")
        result = {
            "ok": True, "action": "session.open",
            "summary": {"session_id": name, "mode": "combined",
                        "open_args": args},
        }
    elif action == "value.at":
        delay = float(args.get("sleep", 0))
        if delay:
            time.sleep(delay)
        result = {"ok": True, "action": "value.at",
                  "summary": {"signal": args.get("signal"), "value": "1"}}
    elif action == "bad.args":
        result = {
            "ok": False,
            "action": "bad.args",
            "error": {
                "code": "INVALID_REQUEST",
                "message": "invalid parameter args.bad",
                "recoverable": True,
                "error_layer": "schema",
                "invalid_arg": "args.bad",
                "expected": "no additional properties allowed",
                "correct_example": {
                    "api_version": "xdebug.v1",
                    "action": "bad.args",
                    "target": {"session_id": "native_session"},
                    "args": {}
                }
            }
        }
    else:
        result = {"ok": True, "action": action,
                  "summary": {"echo_args": args, "echo_target": target, "echo_limits": limits}}

    if not result.get("ok"):
        if wants_json:
            rsp = {"id": rid, "ok": False, "payload_format": "json", "error": result["error"], "json": result}
        else:
            xout = "@xdebug.error.v1\naction: " + action + "\ncode: " + result["error"]["code"] + "\n"
            rsp = {"id": rid, "ok": False, "payload_format": "xout", "error": result["error"], "json": result, "xout": xout}
        print(json.dumps(rsp))
        sys.stdout.flush()
        continue

    if wants_json:
        rsp = {"id": rid, "ok": True, "payload_format": "json", "json": result}
    else:
        xout = f"@xdebug.{action}.v1\n\nsummary:\n  signal: {args.get('signal','?')}\n  value: 0x1\n"
        rsp = {"id": rid, "ok": True, "payload_format": "xout", "xout": xout}

    print(json.dumps(rsp))
    sys.stdout.flush()
""")
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def fake_xdebug_bin(tmp_path):
    return _fake_xdebug_script(tmp_path)


@pytest.fixture
def session(fake_xdebug_bin):
    s = XdebugLoopSession(
        alias="test",
        fsdb="test.fsdb",
        daidir=None,
        launcher=DirectLauncher(),
        xdebug_bin=fake_xdebug_bin,
        startup_timeout_sec=5.0,
        request_timeout_sec=5.0,
    )
    yield s
    try:
        s.close(force=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestSafeName:
    def test_basic(self):
        assert _safe_name("hello") == "hello"

    def test_special_chars(self):
        assert _safe_name("user.name") == "user_name"

    def test_empty(self):
        assert _safe_name("") == "unnamed"

    def test_max_len(self):
        long = "a" * 100
        assert len(_safe_name(long, max_len=32)) <= 32


class TestLoopSessionOpen:
    def test_open_alive(self, session):
        r = session.open()
        assert r.get("ok"), r
        assert session.state == "alive"
        assert session.session_id == "test"

    def test_open_does_not_send_reuse_or_reopen(self, fake_xdebug_bin):
        s = XdebugLoopSession(
            alias="test2", fsdb="t.fsdb", daidir=None,
            launcher=DirectLauncher(), xdebug_bin=fake_xdebug_bin,
            startup_timeout_sec=5.0, request_timeout_sec=5.0,
        )
        try:
            r = s.open()
            assert r.get("ok")
            assert s.state == "alive"
            rsp = s.query("fake", {}, output_format="json")
            assert rsp["summary"]["echo_target"]["session_id"] == "test2"
        finally:
            s.close(force=True)


class TestLoopSessionQuery:
    def test_xout_format(self, session):
        session.open()
        r = session.query("value.at", {"signal": "clk"}, output_format="xout")
        assert isinstance(r, str)
        assert r.startswith("@xdebug.")

    def test_json_format(self, session):
        session.open()
        r = session.query("value.at", {"signal": "clk"}, output_format="json")
        assert isinstance(r, dict)
        assert r.get("ok")

    def test_xout_error_uses_mcp_correct_example(self, session):
        session.open()
        r = session.query("bad.args", {"bad": True}, output_format="xout")
        assert isinstance(r, str)
        assert r.startswith("@xdebug.error.v1")
        assert "error_layer: schema" in r
        assert "xverif_debug_query" in r
        assert '"api_version"' not in r

    def test_json_error_uses_mcp_correct_example(self, session):
        session.open()
        r = session.query("bad.args", {"bad": True}, output_format="json")
        assert isinstance(r, dict)
        assert r["ok"] is False
        assert r["error"]["correct_example"]["tool"] == "xverif_debug_query"
        example_args = r["error"]["correct_example"]["args"]
        assert example_args["session_id"] == "test"
        assert example_args["action"] == "bad.args"
        assert "api_version" not in example_args

    def test_envelope_format(self, session):
        session.open()
        r = session.query("value.at", {"signal": "clk"}, output_format="envelope")
        assert isinstance(r, dict)

    def test_target_override_is_ignored(self, session):
        session.open()
        r = session.query("fake", {}, target={"fsdb": "override.fsdb"}, output_format="json")
        echo = r.get("summary", {}).get("echo_target", {})
        assert echo == {"session_id": "test"}

    def test_limits_passthrough(self, session):
        session.open()
        r = session.query("fake", {}, limits={"max_items": 42}, output_format="json")
        echo = r.get("summary", {}).get("echo_limits", {})
        assert echo.get("max_items") == 42

    def test_no_target_uses_session_id(self, session):
        session.open()
        r = session.query("fake", {}, output_format="json")
        echo = r.get("summary", {}).get("echo_target", {})
        assert echo.get("session_id") == "test"

    def test_request_lock_serial(self, session):
        """同一 session 的并发 query 应该串行执行。"""
        session.open()
        results = []
        errors = []

        def query_with_sleep():
            try:
                r = session.query("value.at", {"signal": "clk", "sleep": 0.1}, output_format="json")
                results.append(r)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=query_with_sleep)
        t2 = threading.Thread(target=query_with_sleep)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(results) == 2, f"expected 2 results, got {len(results)}; errors={errors}"
        assert all(r.get("ok") for r in results)


class TestLoopSessionClose:
    def test_close_changes_state(self, session):
        session.open()
        r = session.close()
        assert r["ok"] is True
        assert r["cleanup"]["backend_close"] == "ok"
        assert r["cleanup"]["stdio_quit"] == "ok"
        assert r["cleanup"]["terminate"] == "ok"
        assert session.state == "closed"

    def test_dead_session_query_fails(self, session):
        session.open()
        session.close()
        r = session.query("value.at", {"signal": "clk"}, output_format="json")
        assert not r.get("ok")
        assert r["error"]["code"] == "SESSION_DEAD"

    def test_close_backend_failure_reports_partial_failure(self, session, monkeypatch):
        session.open()
        original_call_raw = session._call_raw

        def fail_backend_close(req, *args, **kwargs):
            if req.get("action") == "session.close":
                raise RuntimeError("backend close failed")
            return original_call_raw(req, *args, **kwargs)

        monkeypatch.setattr(session, "_call_raw", fail_backend_close)
        r = session.close()

        assert r["ok"] is False
        assert r["error"]["code"] == "SESSION_CLEANUP_PARTIAL_FAILURE"
        assert r["error"]["cleanup"]["backend_close"] == "failed"
        assert "backend close failed" in r["error"]["cleanup"]["errors"]["backend_close"]
        assert r["error"]["cleanup"]["stdio_quit"] == "ok"
        assert r["error"]["cleanup"]["terminate"] == "ok"
        assert session.state == "alive"

    def test_close_terminate_failure_reports_partial_failure(self, fake_xdebug_bin):
        class FailingTerminateLauncher(DirectLauncher):
            def terminate(self, handle):
                raise RuntimeError("terminate failed")

        s = XdebugLoopSession(
            alias="termfail",
            fsdb="test.fsdb",
            daidir=None,
            launcher=FailingTerminateLauncher(),
            xdebug_bin=fake_xdebug_bin,
            startup_timeout_sec=5.0,
            request_timeout_sec=5.0,
        )
        try:
            assert s.open()["ok"] is True
            r = s.close()
            assert r["ok"] is False
            assert r["error"]["code"] == "SESSION_CLEANUP_PARTIAL_FAILURE"
            assert r["error"]["cleanup"]["terminate"] == "failed"
            assert "terminate failed" in r["error"]["cleanup"]["errors"]["terminate"]
            assert s.state == "alive"
        finally:
            try:
                DirectLauncher().terminate(s.handle)
            except Exception:
                pass

    def test_manager_keeps_session_after_close_partial_failure(self, fake_xdebug_bin, monkeypatch):
        manager = McpSessionManager(
            mode="direct",
            xdebug_bin=fake_xdebug_bin,
            startup_timeout_sec=5.0,
            request_timeout_sec=5.0,
        )
        assert manager.open_session("keep", fsdb="test.fsdb")["ok"] is True
        s = manager.sessions["keep"]
        original_call_raw = s._call_raw

        def fail_backend_close(req, *args, **kwargs):
            if req.get("action") == "session.close":
                raise RuntimeError("backend close failed")
            return original_call_raw(req, *args, **kwargs)

        monkeypatch.setattr(s, "_call_raw", fail_backend_close)
        r = manager.close_session("keep")

        assert r["ok"] is False
        assert r["error"]["code"] == "SESSION_CLEANUP_PARTIAL_FAILURE"
        assert manager.sessions["keep"] is s
        assert s.state == "alive"
