"""UDS JSONL tests for the SDK-free loop wrapper."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from xverif_loop.config import configure_mcp_environment
from xverif_loop.logging import configure_mcp_logging
from xverif_loop.wrapper import LoopWrapperServer, LoopWrapperService, send_requests


@pytest.fixture(autouse=True)
def _restore_shared_defaults():
    yield
    configure_mcp_environment()
    configure_mcp_logging()


def _make_fake_loop(path: Path, *, protocol: str, api_version: str, slow_query: bool = False) -> str:
    path.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys, time

print(json.dumps({{"type":"ready","protocol":{protocol!r},"version":1,"pid":os.getpid()}}))
sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    rid = req.get("request_id", req.get("id", "unknown"))
    action = req.get("action", "")
    output = req.get("output", {{}})
    wants_json = (output.get("format") == "json" or
                  output.get("response_format") == "json" or
                  req.get("__xverif_loop_payload_format") == "json")
    if action == "stdio.quit":
        rsp = {{"id": rid, "ok": True, "payload_format": "json", "json": {{"ok": True, "action": "stdio.quit"}}}}
        print(json.dumps(rsp)); sys.stdout.flush(); sys.exit(0)
    if action == "session.open":
        name = req.get("args", {{}}).get("name", "fake")
        result = {{"ok": True, "action": action, "summary": {{"session_id": name, "mode": "fake"}}}}
    else:
        if {slow_query!r}:
            time.sleep(999)
        result = {{"ok": True, "action": action, "summary": {{"echo_args": req.get("args", {{}})}}}}
    if wants_json:
        rsp = {{"id": rid, "ok": True, "payload_format": "json", "json": result}}
    else:
        rsp = {{"id": rid, "ok": True, "payload_format": "xout", "xout": "@{api_version}." + action + ".v1\\n"}}
    print(json.dumps(rsp)); sys.stdout.flush()
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return str(path)


def _start_server(tmp_path: Path, service: LoopWrapperService) -> tuple[LoopWrapperServer, threading.Thread, str]:
    sock = str(tmp_path / "wrapper.sock")
    server = LoopWrapperServer(sock, service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.wait_until_ready(timeout_sec=5.0)
    return server, thread, sock


def _send_raw(socket_path: str, payload: str) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path)
        reader = sock.makefile("r", encoding="utf-8")
        writer = sock.makefile("w", encoding="utf-8")
        writer.write(payload + "\n")
        writer.flush()
        return json.loads(reader.readline())


def _read_ndjson(path: Path) -> list[dict]:
    assert path.exists(), path
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _session_log(root: Path, alias: str, name: str) -> list[dict]:
    return _read_ndjson(root / "sessions" / alias / f"{name}.ndjson")


def test_loop_wrapper_ping(tmp_path, monkeypatch):
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(tmp_path / "logs"))
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        rsp = send_requests(sock, [{"id": "p1", "method": "server.ping", "params": {}}])[0]
        assert rsp["ok"] is True
        assert rsp["result"]["pong"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loop_wrapper_debug_session_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(tmp_path / "logs"))
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        responses = send_requests(sock, [
            {"id": "open", "method": "debug.session.open", "params": {
                "name": "d0", "fsdb": "wave.fsdb", "run_manifest": "debug-run-manifest.json"}},
            {"id": "doctor", "method": "debug.session.doctor", "params": {"session": "d0"}},
            {"id": "query", "method": "debug.query", "params": {
                "session": "d0", "action": "value.at", "args": {"signal": "clk"}, "output_format": "json"}},
            {"id": "list", "method": "debug.session.list", "params": {}},
            {"id": "close", "method": "debug.session.close", "params": {"name": "d0"}},
            {"id": "gc", "method": "debug.session.gc", "params": {}},
        ])
        assert [r["ok"] for r in responses] == [True, True, True, True, True, True]
        assert responses[0]["result"]["session"]["alias"] == "d0"
        assert responses[1]["result"]["summary"]["read_only"] is True
        assert responses[2]["result"]["action"] == "value.at"
        assert responses[3]["result"]["sessions"]
        assert responses[5]["result"]["summary"]["removed_count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loop_wrapper_cov_session_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(tmp_path / "logs"))
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        responses = send_requests(sock, [
            {"id": "open", "method": "cov.session.open", "params": {
                "name": "c0", "vdb": "merged.vdb", "run_manifest": "cov-run-manifest.json"}},
            {"id": "doctor", "method": "cov.session.doctor", "params": {"session": "c0"}},
            {"id": "query", "method": "cov.query", "params": {
                "session": "c0", "action": "coverage.summary", "output_format": "json"}},
            {"id": "kill", "method": "cov.session.kill", "params": {"name": "c0"}},
            {"id": "gc", "method": "cov.session.gc", "params": {}},
        ])
        assert [r["ok"] for r in responses] == [True, True, True, True, True]
        assert responses[0]["result"]["session"]["vdb"] == "merged.vdb"
        assert responses[1]["result"]["summary"]["read_only"] is True
        assert responses[2]["result"]["action"] == "coverage.summary"
        assert responses[3]["result"]["data"]["cleanup"]["native_kill"] == "not_supported"
        assert responses[4]["result"]["summary"]["removed_count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loop_wrapper_reports_bad_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(tmp_path / "logs"))
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        invalid = _send_raw(sock, "{not-json")
        assert invalid["ok"] is False
        assert invalid["error"]["code"] == "INVALID_JSON"
        unknown = send_requests(sock, [{"id": "u", "method": "missing.method", "params": {}}])[0]
        assert unknown["ok"] is False
        assert unknown["error"]["code"] == "UNKNOWN_METHOD"
        missing = send_requests(sock, [{"id": "m", "method": "debug.query", "params": {"session": "d0"}}])[0]
        assert missing["ok"] is False
        assert missing["error"]["code"] == "INVALID_PARAMS"
        unsupported_output = send_requests(sock, [{
            "id": "o",
            "method": "debug.query",
            "params": {
                "session": "d0",
                "action": "value.at",
                "output": {"response_format": "json"},
            },
        }])[0]
        assert unsupported_output["ok"] is False
        assert unsupported_output["error"]["code"] == "INVALID_PARAMS"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loop_wrapper_query_timeout_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(tmp_path / "logs"))
    debug = _make_fake_loop(
        tmp_path / "fake_xdebug",
        protocol="xdebug-stdio-loop",
        api_version="xdebug",
        slow_query=True,
    )
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(
        mode="direct",
        xdebug_bin=debug,
        xcov_bin=cov,
        startup_timeout_sec=2.0,
        request_timeout_sec=0.2,
    )
    server, thread, sock = _start_server(tmp_path, service)
    try:
        open_rsp = send_requests(sock, [
            {"id": "open", "method": "debug.session.open", "params": {"name": "slow", "fsdb": "wave.fsdb"}}
        ])[0]
        assert open_rsp["ok"] is True
        query_rsp = send_requests(sock, [
            {"id": "query", "method": "debug.query", "params": {
                "session": "slow", "action": "value.at", "args": {"signal": "clk"}, "output_format": "json"}}
        ], timeout_sec=2.0)[0]
        assert query_rsp["ok"] is False
        assert query_rsp["error"]["code"] == "SESSION_LOST"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_loop_wrapper_writes_direct_structured_logs(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(log_root))
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        responses = send_requests(sock, [
            {"id": "open", "method": "debug.session.open", "params": {"name": "logcase", "fsdb": "wave.fsdb"}},
            {"id": "query", "method": "debug.query", "params": {
                "session": "logcase", "action": "value.at", "args": {"signal": "clk"}, "output_format": "json"}},
            {"id": "close", "method": "debug.session.close", "params": {"name": "logcase"}},
        ])
        assert all(r["ok"] for r in responses)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    uds_events = _read_ndjson(log_root / "logs" / "uds.ndjson")
    session_events = _session_log(log_root, "logcase", "session")
    stdio_events = _session_log(log_root, "logcase", "stdio")
    assert {e["component"] for e in uds_events} == {"xverif-loop-wrapper"}
    assert {e["layer"] for e in uds_events} == {"loop-wrapper"}
    assert "uds.listen.ready" in [e["phase"] for e in uds_events]
    assert "uds.request.begin" in [e["phase"] for e in uds_events]
    assert "uds.request.end" in [e["phase"] for e in uds_events]
    assert "manager.open.begin" in [e["phase"] for e in session_events]
    assert "query.begin" in [e["phase"] for e in session_events]
    assert "manager.close.end" in [e["phase"] for e in session_events]
    assert "process.start" in [e["phase"] for e in stdio_events]
    assert "ready.ok" in [e["phase"] for e in stdio_events]
    assert "request.end" in [e["phase"] for e in stdio_events]


def test_loop_wrapper_logs_invalid_json_and_redacts_paths(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    private_dir = tmp_path / "very" / "private"
    private_dir.mkdir(parents=True)
    private_fsdb = private_dir / "wave.fsdb"
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(log_root))
    monkeypatch.setenv("XDEBUG_LOG_PATH_MODE", "basename")
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(mode="direct", xdebug_bin=debug, xcov_bin=cov)
    server, thread, sock = _start_server(tmp_path, service)
    try:
        invalid = _send_raw(sock, "{not-json")
        assert invalid["ok"] is False
        opened = send_requests(sock, [
            {"id": "open", "method": "debug.session.open", "params": {"name": "redact", "fsdb": str(private_fsdb)}}
        ])[0]
        assert opened["ok"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)

    uds_text = (log_root / "logs" / "uds.ndjson").read_text(encoding="utf-8")
    session_text = (log_root / "sessions" / "redact" / "session.ndjson").read_text(encoding="utf-8")
    assert "uds.request.invalid_json" in uds_text
    assert "wave.fsdb" in session_text
    assert str(private_dir) not in session_text
    assert str(tmp_path) not in uds_text


def test_loop_wrapper_fake_lsf_logs_job_and_cleanup(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("XVERIF_LOOP_LOG_DIR", str(log_root))
    monkeypatch.setenv("XVERIF_LOOP_FAKE_LSF", "1")
    monkeypatch.setenv("FAKE_BSUB_STDOUT_NOISE_BEFORE_READY", "1")
    debug = _make_fake_loop(tmp_path / "fake_xdebug", protocol="xdebug-stdio-loop", api_version="xdebug")
    cov = _make_fake_loop(tmp_path / "fake_xcov", protocol="xcov-stdio-loop", api_version="xcov")
    service = LoopWrapperService(
        mode="lsf",
        xdebug_bin=debug,
        xcov_bin=cov,
        startup_timeout_sec=3.0,
        request_timeout_sec=3.0,
    )
    server, thread, sock = _start_server(tmp_path, service)
    try:
        responses = send_requests(sock, [
            {"id": "open", "method": "debug.session.open", "params": {"name": "lsfcase", "fsdb": "wave.fsdb"}},
            {"id": "close", "method": "debug.session.close", "params": {"name": "lsfcase"}},
        ], timeout_sec=10.0)
        assert [r["ok"] for r in responses] == [True, True]
    finally:
        server.shutdown()
        thread.join(timeout=5)

    lsf_events = _session_log(log_root, "lsfcase", "lsf")
    phases = [e["phase"] for e in lsf_events]
    assert "launcher.lsf.start" in phases
    assert "bsub.start" in phases
    assert "job_id.detected" in phases
    assert any(e.get("job_id") == "123" for e in lsf_events)
    assert any(e["phase"].startswith("bkill.") for e in lsf_events)
