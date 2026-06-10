"""Unit tests for XdebugLoopSession (fake process)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from xdebug_mcp.launchers import DirectLauncher, LaunchConfig, default_xdebug_bin
from xdebug_mcp.loop_session import XdebugLoopSession, _safe_name
from xdebug_lsf.protocol import JsonlProcess


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
        reuse = args.get("reuse", True)
        reopen = args.get("reopen", False)
        result = {
            "ok": True, "action": "session.open",
            "summary": {"session_id": name, "mode": "combined",
                        "reuse_called": reuse, "reopen_called": reopen},
        }
    elif action == "value.at":
        delay = float(args.get("sleep", 0))
        if delay:
            time.sleep(delay)
        result = {"ok": True, "action": "value.at",
                  "summary": {"signal": args.get("signal"), "value": "1"}}
    else:
        result = {"ok": True, "action": action,
                  "summary": {"echo_args": args, "echo_target": target, "echo_limits": limits}}

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

    def test_reuse_false(self, fake_xdebug_bin):
        s = XdebugLoopSession(
            alias="test2", fsdb="t.fsdb", daidir=None,
            launcher=DirectLauncher(), xdebug_bin=fake_xdebug_bin,
            reuse=False, reopen=False,
            startup_timeout_sec=5.0, request_timeout_sec=5.0,
        )
        try:
            r = s.open()
            assert r.get("ok")
            assert s.state == "alive"
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

    def test_envelope_format(self, session):
        session.open()
        r = session.query("value.at", {"signal": "clk"}, output_format="envelope")
        assert isinstance(r, dict)

    def test_target_passthrough(self, session):
        session.open()
        r = session.query("fake", {}, target={"fsdb": "override.fsdb"}, output_format="json")
        echo = r.get("summary", {}).get("echo_target", {})
        assert echo.get("fsdb") == "override.fsdb"

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
        session.close()
        assert session.state == "closed"

    def test_dead_session_query_fails(self, session):
        session.open()
        session.close()
        r = session.query("value.at", {"signal": "clk"}, output_format="json")
        assert not r.get("ok")
        assert r["error"]["code"] == "SESSION_DEAD"
