from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from xcov.actions import Dispatcher
from xcov.backend import CoverageBackend, FakeCoverageBackend
from xcov.errors import XcovError
from xcov.logging import sanitize_for_log
from xcov.protocol import render_xout
from xcov.schemas import schema_actions
from xcov.session import SessionManager, XcovSession

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


def test_2018_profile_selects_native_backend(monkeypatch):
    monkeypatch.delenv("XVERIF_XCOV_BACKEND", raising=False)
    monkeypatch.setenv("XVERIF_EDA_PROFILE", "verdi-2018")
    monkeypatch.setattr("xcov.session.NativeNpiCoverageBackend", FakeCoverageBackend)
    manager = SessionManager()
    session = manager.open("sample.vdb", name="native-profile")
    assert session.worker == "npi_native_2018"
    manager.close("native-profile")


def test_2023_profile_selects_python_backend(monkeypatch):
    monkeypatch.delenv("XVERIF_XCOV_BACKEND", raising=False)
    monkeypatch.setenv("XVERIF_EDA_PROFILE", "verdi-2023")
    monkeypatch.setattr("xcov.session.NpiCoverageBackend", FakeCoverageBackend)
    manager = SessionManager()
    session = manager.open("sample.vdb", name="python-profile")
    assert session.worker == "npi_python"
    manager.close("python-profile")


def test_explicit_backend_overrides_profile(monkeypatch):
    monkeypatch.setenv("XVERIF_EDA_PROFILE", "verdi-2023")
    monkeypatch.setenv("XVERIF_XCOV_BACKEND", "native")
    monkeypatch.setattr("xcov.session.NativeNpiCoverageBackend", FakeCoverageBackend)
    manager = SessionManager()
    session = manager.open("sample.vdb", name="native-explicit")
    assert session.worker == "npi_native_2018"
    manager.close("native-explicit")


def test_unknown_backend_is_rejected_without_fallback(monkeypatch):
    monkeypatch.setenv("XVERIF_XCOV_BACKEND", "urg")
    manager = SessionManager()
    try:
        manager.open("sample.vdb", name="invalid-backend")
    except XcovError as exc:
        assert exc.code == "INVALID_BACKEND"
    else:
        raise AssertionError("unknown backend must not fall back")


def test_native_backend_rejects_empty_vdb_before_worker_start(monkeypatch, tmp_path):
    from xcov.native_backend import NativeNpiCoverageBackend

    coverage_db = tmp_path / "empty.vdb" / "snps" / "coverage" / "db"
    coverage_db.mkdir(parents=True)
    monkeypatch.setenv("XVERIF_XCOV_NATIVE_BIN", "/does/not/exist")
    try:
        NativeNpiCoverageBackend(str(tmp_path / "empty.vdb"))
    except XcovError as exc:
        assert exc.code == "INVALID_VDB"
    else:
        raise AssertionError("empty VDB must be rejected before worker startup")


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
    code_export = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "schema-export",
        "action": "schema", "args": {"action": "export.code_coverage"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    assert set(source["properties"]["args"]["required"]) == {"file", "line"}
    assert session_open["properties"]["target"]["required"] == ["vdb"]
    assert "threshold_pct" in code_export["properties"]["args"]["properties"]


def test_new_urg_alignment_actions_are_in_schema_and_actions():
    dispatcher = Dispatcher()
    actions = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "actions",
        "action": "actions", "output": {"response_format": "json"},
    })
    names = {row["name"] for row in actions["data"]["items"]}
    for action in ("code_coverage.summary", "code_coverage.holes",
                   "function_coverage.summary", "function_coverage.holes",
                   "source.annotate", "assert.summary", "export.code_coverage",
                   "export.function_coverage", "export.assert"):
        assert action in names
        schema = dispatcher.dispatch({
            "api_version": "xcov.v1", "request_id": f"schema-{action}",
            "action": "schema", "args": {"action": action},
            "output": {"response_format": "json"},
        })
        assert schema["ok"] is True
        assert schema["data"]["schema"]["properties"]["action"]["const"] == action
    removed = {"cov.summary", "cov.holes", "cov.object.get", "cov.object.search",
               "toggle.details", "export.summary", "export.holes",
               "export.scope_tree", "export.functional",
               "functional.summary", "functional.holes", "assert.report"}
    assert not (names & removed)
    for action in removed:
        rsp = dispatcher.dispatch({
            "api_version": "xcov.v1", "request_id": f"schema-removed-{action}",
            "action": "schema", "args": {"action": action},
            "output": {"response_format": "json"},
        })
        assert rsp["ok"] is False


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
         "action": "code_coverage.holes", "target": {"session_id": "cov0"},
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
    assert "@xcov.v1 ok action=code_coverage.holes" in out[2]["xout"]
    assert out[2]["json"]["summary"]["matched_count"] == 1


def test_stdio_loop_unknown_action_returns_error_without_crash():
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "bad",
         "action": "cov.holes", "target": {"session_id": "cov0"}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(req) for req in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert out[0]["protocol"] == "xcov-stdio-loop"
    assert out[2]["id"] == "bad"
    assert out[2]["ok"] is False
    assert out[2]["json"]["error"]["code"] == "ACTION_NOT_FOUND"
    assert out[2]["json"]["error"]["detail.requested_action"] == "cov.holes"


def test_tests_list_defaults_to_name_filter():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "tests",
        "action": "tests.list", "target": {"session_id": "cov0"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    assert rsp["data"]["items"][0]["name"] == "fake/test"


def test_logging_writes_action_manifest_lifecycle_and_transport(tmp_path):
    log_dir = tmp_path / "xcov_logs"
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "holes",
         "action": "code_coverage.holes", "target": {"session_id": "cov0"},
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
         "action": "code_coverage.holes", "target": {"session_id": "cov0"},
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
    path = tmp_path / "holes.md"
    reqs = [
        {"api_version": "xcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "xcov.v1", "request_id": "export",
         "action": "export.code_coverage", "target": {"session_id": "cov0"},
         "args": {"output": {"path": str(path), "allow_absolute_path": True}}},
    ]
    proc = subprocess.run([str(XCOV), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT))
    assert proc.returncode == 0
    assert path.exists()
    text = path.read_text()
    assert "# Code Coverage Holes" in text
    assert "0->1 covered" in text


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
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "metrics": ["toggle", "branch"]},
        "limits": {"max_items": 1},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 3
    assert rsp["summary"]["returned"] == 1


def test_args_limits_take_precedence_over_top_level_limits():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "holes",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "metrics": ["toggle", "branch"],
                 "limits": {"max_items": 2}},
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
    assert item["coverable"] == 9
    assert item["coverage_pct"] == 25.0
    assert item["score_basis"] == "average_metric_pct"
    assert item["score_item_count"] == 6
    assert item["raw_coverage_pct"] == 22.2222
    assert "metrics" not in item
    assert not (set(item) & {"parent", "depth", "type", "def_name"})
    assert item["toggle_pct"] == 0.0
    assert item["branch_pct"] == 0.0


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
    assert all(set(i) == {"name", "full_name", "coverage_pct"}
               for i in direct["data"]["items"])
    assert "top.u_dut.u_fifo" in {i["full_name"] for i in recursive["data"]["items"]}


def test_scope_summary_xout_uses_compact_items_and_coverage_table():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "scope-xout",
        "action": "scope.summary", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
    })
    xout = render_xout(rsp)
    assert "items:\n  name   full_name  covered  coverable  missing  coverage_pct" in xout
    assert "u_dut  top.u_dut  2        9          7        25.0" in xout
    assert "average_metric_pct" in xout
    assert "22.2222" in xout
    assert "\ncoverage:\n  metric      coverage_pct" in xout
    assert "line        100.0" in xout
    assert "toggle      0.0" in xout
    assert "parent" not in xout.split("items:", 1)[1].split("coverage:", 1)[0]
    assert "depth" not in xout.split("items:", 1)[1].split("coverage:", 1)[0]
    assert "def_name" not in xout.split("items:", 1)[1].split("coverage:", 1)[0]
    assert "line_pct" not in xout


def test_scope_children_xout_only_shows_name_full_name_coverage_pct():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "children-xout",
        "action": "scope.children", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
    })
    xout = render_xout(rsp)
    assert "items:\n  name    full_name         coverage_pct" in xout
    assert "u_ctrl  top.u_dut.u_ctrl  16.6667" in xout
    assert "u_fifo  top.u_dut.u_fifo  0.0" in xout
    items_text = xout.split("items:", 1)[1]
    assert "covered" not in items_text
    assert "line_pct" not in items_text


def test_scope_search_returns_brief_coverage_rows():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "search",
        "action": "scope.search", "target": {"session_id": "cov0"},
        "args": {"query": {"include_patterns": ["*u_fifo"], "match_field": "full_name"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["data"]["items"][0]["full_name"] == "top.u_dut.u_fifo"
    assert set(rsp["data"]["items"][0]) == {"name", "full_name", "coverage_pct"}
    assert rsp["data"]["items"][0]["coverage_pct"] == 0.0


def test_export_code_coverage_writes_markdown_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-export",
        "action": "export.code_coverage", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "output": {"path": "code.md"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["output_path"] == ".xverif/xcov_exports/code.md"
    assert rsp["summary"]["artifact_format"] == "md"
    assert "x-npi" in rsp["summary"]["note"]
    text = (tmp_path / ".xverif/xcov_exports/code.md").read_text(encoding="utf-8")
    assert "# Code Coverage Holes" in text
    assert "| scope | signal | bit | 0->1 covered | 1->0 covered | coverage_pct | file:line |" in text


def test_functional_levels_filter():
    dispatcher = _dispatch_opened()
    bins = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-bin",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
        "output": {"format": "json"},
    })
    cps = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-cp",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["coverpoint"]},
        "output": {"format": "json"},
    })
    assert bins["summary"]["matched_count"] == 1
    assert cps["summary"]["matched_count"] == 1


def test_function_coverage_holes_glob_filters_full_name_and_covergroup():
    dispatcher = _dispatch_opened()
    full_name = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-filter-full",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {
            "levels": ["bin"],
            "query": {"include_patterns": ["*zero_credit"], "match_field": "full_name"},
        },
        "output": {"format": "json"},
    })
    covergroup = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-filter-cg",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {
            "levels": ["bin"],
            "query": {"include_patterns": ["cg_*"], "match_field": "covergroup"},
        },
        "output": {"format": "json"},
    })
    assert full_name["ok"] is True
    assert full_name["summary"]["matched_count"] == 1
    assert full_name["data"]["items"][0]["bin"] == "zero_credit"
    assert covergroup["ok"] is True
    assert covergroup["summary"]["matched_count"] == 1
    assert covergroup["data"]["items"][0]["covergroup"] == "cg_credit"


def test_functional_summary_uses_requested_level_only():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-summary",
        "action": "function_coverage.summary", "target": {"session_id": "cov0"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    assert rsp["data"]["items"][0]["coverable"] == 1
    forbidden = {
        "metric", "name", "full_name", "score_basis", "score_item_count",
        "raw_covered", "raw_coverable", "raw_missing", "raw_coverage_pct",
    }
    assert not (set(rsp["data"]["items"][0]) & forbidden)


def test_code_coverage_summary_omits_display_only_fields():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-summary",
        "action": "code_coverage.summary", "target": {"session_id": "cov0"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    item = rsp["data"]["items"][0]
    assert "metric" in item
    assert not (set(item) & {"name", "full_name", "functional_pct"})


def test_code_summary_uses_urg_score_rows_only():
    from xcov.actions import _coverage_score_rows, _summary_from_items

    rows = [
        {"metric": "line", "type": "npiCovBlock", "covered": 1, "coverable": 2},
        {"metric": "line", "type": "npiCovStmtBin", "covered": 1, "coverable": 1},
        {"metric": "toggle", "type": "npiCovSignal", "covered": 1, "coverable": 4},
        {"metric": "toggle", "type": "npiCovToggleBin", "covered": 2, "coverable": 4},
        {"metric": "assert", "type": "npiCovSuccessBin", "covered": -1, "coverable": -1},
        {"metric": "assert", "type": "npiCovAssert", "covered": 1, "coverable": 1},
    ]
    summary = {row["metric"]: row for row in _summary_from_items(_coverage_score_rows(rows), "metric")}
    assert summary["line"]["covered"] == 1
    assert summary["line"]["coverable"] == 1
    assert summary["toggle"]["covered"] == 2
    assert summary["toggle"]["coverable"] == 4
    assert summary["assert"]["covered"] == 1
    assert summary["assert"]["coverable"] == 1


def test_functional_covergroup_summary_uses_urg_score_average():
    from xcov.actions import _functional_summary_rows

    rows = [
        {"metric": "functional", "type": "npiCovCovergroup", "covergroup": "cg",
         "covered": 5, "coverable": 8, "missing": 3, "coverage_pct": 62.5},
        {"metric": "functional", "type": "npiCovCoverpoint", "covergroup": "cg",
         "coverpoint": "cp_a", "covered": 2, "coverable": 2, "coverage_pct": 100.0},
        {"metric": "functional", "type": "npiCovCoverpoint", "covergroup": "cg",
         "coverpoint": "cp_b", "covered": 1, "coverable": 2, "coverage_pct": 50.0},
        {"metric": "functional", "type": "npiCovCross", "covergroup": "cg",
         "cross": "cx", "covered": 2, "coverable": 4, "coverage_pct": 50.0},
    ]
    summary = _functional_summary_rows(rows, "covergroup")
    assert summary[0]["coverage_pct"] == 66.6667
    assert summary[0]["raw_coverage_pct"] == 62.5
    assert summary[0]["score_basis"] == "average_direct_coverpoint_cross_pct"


def test_functional_bin_evidence_is_inherited_from_parent():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-bin-evidence",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    item = rsp["data"]["items"][0]
    assert item["file"] == "verif/env/uart_coverage.sv"
    assert item["line"] == 22
    forbidden = {
        "metric", "name", "full_name", "score_basis", "score_item_count",
        "raw_covered", "raw_coverable", "raw_missing", "evidence", "evidence_source",
    }
    assert not (set(item) & forbidden)


def test_code_coverage_holes_reports_hierarchy_coverage_only():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-details",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "metrics": ["toggle", "branch", "condition"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    rows = rsp["data"]["items"]
    assert {row["full_name"] for row in rows} == {
        "top.u_dut", "top.u_dut.u_ctrl", "top.u_dut.u_fifo"
    }
    item = next(row for row in rows if row["full_name"] == "top.u_dut.u_ctrl")
    assert item["branch_pct"] == 0.0
    assert item["condition_pct"] == 0.0
    assert "branch_bin" not in item
    assert "toggle_signal" not in item
    forbidden = {"parent", "depth", "type", "def_name", "covered", "coverable", "missing",
                 "file", "line"}
    assert not (set(item) & forbidden)
    assert "note" in rsp["summary"]


def test_code_coverage_holes_glob_filters_hierarchy_rows():
    dispatcher = _dispatch_opened()
    include = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-filter-include",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {
            "scope": "top.u_dut",
            "metrics": ["toggle", "branch", "condition"],
            "query": {"include_patterns": ["*u_ctrl"], "match_field": "full_name"},
        },
        "output": {"format": "json"},
    })
    exclude = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-filter-exclude",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {
            "scope": "top.u_dut",
            "metrics": ["toggle", "branch", "condition"],
            "query": {"exclude_patterns": ["*u_fifo"], "match_field": "full_name"},
        },
        "output": {"format": "json"},
    })
    assert include["ok"] is True
    assert [row["full_name"] for row in include["data"]["items"]] == ["top.u_dut.u_ctrl"]
    assert exclude["ok"] is True
    assert "top.u_dut.u_fifo" not in {row["full_name"] for row in exclude["data"]["items"]}


def test_source_annotate_returns_source_window_and_annotations(tmp_path):
    src = tmp_path / "ctrl.sv"
    src.write_text("\n".join([
        "module ctrl;",
        "  logic enable;",
        "  assert property (p_ready);",
        "endmodule",
    ]) + "\n", encoding="utf-8")
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "annotate",
        "action": "source.annotate", "target": {"session_id": "cov0"},
        "args": {"file": "rtl/ctrl.sv", "line": 120, "window": 0,
                 "include_source_text": False},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    row = rsp["data"]["items"][0]
    assert row["line"] == 120
    assert row["annotation_count"] == 1
    assert row["annotations"][0]["metric"] == "assert"


def test_function_coverage_export_groups_bins_by_covergroup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-export",
        "action": "export.function_coverage", "target": {"session_id": "cov0"},
        "args": {"covergroup": "cg_credit", "output": {"path": "func.md"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    text = (tmp_path / ".xverif/xcov_exports/func.md").read_text(encoding="utf-8")
    assert "## cg_credit (verif/env/uart_coverage.sv:21)" in text
    assert "### cp_level" in text
    assert "zero_credit" in text
    assert "verif/env/uart_coverage.sv:22" not in text


def test_assert_summary_summarizes_bins_without_report_fields():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "assert-summary",
        "action": "assert.summary", "target": {"session_id": "cov0"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    item = next(row for row in rsp["data"]["items"]
                if row["full_name"] == "top.u_dut.u_ctrl.p_ready")
    assert item["attempts"] == 10
    assert item["real_successes"] == 8
    forbidden = {"kind", "category", "severity", "failures", "incomplete",
                 "first_match", "file", "line", "evidence"}
    assert not (set(item) & forbidden)
    assert "sections" not in rsp["data"]


def test_xout_function_coverage_holes_uses_projected_fields():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "func-bin-xout",
        "action": "function_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
    })
    xout = render_xout(rsp)
    assert "evidence_source={" not in xout
    assert "evidence_source.inherited" not in xout
    assert "covergroup  coverpoint" in xout
    assert "  - metric=functional" not in xout


def test_xout_items_render_as_aligned_plain_text_table():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "metrics-xout",
        "action": "metrics.list", "target": {"session_id": "cov0"},
    })
    xout = render_xout(rsp)
    assert "items:\n  metric" in xout
    assert "  - metric=" not in xout
    assert "metric      covered  coverable  missing  coverage_pct" in xout
    assert "line        1        1          0        100.0" in xout
    assert "toggle      0        2          2        0.0" in xout


def test_xout_contains_code_coverage_hierarchy_fields_without_metrics_json():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "code-detail-xout",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "metrics": ["condition"], "limits": {"max_items": 1}},
    })
    xout = render_xout(rsp)
    assert "metrics={" not in xout
    assert "condition_pct" in xout
    assert "0.0" in xout
    assert "condition_bin=" not in xout
    assert "  - name=" not in xout
    items_text = xout.split("items:", 1)[1]
    assert "parent" not in items_text
    assert "coverable" not in items_text
    assert "summary:" in xout
    assert "note:" in xout


def test_xout_assert_summary_omits_report_fields():
    dispatcher = _dispatch_opened()
    assert_rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "assert-xout",
        "action": "assert.summary", "target": {"session_id": "cov0"},
    })
    assert_xout = render_xout(assert_rsp)
    assert "sections:" not in assert_xout
    assert "name" in assert_xout
    assert "full_name" in assert_xout
    assert "attempts  real_successes  without_attempts" in assert_xout
    assert "failures" not in assert_xout
    assert "incomplete" not in assert_xout


def test_branch_mask_hint_decoding():
    from xcov.backend import _branch_mask_hint
    # one_hot: single '1' bit, no '-'
    assert _branch_mask_hint("000000100") == {"encoding": "one_hot",
                                               "branch_arm_index": 2}
    assert _branch_mask_hint("1") == {"encoding": "one_hot",
                                       "branch_arm_index": 0}
    assert _branch_mask_hint("1000000") == {"encoding": "one_hot",
                                             "branch_arm_index": 6}
    # multi_bit: multiple '1's or all zeros
    assert _branch_mask_hint("001001000") == {"encoding": "multi_bit",
                                               "one_positions": [3, 6]}
    assert _branch_mask_hint("000000000") == {"encoding": "multi_bit",
                                               "one_positions": []}
    # path: contains '-'
    result = _branch_mask_hint("---001-1--")
    assert result["encoding"] == "path"
    assert result["dontcare_bits"] > 0
    assert result["active_bits"] > 0
    # invalid
    assert _branch_mask_hint("") is None
    assert _branch_mask_hint("else") is None
    assert _branch_mask_hint("0b1010") is None


def test_branch_mask_hint_enabled(monkeypatch):
    from xcov.backend import _branch_mask_hint_enabled
    monkeypatch.delenv("XVERIF_XCOV_BRANCH_MASK_HINT", raising=False)
    assert _branch_mask_hint_enabled() is True
    for v in ("1", "true", "yes", "on"):
        monkeypatch.setenv("XVERIF_XCOV_BRANCH_MASK_HINT", v)
        assert _branch_mask_hint_enabled() is True
    for v in ("0", "false", "no", "off"):
        monkeypatch.setenv("XVERIF_XCOV_BRANCH_MASK_HINT", v)
        assert _branch_mask_hint_enabled() is False


def test_branch_mask_in_response():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "branch-mask",
        "action": "source.map", "target": {"session_id": "cov0"},
        "args": {"file": "rtl/ctrl.sv", "line": 95, "window": 10, "metrics": ["branch"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    rows = rsp["data"]["items"]
    # one-hot item: "000000100" -> branch_mask
    bin_item = next(row for row in rows
                    if row.get("branch_bin") == "000000100")
    assert "branch_mask" in bin_item
    assert bin_item["branch_mask"]["encoding"] == "one_hot"
    assert bin_item["branch_mask"]["branch_arm_index"] == 2
    # non-bitmask item: "else" -> no branch_mask
    else_item = next(row for row in rows
                     if row.get("branch_bin") == "else")
    assert "branch_mask" not in else_item


def test_branch_mask_in_xout():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "branch-mask-xout",
        "action": "source.map", "target": {"session_id": "cov0"},
        "args": {"file": "rtl/ctrl.sv", "line": 95, "window": 10, "metrics": ["branch"]},
    })
    xout = render_xout(rsp)
    assert "branch_mask={" not in xout
    assert "branch_mask.encoding" in xout
    assert "branch_mask.branch_arm_index" in xout
    assert "one_hot" in xout


def test_test_each_is_explicitly_unsupported():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "each",
        "action": "code_coverage.holes", "target": {"session_id": "cov0"},
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
        "action": "export.code_coverage", "target": {"session_id": "cov0"},
        "args": {"output": {"path": "../holes.md"}},
        "output": {"format": "json"},
    })
    bad_abs = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "bad-abs",
        "action": "export.code_coverage", "target": {"session_id": "cov0"},
        "args": {"output": {"path": str(tmp_path / "holes.md")}},
        "output": {"format": "json"},
    })
    ok = dispatcher.dispatch({
        "api_version": "xcov.v1", "request_id": "ok-rel",
        "action": "export.code_coverage", "target": {"session_id": "cov0"},
        "args": {"output": {"path": "holes.md"}},
        "output": {"format": "json"},
    })
    assert bad_parent["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert bad_abs["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert ok["ok"] is True
    assert (tmp_path / ".xverif/xcov_exports/holes.md").exists()


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
