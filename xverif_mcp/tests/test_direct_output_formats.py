"""Output format tests for xverif-mcp one-shot requests (xout / json / envelope)."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from xverif_mcp.runner import StatelessCliRunner


def _make_fake_xdebug(dirpath: Path,
                      xout_response: str = "@xdebug.fake.v1\n\nsummary:\n  format: xout\n"):
    """Create a fake xdebug executable that returns controlled output."""
    script = dirpath / "xdebug"
    json_response = json.dumps({"ok": True, "action": "fake",
                                "summary": {"format": "json"}})
    script.write_text(
        '#!/usr/bin/env python3\n'
        'import json, sys\n'
        f'XOUT_RESPONSE = {json.dumps(xout_response)}\n'
        f'JSON_RESPONSE = {json.dumps(json_response)}\n'
        'args = sys.argv[1:]\n'
        'stdin = sys.stdin.read()\n'
        'try:\n'
        '    req = json.loads(stdin) if stdin.strip() else {}\n'
        'except Exception:\n'
        '    req = {}\n'
        'if "--json" in args or req.get("output", {}).get("format") == "json":\n'
        '    print(JSON_RESPONSE)\n'
        'else:\n'
        '    print(XOUT_RESPONSE, end="")\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def runner():
    """Return a StatelessCliRunner pointed at a fake xdebug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        script = _make_fake_xdebug(tmp)
        r = StatelessCliRunner()
        # Override tool_path to use our fake script
        orig_tool_path = r.tool_path
        r.tool_path = lambda tool: str(script)
        yield r
        r.tool_path = orig_tool_path


class TestXverifOutputFormats:
    def test_xout_returns_string(self, runner):
        result = runner.run_text("xdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "xdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@xdebug.")

    def test_json_returns_dict(self, runner):
        result = runner.run_json("xdebug", ["--json", "-"],
                                  input_text=json.dumps(
                                      {"api_version": "xdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["summary"]["format"] == "json"

    def test_default_output_is_xout(self, runner):
        result = runner.run_text("xdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "xdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@xdebug.")

    def test_invalid_output_returns_error(self):
        """Non-existent binary gives CLI_FAILED error."""
        r = StatelessCliRunner()
        result = r.run_json("nonexistent_tool", ["--help"])
        assert not result.get("ok")
        assert result["error"]["code"] == "XVERIF_CLI_FAILED"

    def test_json_keeps_json_default(self, runner):
        """run_json always returns a dict."""
        result = runner.run_json("xdebug", ["--json", "-"],
                                  input_text=json.dumps(
                                      {"api_version": "xdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, dict)
        assert result.get("ok") is True

    def test_runner_xout_text(self, runner):
        """run_text produces raw text string on success."""
        result = runner.run_text("xdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "xdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@xdebug.")

    def test_runner_error_returns_dict(self):
        """run_text returns error dict on failure."""
        r = StatelessCliRunner()
        result = r.run_text("nonexistent_binary", ["--help"])
        assert isinstance(result, dict)
        assert not result.get("ok")
        assert result["error"]["code"] == "XVERIF_CLI_FAILED"
