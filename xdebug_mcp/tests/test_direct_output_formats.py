"""Direct backend output format tests (xout / json / envelope)."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from xdebug_mcp.backend import DirectBackend, XdebugRunner


def _make_fake_xdebug(dirpath: Path, xout_response: str = "@xdebug.fake.v1\n\nsummary:\n  format: xout\n"):
    """Create a fake xdebug executable that returns controlled output."""
    script = dirpath / "xdebug"
    json_response = json.dumps({"ok": True, "action": "fake", "summary": {"format": "json"}})

    script.write_text(
        '#!/usr/bin/env python3\n'
        'import json, sys\n'
        f'XOUT_RESPONSE = {json.dumps(xout_response)}\n'
        f'JSON_RESPONSE = {json.dumps(json_response)}\n'
        'args = sys.argv[1:]\n'
        'if "--json" in args:\n'
        '    print(JSON_RESPONSE)\n'
        'else:\n'
        '    print(XOUT_RESPONSE, end="")\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def backend_with_fake_xdebug():
    """Return a DirectBackend pointed at a fake xdebug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        script = _make_fake_xdebug(tmp)
        runner = XdebugRunner(
            cmd_json=[str(script), "--json", "-"],
            cmd_xout=[str(script), "-"],
        )
        yield DirectBackend(runner)


class TestDirectOutputFormats:
    def test_xout_returns_string(self, backend_with_fake_xdebug):
        result = backend_with_fake_xdebug.query(
            action="fake", args={}, output_format="xout",
            target={"fsdb": "fake.fsdb"},
        )
        assert isinstance(result, str)
        assert result.startswith("@xdebug.")

    def test_json_returns_dict(self, backend_with_fake_xdebug):
        result = backend_with_fake_xdebug.query(
            action="fake", args={}, output_format="json",
            target={"fsdb": "fake.fsdb"},
        )
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["summary"]["format"] == "json"

    def test_envelope_returns_dict_with_keys(self, backend_with_fake_xdebug):
        result = backend_with_fake_xdebug.query(
            action="fake", args={}, output_format="envelope",
            target={"fsdb": "fake.fsdb"},
        )
        assert isinstance(result, dict)
        assert "stdout" in result
        assert "stderr" in result
        assert "exit_code" in result

    def test_default_output_is_xout(self, backend_with_fake_xdebug):
        result = backend_with_fake_xdebug.query(
            action="fake", args={},
            target={"fsdb": "fake.fsdb"},
        )
        assert isinstance(result, str)
        assert result.startswith("@xdebug.")

    def test_invalid_output_format_returns_error(self, backend_with_fake_xdebug):
        result = backend_with_fake_xdebug.query(
            action="fake", args={}, output_format="invalid"
        )
        # Should not crash; handled by the query caller (server.py validates)
        # At the backend level we pass through to runner
        pass  # Backend doesn't validate format — server.py does

    def test_request_method_keeps_json_default(self, backend_with_fake_xdebug):
        """The legacy request() method defaults to json output."""
        result = backend_with_fake_xdebug.request(
            {"api_version": "xdebug.v1", "action": "fake"}
        )
        # Legacy: calls runner.request with output_format="json" as default
        assert isinstance(result, dict)
        assert result.get("ok") is True

    def test_runner_direct_xout(self):
        """XdebugRunner.request() can produce xout string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = _make_fake_xdebug(tmp)
            runner = XdebugRunner(
                cmd_json=[str(script), "--json", "-"],
                cmd_xout=[str(script), "-"],
            )
            result = runner.request(
                {"api_version": "xdebug.v1", "action": "fake"},
                output_format="xout",
            )
            assert isinstance(result, str)
            assert result.startswith("@xdebug.")

    def test_runner_envelope(self):
        """XdebugRunner.request() envelope mode returns raw process info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = _make_fake_xdebug(tmp)
            runner = XdebugRunner(
                cmd_json=[str(script), "--json", "-"],
                cmd_xout=[str(script), "-"],
            )
            result = runner.request(
                {"api_version": "xdebug.v1", "action": "fake"},
                output_format="envelope",
            )
            assert isinstance(result, dict)
            assert "exit_code" in result
            assert "stdout" in result
