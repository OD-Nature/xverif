"""Native supervisor fault injection with real subprocesses and no EDA license."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from xcov import native
from xcov.backend import NpiCoverageBackend, UrgCoverageBackend
from xcov.errors import XcovError, error_response
from xcov.schemas import validate_response

FAULT_PEER = r'''
import json, os, signal, socket, sys, time
from pathlib import Path
channel = socket.socket(fileno=int(sys.argv[1]))
stage = sys.argv[2]
reader = channel.makefile('rb')
def reply(value):
    channel.sendall((json.dumps(value) + '\n').encode())
for line in reader:
    method = json.loads(line)['method']
    if method == 'hello':
        if stage == 'startup': time.sleep(60)
        library = Path(os.environ['VERDI_HOME']) / 'share/NPI/lib/LINUX64/libNPI.so'
        stat = library.stat()
        reply({'ok': True, 'result': {
            'protocol': 99 if stage == 'sdk_mismatch' else 1,
            'sdk_home': os.environ['VERDI_HOME'],
            'library_size': stat.st_size, 'library_mtime': int(stat.st_mtime)}})
        continue
    if stage in {'request', 'close'}: time.sleep(60)
    if stage == 'paced': time.sleep(0.12)
    if stage == 'crash': os._exit(7)
    if stage == 'close_crash':
        reply({'ok': True, 'result': 1})
        os.kill(os.getpid(), signal.SIGTERM)
    if stage == 'malformed':
        reply({'ok': 'yes', 'result': 1})
    elif stage == 'invalid_handle':
        reply({'ok': True, 'result': {'handle': 1, 'properties': 'invalid'}})
    elif stage == 'partial':
        for _ in range(100):
            channel.sendall(b' ')
            time.sleep(0.04)
    elif stage == 'oversize':
        channel.sendall(b'x' * 4096)
    elif stage == 'remote_error':
        reply({'ok': False, 'error': 'injected native failure'})
    else:
        reply({'ok': True, 'result': 0 if method == 'init' and stage == 'init_rejected' else 1})
        if method in {'close', 'end'}: os._exit(0)
'''

@pytest.fixture
def fault_peer(monkeypatch, tmp_path):
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    library = tmp_path / 'sdk/share/NPI/lib/LINUX64/libNPI.so'
    library.parent.mkdir(parents=True)
    library.write_bytes(b'fault-injection-only')
    monkeypatch.setattr(native, 'resolve_verdi_home', lambda: str(tmp_path / 'sdk'))
    monkeypatch.setattr(native, '_worker_binary', lambda: Path(sys.executable))
    monkeypatch.setenv('XVERIF_XCOV_LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setenv(native.INIT_TIMEOUT_ENV, '0.5')
    monkeypatch.setattr(native, 'RPC_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(native, 'STOP_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(native, 'CLOSE_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(native, 'MAX_FRAME_BYTES', 1024)
    real_popen = subprocess.Popen
    processes = []
    def launch(stage):
        def popen(command, **kwargs):
            process = real_popen([sys.executable, '-u', '-c', FAULT_PEER, command[1], stage], **kwargs)
            processes.append(process)
            return process
        monkeypatch.setattr(native.subprocess, 'Popen', popen)
        return processes
    yield launch
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

@pytest.mark.parametrize('stage', [
    'startup', 'request', 'close', 'crash', 'close_crash', 'malformed',
    'invalid_handle', 'partial', 'oversize', 'remote_error', 'sdk_mismatch',
])
def test_worker_failure_reaps_child_without_restarting(fault_peer, stage):
    processes = fault_peer(stage)
    worker = None
    started = time.monotonic()
    with pytest.raises(XcovError) as caught:
        worker = native.NativeCoverage()
        if stage.startswith('close'):
            worker.end()
        else:
            worker.call('diagnostics')
    assert caught.value.code == {
        'remote_error': 'NPI_NATIVE_FAILED', 'sdk_mismatch': 'NPI_SDK_MISMATCH',
    }.get(stage, 'NPI_WORKER_LOST')
    assert time.monotonic() - started < 4, 'partial frames must not reset the operation deadline'
    action = 'session.close' if stage.startswith('close') else 'exclude.add'
    validate_response(action, error_response(
        action, 'worker-failure', caught.value.code, caught.value.message, **caught.value.detail,
    ))
    assert len(processes) == 1, 'failed workers must never silently restart'
    assert processes[0].poll() is not None
    if stage == 'close':
        assert caught.value.detail['failure_kind'] == 'timeout'
        assert caught.value.detail['operation'] == 'end'
    if worker is not None:
        assert worker._socket.fileno() == -1
        worker.end()

def test_rejected_initialization_reaps_worker(fault_peer):
    processes = fault_peer('init_rejected')
    with pytest.raises(XcovError) as caught:
        NpiCoverageBackend('unused.vdb')
    assert caught.value.code == 'NPI_INIT_FAILED'
    assert len(processes) == 1 and processes[0].poll() == 0


def test_nested_operations_share_one_deadline(fault_peer, monkeypatch):
    fault_peer('paced')
    monkeypatch.setattr(native, 'RPC_TIMEOUT_SECONDS', 1)
    monkeypatch.setattr(native, 'OPERATION_TIMEOUT_SECONDS', 0.2)
    worker = native.NativeCoverage()
    with pytest.raises(XcovError) as caught:
        with worker.operation():
            assert worker.call('diagnostics') == 1
            with worker.operation():
                worker.call('diagnostics')
    assert caught.value.detail['failure_kind'] == 'timeout'
    assert worker.process.poll() is not None


def test_cancelled_initialization_reaps_worker(fault_peer, monkeypatch):
    processes = fault_peer('healthy')
    def cancelled(self, argv):
        raise KeyboardInterrupt('injected cancellation before SDK init')
    monkeypatch.setattr(native.NativeCoverage, 'init', cancelled)
    with pytest.raises(KeyboardInterrupt):
        NpiCoverageBackend('unused.vdb')
    assert len(processes) == 1 and processes[0].poll() == 0

def test_unconfirmed_cleanup_can_be_retried(fault_peer, monkeypatch):
    import gc
    import weakref
    fault_peer('request')
    worker = native.NativeCoverage()
    original_wait, original_poll = worker.process.wait, worker.process.poll
    def unconfirmed(*args, **kwargs):
        raise subprocess.TimeoutExpired('injected wait failure', 0.2)
    monkeypatch.setattr(worker.process, 'wait', unconfirmed)
    monkeypatch.setattr(worker.process, 'poll', lambda: None)
    with pytest.raises(XcovError) as caught:
        worker.shutdown(force=True)
    assert caught.value.code == 'NPI_WORKER_CLEANUP_UNCONFIRMED'
    monkeypatch.setattr(worker.process, 'wait', original_wait)
    monkeypatch.setattr(worker.process, 'poll', original_poll)
    worker.end()
    assert worker.process.poll() is not None
    reference = weakref.ref(worker)
    del worker, caught
    gc.collect()
    assert reference() is None, 'confirmed cleanup must release the atexit owner reference'

def test_cached_properties_are_unusable_after_worker_close(fault_peer):
    fault_peer('healthy')
    worker = native.NativeCoverage()
    properties = [None] * len(native.PROPERTY_NAMES)
    properties[native.PROPERTY_INDEX['name']] = 'cached'
    handle = native.NativeHandle(worker, 1, properties)
    worker.end()
    with pytest.raises(XcovError) as caught:
        handle.name()
    assert caught.value.code == 'NPI_WORKER_LOST'

def test_urg_close_retains_unconfirmed_worker_for_cleanup_retry():
    class IncompleteCleanup:
        attempts = 0
        def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise XcovError('NPI_WORKER_CLEANUP_UNCONFIRMED', 'worker still alive')
    backend = UrgCoverageBackend('unused.vdb')
    worker = IncompleteCleanup()
    backend._npi = worker
    with pytest.raises(XcovError, match='worker still alive'):
        backend.close()
    assert backend._npi is worker
    backend.close()
    assert worker.attempts == 2 and backend._npi is None
