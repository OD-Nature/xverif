"""Exercise worker failure cleanup with real subprocesses, without an EDA license."""
from __future__ import annotations

import subprocess
import sys
from copy import deepcopy

import pytest

from xcov.errors import XcovError, error_response
from xcov.schemas import validate_response
from xcov import npi_worker
from xcov.backend import NpiCoverageBackend, UrgCoverageBackend


@pytest.mark.parametrize("stage", ["startup", "request", "close", "crash", "close_crash"])
def test_worker_failure_reaps_child_without_restarting(monkeypatch, stage):
    script = """
import json
import os
import signal
import sys
import time
stage = sys.argv[1]
if stage == 'startup':
    time.sleep(60)
print(json.dumps({'ok': True, 'result': None}), flush=True)
for line in sys.stdin:
    if stage == 'crash':
        os._exit(7)
    if stage == 'close_crash':
        print(json.dumps({'ok': True, 'result': None}), flush=True)
        os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(60)
"""
    processes = []
    real_popen = subprocess.Popen

    def launch(_command, **kwargs):
        process = real_popen([sys.executable, "-u", "-c", script, stage], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(npi_worker.subprocess, "Popen", launch)
    monkeypatch.setattr(npi_worker, "STARTUP_TIMEOUT_SEC", 0.2 if stage == "startup" else 10)
    monkeypatch.setattr(npi_worker, "REQUEST_TIMEOUT_SEC", 0.1)
    monkeypatch.setattr(npi_worker, "CLOSE_TIMEOUT_SEC", 0.1)
    worker = None
    with pytest.raises(XcovError) as caught:
        worker = npi_worker.NpiWorker("unused.vdb", "default")
        if stage.startswith("close"):
            worker.close()
        else:
            worker.call("items")
    assert caught.value.code == (
        "NPI_WORKER_EXITED" if stage in {"crash", "close_crash"} else "NPI_WORKER_TIMEOUT"
    )
    action = "session.close" if stage.startswith("close") else "exclude.add"
    validate_response(action, error_response(
        action, "worker-failure", caught.value.code, caught.value.message,
        **caught.value.detail,
    ))
    assert len(processes) == 1, "failed workers must never silently restart"
    process = processes[0]
    assert process.poll() is not None
    assert process.stdin.closed and process.stdout.closed
    if worker is not None:
        worker.close()


@pytest.mark.parametrize("message", ["unexpected startup failure", ""])
def test_worker_unexpected_startup_error_matches_public_schema(monkeypatch, message):
    script = """
import sys
from xcov import backend
from xcov.npi_worker import _serve
class BrokenInitialization:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(sys.argv[4])
backend._LocalNpiCoverageBackend = BrokenInitialization
raise SystemExit(_serve())
"""
    processes = []
    real_popen = subprocess.Popen

    def launch(command, **kwargs):
        process = real_popen([sys.executable, "-c", script, *command[3:], message], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(npi_worker.subprocess, "Popen", launch)
    with pytest.raises(XcovError) as caught:
        npi_worker.NpiWorker("unused.vdb", "default")
    assert caught.value.code == "NPI_WORKER_FAILED"
    assert caught.value.detail["cause_type"] == "RuntimeError"
    assert caught.value.message
    validate_response("session.open", error_response(
        "session.open", "worker-startup", caught.value.code, caught.value.message,
        **caught.value.detail,
    ))
    assert len(processes) == 1 and processes[0].poll() is not None


def test_urg_close_retains_unconfirmed_worker_for_cleanup_retry():
    class IncompleteCleanup:
        attempts = 0

        def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise XcovError("NPI_WORKER_CLEANUP_UNCONFIRMED", "worker still alive")

    backend = UrgCoverageBackend("unused.vdb")
    worker = IncompleteCleanup()
    backend._npi = worker
    with pytest.raises(XcovError, match="worker still alive"):
        backend.close()
    assert backend._npi is worker
    backend.close()
    assert worker.attempts == 2
    assert backend._npi is None


@pytest.mark.parametrize("operation", ["attach_gap_locators", "resolve_gap_payload"])
def test_gap_resolution_updates_existing_caller_references(operation):
    payload = {"line_groups": [{"uncovered": [{"gap_id": "L0001"}]}]}
    selected_gap = payload["line_groups"][0]["uncovered"][0]

    class Worker:
        def call(self, name, value, test):
            assert name == operation and test == "merged"
            resolved = deepcopy(value)
            resolved["line_groups"][0]["uncovered"][0]["_exclude_targets"] = [{"path": [0, 1]}]
            resolved["exclusion_locator"] = {"version": "xcov.npi_path.v1"}
            return resolved

    backend = object.__new__(NpiCoverageBackend)
    backend._worker = Worker()
    result = getattr(backend, operation)(payload)
    assert result is payload
    assert selected_gap is payload["line_groups"][0]["uncovered"][0]
    assert selected_gap["_exclude_targets"] == [{"path": [0, 1]}]
    assert payload["exclusion_locator"]["version"] == "xcov.npi_path.v1"
