from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

def test_real_pynpi_exclusion_matrix_union_strict_and_reopen(
    xverif_fixture,
    tmp_path,
):
    resources = xverif_fixture("xcov.exclusion")
    vdb = resources / "exclusion.vdb"
    worker = Path(__file__).with_name("real_exclusion_worker.py")
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }

    def run(*args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(worker), *args],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
        assert lines, proc.stdout + proc.stderr
        return json.loads(lines[-1])

    default = run("default", str(vdb), str(tmp_path))
    assert default["union"] is True
    assert all(
        statuses == ["changed", "already_in_state", "changed"]
        for statuses in default["matrix"].values()
    )

    reopened = run("reopen", str(vdb), default["persisted"])
    assert reopened["before"] == 0
    assert reopened["after"] >= 2

    strict = run("strict", str(vdb))
    assert set(strict) == {"line", "toggle", "branch", "condition", "fsm", "assert", "functional"}
    assert all(value == {"covered": "failed", "uncovered": "changed"} for value in strict.values())


def test_native_worker_crash_isolated_and_explicit_close_reopens(xverif_fixture):
    import pytest
    from xcov.backend import NpiCoverageBackend
    from xcov.errors import XcovError
    vdb = str(xverif_fixture("xcov.exclusion") / "exclusion.vdb")
    backend = NpiCoverageBackend(vdb)
    worker = backend.cov.process
    worker.kill()
    worker.wait(timeout=10)
    with pytest.raises(XcovError) as failure:
        backend.items(metrics=["line"])
    assert failure.value.code == "NPI_WORKER_LOST"
    backend.close()
    backend.close()
    reopened = NpiCoverageBackend(vdb, exclusion_policy="strict")
    try:
        assert reopened.items(metrics=["line"])
    finally:
        process = reopened.cov.process
        reopened.close()
    assert process.returncode == 0


def test_native_init_timeout_is_bounded_and_reaps_stopped_worker(tmp_path, monkeypatch):
    import signal
    import time
    import pytest
    from xcov.native import NativeCoverage
    from xcov.errors import XcovError

    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setenv("XVERIF_XCOV_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("XVERIF_XCOV_NATIVE_INIT_TIMEOUT_SECONDS", "5")
    worker = NativeCoverage()
    worker.init_timeout_seconds = 0.15
    try:
        os.kill(worker.process.pid, signal.SIGSTOP)
        started = time.monotonic()
        with pytest.raises(XcovError) as failure:
            worker.init([])
        elapsed = time.monotonic() - started
        assert failure.value.code == "NPI_WORKER_LOST"
        assert failure.value.detail["failure_kind"] == "timeout"
        assert failure.value.detail["operation"] == "init"
        assert failure.value.detail["timeout_seconds"] == 0.15
        assert failure.value.detail["automatic_retry"] is False
        from xcov.errors import error_response
        from xcov.schemas import validate_response
        exc = failure.value
        response = error_response("session.open", "native-init-timeout", exc.code, exc.message, **exc.detail)
        validate_response("session.open", response)
        assert response["error"]["detail.failure_kind"] == "timeout"
        assert elapsed < 3, "timeout cleanup must not add the old 5-second grace period"
        assert worker.process.returncode == -signal.SIGKILL
        status = json.loads(Path(failure.value.detail["diagnostic_path"]).read_text())
        assert status["state"] == "failed" and status["operation"] == "init"
        assert status["process_returncode"] == -signal.SIGKILL
        assert "network" in status
        with pytest.raises(XcovError, match="closed"):
            worker.init([])
    finally:
        worker.shutdown(force=True)


def test_native_close_timeout_remains_an_error_after_reaping(xverif_fixture, monkeypatch):
    import signal
    import pytest
    from xcov import native
    from xcov.backend import NpiCoverageBackend
    from xcov.errors import XcovError
    monkeypatch.setattr(native, 'CLOSE_TIMEOUT_SECONDS', 0.15)
    backend = NpiCoverageBackend(str(xverif_fixture('xcov.exclusion') / 'exclusion.vdb'))
    process = backend.cov.process
    try:
        os.kill(process.pid, signal.SIGSTOP)
        with pytest.raises(XcovError) as caught:
            backend.close()
        assert caught.value.code == 'NPI_WORKER_LOST'
        assert caught.value.detail['failure_kind'] == 'timeout'
        assert caught.value.detail['operation'] == 'close'
        assert process.poll() == -signal.SIGKILL
        assert backend.db is None
        backend.close()
    finally:
        backend.cov.shutdown(force=True)


def test_native_worker_dies_with_owner_even_when_stopped(tmp_path):
    # Isolate subreaper state in a helper, so the adopted native process can be
    # reaped without affecting pytest or leaving a zombie in a container PID 1.
    owner = r'''
import os, sys
from xcov.native import NativeCoverage
from xcov.errors import XcovError
worker = NativeCoverage()
assert worker.call("hello")["protocol"] == 1
print(worker.process.pid, flush=True)
sys.stdin.readline()
worker.shutdown(force=True)
'''
    supervisor = r'''
import ctypes, os, signal, subprocess, sys, time
libc = ctypes.CDLL(None)
assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
parent = subprocess.Popen([sys.executable, "-c", sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
worker_pid = None
try:
    line = parent.stdout.readline()
    assert line.strip().isdigit(), line
    worker_pid = int(line)
    os.kill(worker_pid, signal.SIGSTOP)
    parent.kill()
    parent.wait(timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pid, status = os.waitpid(worker_pid, os.WNOHANG)
        if pid:
            assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
            worker_pid = None
            print("OWNER_DEATH_REAPED")
            break
        time.sleep(0.02)
    else:
        raise AssertionError("native worker survived its owner")
finally:
    if parent.poll() is None:
        parent.kill(); parent.wait(timeout=5)
    if worker_pid:
        try: os.kill(worker_pid, signal.SIGKILL)
        except ProcessLookupError: pass
        os.waitpid(worker_pid, 0)
'''
    env = {**os.environ, "XVERIF_XCOV_LOG_DIR": str(tmp_path)}
    result = subprocess.run([sys.executable, "-c", supervisor, owner], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OWNER_DEATH_REAPED" in result.stdout


def test_native_repeated_reads_record_memory_and_reap_session(xverif_fixture, tmp_path):
    """Repeated complete reads release wire references within the fixture memory budget."""
    from xcov.backend import NpiCoverageBackend
    backend = NpiCoverageBackend(str(xverif_fixture("xcov.exclusion") / "exclusion.vdb"))
    worker = backend.cov.process
    samples = []
    def rss_kib():
        fields = dict(line.split(":", 1) for line in Path(f"/proc/{worker.pid}/status").read_text().splitlines() if ":" in line)
        return int(fields["VmRSS"].split()[0])
    try:
        samples.append(rss_kib())
        baseline = None
        owned = backend.cov.call('diagnostics')['handles']
        for _ in range(40):
            rows = backend.items()
            signature = [{key: value for key, value in row.items() if key != 'coverage_ref'} for row in rows]
            assert signature
            if baseline is None:
                baseline = signature
            assert signature == baseline
            assert backend.cov.call('diagnostics')['handles'] == owned
            samples.append(rss_kib())
        assert max(samples[-10:]) - min(samples[10:20]) < 4096, 'native per-scan allocation exceeded the fixture memory budget'
    finally:
        backend.close()
    assert worker.poll() == 0
    assert not Path(f"/proc/{worker.pid}").exists()
    evidence = {"iterations": 40, "rows_per_iteration": len(baseline), "rss_kib": samples,
                "growth_kib": samples[-1] - samples[0], "peak_kib": max(samples),
                "reaped": True, "scope": "bounded fixture observation, not an unlimited-session guarantee"}
    (tmp_path / "native-lifecycle.json").write_text(json.dumps(evidence, indent=2))
    print("NATIVE_LIFECYCLE=" + json.dumps(evidence))


def test_releasing_one_native_alias_preserves_the_other(xverif_fixture):
    from xcov.backend import NpiCoverageBackend
    backend = NpiCoverageBackend(str(xverif_fixture('xcov.exclusion') / 'exclusion.vdb'))
    try:
        owned = backend.cov.call('diagnostics')['handles']
        instances = backend.db.instance_handles()
        original = instances[0]
        alias = backend.db.handle_by_name(original.full_name())
        backend.cov.release_handle(original)
        backend.cov.call('flush')
        metric = alias.line_metric_handle()
        assert metric.type() == 'npiCovLineMetric'
        children = metric.child_handles()
        assert children
        for child in children:
            backend.cov.release_handle(child)
        backend.cov.release_handle(metric)
        backend.cov.release_handle(alias)
        for instance in instances[1:]:
            backend.cov.release_handle(instance)
        assert backend.cov.call('diagnostics')['handles'] == owned
    finally:
        backend.close()


def test_ambiguous_second_pass_never_mutates_exclusion(xverif_fixture, monkeypatch):
    from xcov.backend import NpiCoverageBackend
    backend = NpiCoverageBackend(str(xverif_fixture('xcov.exclusion') / 'exclusion.vdb'))
    try:
        rows = backend.items(metrics=['line'])
        target = next(row for row in rows if row['type'] == 'npiCovStmtBin' and row['coverable'] == 1)
        original = backend._scan_score_handles

        def duplicate(test, callback, metrics):
            def visit(handle, row):
                callback(handle, row)
                callback(handle, row)
            original(test, visit, metrics)

        monkeypatch.setattr(backend, '_scan_score_handles', duplicate)
        response = backend.set_exclusion(target['coverage_ref'], True)
        assert response['status'] == 'failed' and response['match_count'] == 2
        assert backend.items(metrics=['line']) == rows
        assert not backend._pinned_handle_ids
    finally:
        backend.close()
