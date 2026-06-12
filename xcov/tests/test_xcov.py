from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from xcov.actions import Dispatcher
from xcov.backend import CoverageBackend
from xcov.logging import sanitize_for_log
from xcov.schemas import schema_actions
from xcov.session import XcovSession

ROOT = Path(__file__).resolve().parents[2]
XCOV = ROOT / "tools" / "xcov"


def _run(req: dict) -> dict:
    req.setdefault("output", {})["response_format"] = "json"
    proc = subprocess.run([str(XCOV), "--json", "-"], input=json.dumps(req),
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout)


def _run_proc(req: dict, args: list[str] | None = None, env: dict | None = None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run([str(XCOV), *(args or ["-"])], input=json.dumps(req),
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=merged_env)


def _read_last_json_line(path: Path) -> dict:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    return json.loads(lines[-1])


def test_cli_json_flag_outputs_json_not_xout(tmp_path):
    proc = _run_proc({
        "api_version": "xcov.v1",
        "request_id": "actions",
        "action": "actions",
    }, ["--json", "-"], {"XVERIF_XCOV_LOG_DIR": str(tmp_path / "logs")})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.lstrip().startswith("{")
    assert "XOUT_BEGIN" not in proc.stdout
    assert json.loads(proc.stdout)["ok"] is True


def test_output_response_format_json_outputs_json(tmp_path):
    proc = _run_proc({
        "api_version": "xcov.v1",
        "request_id": "actions",
        "action": "actions",
        "output": {"response_format": "json"},
    }, ["-"], {"XVERIF_XCOV_LOG_DIR": str(tmp_path / "logs")})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.lstrip().startswith("{")
    assert "XOUT_BEGIN" not in proc.stdout


def test_session_open_fake_json():
    rsp = _run({
        "api_version": "xcov.v1",
        "request_id": "open",
        "action": "session.open",
        "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["session_id"] == "cov0"
    assert rsp["summary"]["worker"] == "fake"


def test_schema_registry_covers_all_p0_actions():
    dispatcher = Dispatcher()
    for action in schema_actions():
        rsp = dispatcher.dispatch({
            "api_version": "xcov.v1",
            "request_id": f"schema-{action}",
            "action": "schema",
            "args": {"action": action},
            "output": {"response_format": "json"},
        })
        assert rsp["ok"] is True, action
        schema = rsp["data"]["schema"]
        assert schema["properties"]["action"]["const"] == action


def test_schema_required_fields_are_action_specific():
    dispatcher = Dispatcher()
    source = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "schema-source",
        "action": "schema", "args": {"action": "source.map"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    session_open = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "schema-open",
        "action": "schema", "args": {"action": "session.open"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    object_get = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "schema-object",
        "action": "schema", "args": {"action": "cov.object.get"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    assert set(source["properties"]["args"]["required"]) == {"file", "line"}
    assert session_open["properties"]["target"]["required"] == ["vdb"]
    assert object_get["properties"]["args"]["required"] == ["name"]


def test_logging_sanitize_omits_heavy_fields():
    sanitized = sanitize_for_log({"data": {"items": [{"x": i} for i in range(100)]},
                                  "small": True})
    assert sanitized["data"] == "<omitted:large-field>"
    assert sanitized["small"] is True
    assert sanitized["log_truncated"] is True


def test_stdio_loop_fake_holes():
    lines = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "holes",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"metrics": ["toggle", "branch"]}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in lines) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert out[0]["protocol"] == "xcov-stdio-loop"
    assert out[2]["id"] == "holes"
    assert out[2]["ok"] is True
    assert "@xcov.v1 ok action=cov.holes" in out[2]["xout"]
    assert out[2]["json"]["summary"]["matched_count"] == 2


def test_logging_writes_action_manifest_lifecycle_and_transport(tmp_path):
    log_dir = tmp_path / "xcov_logs"
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "holes",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"metrics": ["toggle"]}},
        {"api_version": "xcov.v1", "request_id": "close",
         "action": "session.close", "target": {"session_id": "cov0"}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT),
                          env={**os.environ, "XVERIF_XCOV_LOG_DIR": str(log_dir)})
    assert proc.returncode == 0
    action_log = log_dir / "sessions" / "cov0" / "logs" / "actions.ndjson"
    manifest = log_dir / "sessions" / "cov0" / "session.json"
    lifecycle = log_dir / "backend" / "sessions" / "cov0" / "logs" / "lifecycle.ndjson"
    transport = log_dir / "backend" / "sessions" / "cov0" / "logs" / "transport.ndjson"
    assert action_log.exists()
    assert manifest.exists()
    assert lifecycle.exists()
    assert transport.exists()
    assert _read_last_json_line(action_log)["component"] == "xcov"
    assert json.loads(manifest.read_text(encoding="utf-8"))["session_id"] == "cov0"


def test_logging_can_be_disabled(tmp_path):
    log_dir = tmp_path / "disabled_logs"
    proc = _run_proc({
        "api_version": "xcov.v1",
        "request_id": "open",
        "action": "session.open",
        "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
    }, ["--json", "-"], {"XVERIF_XCOV_LOG_DIR": str(log_dir), "XVERIF_XCOV_LOG": "0"})
    assert proc.returncode == 0
    assert not log_dir.exists()


def test_regex_rejected():
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "bad",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"query": {"include_patterns": ["^top.*"]}}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert out[2]["ok"] is False
    assert out[2]["json"]["error"]["code"] == "REGEX_NOT_SUPPORTED"


def test_export_writes_file(tmp_path):
    path = tmp_path / "holes.ndjson"
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "export",
         "action": "export.holes", "target": {"session_id": "cov0"},
         "args": {"output": {"mode": "file", "artifact_format": "ndjson",
                              "path": str(path), "allow_absolute_path": True}}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    assert proc.returncode == 0
    assert path.exists()
    assert "npiCovToggleBin" in path.read_text()


def _dispatch_opened() -> Dispatcher:
    dispatcher = Dispatcher()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "open",
        "action": "session.open", "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    return dispatcher


def test_top_level_limits_output_are_merged_for_mcp_queries():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "holes",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["toggle", "branch"]},
        "limits": {"max_items": 1},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 2
    assert rsp["summary"]["returned"] == 1


def test_args_limits_take_precedence_over_top_level_limits():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "holes",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["toggle", "branch"], "limits": {"max_items": 2}},
        "limits": {"max_items": 1},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["returned"] == 2


def test_scope_summary_returns_one_requested_scope():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "scope",
        "action": "scope.summary", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    item = rsp["data"]["items"][0]
    assert item["full_name"] == "top.u_dut"
    assert item["coverable"] == 4


def test_scope_children_direct_vs_recursive():
    dispatcher = _dispatch_opened()
    direct = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "children",
        "action": "scope.children", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
        "output": {"format": "json"},
    })
    recursive = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "children-rec",
        "action": "scope.children", "target": {"session_id": "cov0"},
        "args": {"scope": "top", "recursive": True},
        "output": {"format": "json"},
    })
    assert {i["full_name"] for i in direct["data"]["items"]} == {
        "top.u_dut.u_ctrl", "top.u_dut.u_fifo"
    }
    assert "top.u_dut.u_fifo" in {i["full_name"] for i in recursive["data"]["items"]}


def test_scope_search_does_not_enrich_coverage():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "search",
        "action": "scope.search", "target": {"session_id": "cov0"},
        "args": {"query": {"include_patterns": ["*u_fifo"], "match_fields": ["full_name"]}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["data"]["items"][0]["full_name"] == "top.u_dut.u_fifo"
    assert "coverage_pct" not in rsp["data"]["items"][0]


def test_export_scope_tree_contains_coverage_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "tree",
        "action": "export.scope_tree", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "output": {"mode": "both", "path": "tree.json"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["output_path"] == ".xverif/xcov_exports/tree.json"
    item = next(i for i in rsp["data"]["items"] if i["full_name"] == "top.u_dut")
    assert item["coverable"] == 4
    assert item["metrics"]
    assert (tmp_path / ".xverif/xcov_exports/tree.json").exists()


def test_functional_levels_filter():
    dispatcher = _dispatch_opened()
    bins = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-bin",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
        "output": {"format": "json"},
    })
    cps = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-cp",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["coverpoint"]},
        "output": {"format": "json"},
    })
    assert bins["summary"]["matched_count"] == 1
    assert cps["summary"]["matched_count"] == 0


def test_test_each_is_explicitly_unsupported():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "each",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"test": "each"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is False
    assert rsp["error"]["code"] == "TEST_MODE_NOT_SUPPORTED"


def test_export_path_safety(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    bad_parent = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "bad-parent",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": "../holes.json"}},
        "output": {"format": "json"},
    })
    bad_abs = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "bad-abs",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": str(tmp_path / "holes.json")}},
        "output": {"format": "json"},
    })
    ok = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "ok-rel",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": "holes.json"}},
        "output": {"format": "json"},
    })
    assert bad_parent["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert bad_abs["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert ok["ok"] is True
    assert (tmp_path / ".xverif/xcov_exports/holes.json").exists()


class CountingBackend(CoverageBackend):
    def __init__(self) -> None:
        self.scopes_called = 0

    def tests(self):
        return [{"name": "t0"}]

    def summary(self):
        return {"test_count": 1, "top_scope_count": 1}

    def scopes(self):
        self.scopes_called += 1
        raise AssertionError("session public_json must not scan scopes")

    def metrics_for_scope(self, scope, test):
        return []

    def items(self, metrics=None, scope=None, test="merged", functional_only=False):
        return []


def test_session_public_json_does_not_scan_scopes():
    backend = CountingBackend()
    session = XcovSession("cov0", "fake", backend, "fake")
    assert session.public_json()["top_scope_count"] == 1
    assert backend.scopes_called == 0
