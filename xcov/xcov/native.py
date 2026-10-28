"""Isolated native coverage RPC; no vendor Python binding or raw pointers."""
from __future__ import annotations

import json
import atexit
import ipaddress
import math
import os
from pathlib import Path
import socket
import select
import subprocess
import threading
import tempfile
import time
from contextlib import contextmanager
from functools import wraps

from .eda import resolve_verdi_home
from .errors import XcovError
from .logging import log_root


INIT_TIMEOUT_ENV = "XVERIF_XCOV_NATIVE_INIT_TIMEOUT_SECONDS"
RPC_TIMEOUT_SECONDS = 120.0
CLOSE_TIMEOUT_SECONDS = 5.0
OPERATION_TIMEOUT_SECONDS = 600.0
STOP_TIMEOUT_SECONDS = 5.0
MAX_FRAME_BYTES = 16 * 1024 * 1024
PROPERTY_NAMES = (
    'type', 'name', 'full_name', 'file_name', 'def_name', 'value', 'toggle_type',
    'line_no', 'covered', 'coverable', 'count', 'is_port', 'severity', 'category',
    'has_status_excluded', 'has_status_partially_excluded',
    'has_status_excluded_at_compile_time', 'has_status_excluded_at_report_time',
    'has_status_unreachable', 'has_status_illegal', 'has_status_proven',
    'has_status_attempted', 'has_status_partially_attempted',
)
PROPERTY_INDEX = {name: index for index, name in enumerate(PROPERTY_NAMES)}
STRING_PROPERTIES = frozenset({'type', 'name', 'full_name', 'file_name', 'def_name'})
TEST_PROPERTIES = frozenset({
    'line_no', 'covered', 'coverable', 'count', 'value', 'toggle_type',
    'is_port', 'severity', 'category', 'has_status_excluded',
    'has_status_partially_excluded', 'has_status_excluded_at_compile_time',
    'has_status_excluded_at_report_time', 'has_status_unreachable',
    'has_status_illegal', 'has_status_proven', 'has_status_attempted',
    'has_status_partially_attempted',
})
MUTATIONS = frozenset({'set_status_excluded_at_report_time', 'load_exclude_file', 'unload_exclusion'})


def _init_timeout_seconds():
    raw = os.environ.get(INIT_TIMEOUT_ENV, str(RPC_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or not 0 < value <= 3600:
        raise XcovError("NPI_TIMEOUT_INVALID", "native init timeout must be finite and in (0, 3600] seconds", variable=INIT_TIMEOUT_ENV)
    return value


ALLOCATOR_ENV = "XVERIF_XCOV_NATIVE_USE_MALLOC"


def _worker_environment(environment):
    """Preserve the site environment unless it explicitly selects an allocator."""
    env = dict(environment)
    if ALLOCATOR_ENV in env:
        value = env[ALLOCATOR_ENV]
        if value not in {"0", "1"}:
            raise XcovError("NPI_ALLOCATOR_INVALID", "native allocator option must be 0 or 1", variable=ALLOCATOR_ENV)
        env["VCS_USE_MALLOC"] = value
    return env


def _worker_connections(pid):
    """Best-effort Linux diagnostics for this worker only; never inspect payloads."""
    root = Path("/proc") / str(pid)
    try:
        inodes = set()
        for fd in (root / "fd").iterdir():
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(target[8:-1])
        connections = []
        for table in ("tcp", "tcp6"):
            for line in (root / "net" / table).read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) < 10 or fields[9] not in inodes:
                    continue
                address, port = fields[2].split(":")
                packed = bytes.fromhex(address)
                packed = b"".join(packed[i:i + 4][::-1] for i in range(0, len(packed), 4))
                connections.append({
                    "remote_address": str(ipaddress.ip_address(packed)),
                    "remote_port": int(port, 16),
                    "state": {"01": "ESTABLISHED", "02": "SYN_SENT", "08": "CLOSE_WAIT"}.get(fields[3], fields[3]),
                    "retransmissions": int(fields[6], 16),
                })
        return {"available": True, "tcp_connections": connections}
    except (OSError, ValueError):
        return {"available": False}


class NativeHandle:
    __slots__ = ('worker', 'identity', 'properties', 'test', 'revision', 'children', 'released')

    def __init__(self, worker, identity, properties=None, test=0, children=None):
        self.worker = worker
        self.identity = identity
        self.properties = properties or []
        self.test = test
        self.revision = worker.revision
        self.children = children
        self.released = False

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)
        return lambda *args: self._read(method, args)

    def _read(self, method, args):
        with self.worker._lock:
            self.worker._check_handle(self)
            if method == 'child_handles' and self.children is not None:
                children, self.children = self.children, None
                return children
            if method in STRING_PROPERTIES and not args:
                if not self.properties:
                    self.properties = self.worker.call('properties', obj=self)
                return self.properties[PROPERTY_INDEX[method]]
            if method in TEST_PROPERTIES and len(args) == 1 and args[0] is not None:
                test = self.worker._check_handle(args[0]).identity if args[0] is not None else 0
                if self.test != test or self.revision != self.worker.revision or not self.properties:
                    self.worker.sample_test = test
                    self.properties = self.worker.call('properties', obj=self)
                    self.test = test
                    self.revision = self.worker.revision
                return self.properties[PROPERTY_INDEX[method]]
            return self.worker.call(method, *args, obj=self)

    def status_values(self, test):
        """One coherent status vector, refreshed after every exclusion mutation."""
        with self.worker._lock:
            self.worker._check_handle(self)
            self.worker._check_handle(test)
            if self.test != test.identity or self.revision != self.worker.revision or not self.properties:
                self.worker.sample_test = test.identity
                self.properties = self.worker.call('properties', obj=self)
                self.test = test.identity
                self.revision = self.worker.revision
            return self.properties[PROPERTY_INDEX['has_status_excluded']:]


def _property_reader(method):
    index = PROPERTY_INDEX[method]
    if method in STRING_PROPERTIES:
        def read(self):
            worker = self.worker
            with worker._lock:
                if not worker._ended and not self.released and self.properties:
                    return self.properties[index]
                return self._read(method, ())
    else:
        def read(self, test=None):
            worker = self.worker
            with worker._lock:
                if (not worker._ended and not self.released
                        and isinstance(test, NativeHandle) and test.worker is worker and not test.released
                        and self.test == test.identity and self.revision == worker.revision and self.properties):
                    return self.properties[index]
                return self._read(method, (test,))
    return read


# Bind frequent properties once, rather than allocating a closure for every bin
# attribute read. Less common operations still use the generic RPC boundary.
for _property in STRING_PROPERTIES | TEST_PROPERTIES:
    setattr(NativeHandle, _property, _property_reader(_property))


class NativeCoverage:
    def __init__(self):
        self.init_timeout_seconds = _init_timeout_seconds()
        home = Path(resolve_verdi_home())
        binary = _worker_binary()
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise XcovError("NPI_WORKER_MISSING", "build and install xcov/libexec/xcov-npi-worker")
        env = os.environ.copy()
        env["VERDI_HOME"] = str(home)
        # A site can opt in without changing MCP, xdebug or other EDA processes.
        env = _worker_environment(env)
        env["LD_LIBRARY_PATH"] = str(home / "share/NPI/lib/LINUX64") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        log_dir = log_root().resolve() / "native"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_directory = Path(tempfile.mkdtemp(prefix="worker-", dir=log_dir))
        self._lock = threading.RLock()
        self._socket, child = socket.socketpair()
        self._socket.setblocking(False)
        try:
            self.process = subprocess.Popen(
                [str(binary), str(child.fileno()), str(os.getpid())], pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL, stdout=2, stderr=2, env=env, cwd=self.log_directory,
            )
        except BaseException:
            self._socket.close()
            raise
        finally:
            child.close()
        self._buffer = bytearray()
        self._ended = False
        self.revision = 0
        self.sample_test = 0
        self._releases = []
        self.rpc_count = 0
        self._deadline = None
        self.diagnostic_path = self.log_directory / "native-status.json"
        atexit.register(self.shutdown, force=True)
        try:
            identity = self.call('hello')
            library = home / 'share/NPI/lib/LINUX64/libNPI.so'
            stat = library.stat()
            if identity != {'protocol': 1, 'sdk_home': str(home),
                            'library_size': stat.st_size, 'library_mtime': int(stat.st_mtime)}:
                raise XcovError('NPI_SDK_MISMATCH',
                                'native worker and configured NPI installation differ; rebuild with make xcov')
        except BaseException:
            self.shutdown(force=True)
            raise

    def _status(self, **fields):
        status = {"worker_pid": self.process.pid, "timestamp": time.time(), **fields}
        temporary = self.diagnostic_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(self.diagnostic_path)
            return str(self.diagnostic_path)
        except OSError:
            return None

    def _encode(self, value):
        if isinstance(value, NativeHandle):
            self._check_handle(value)
            return {"handle": value.identity}
        return value

    def _check_handle(self, handle):
        if self._ended:
            raise XcovError('NPI_WORKER_LOST', 'coverage worker is closed')
        if not isinstance(handle, NativeHandle) or handle.worker is not self or handle.released:
            raise XcovError('NPI_HANDLE_INVALID', 'coverage handle is released or belongs to another worker')
        return handle

    def _decode(self, value):
        if isinstance(value, dict) and 'handle' in value:
            if (set(value) - {'handle', 'properties', 'test', 'children'}
                    or type(value['handle']) is not int or value['handle'] < 1
                    or not isinstance(value.get('properties'), list)
                    or len(value['properties']) != len(PROPERTY_NAMES)
                    or type(value.get('test', 0)) is not int
                    or ('children' in value and not isinstance(value['children'], list))):
                raise ValueError('invalid native handle response')
            children = self._decode(value['children']) if 'children' in value else None
            return NativeHandle(self, value['handle'], value.get('properties'), value.get('test', 0), children)
        if isinstance(value, list):
            return [self._decode(item) for item in value]
        return value

    def _wait(self, deadline, *, writing=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('native operation deadline expired')
        readable, writable, _ = select.select(
            [] if writing else [self._socket], [self._socket] if writing else [], [], remaining,
        )
        if not readable and not writable:
            raise TimeoutError('native operation deadline expired')

    def _exchange(self, payload, deadline):
        encoded = memoryview((json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n').encode())
        if len(encoded) > MAX_FRAME_BYTES:
            raise ValueError('native request exceeds frame budget')
        while encoded:
            self._wait(deadline, writing=True)
            encoded = encoded[self._socket.send(encoded):]
        while b'\n' not in self._buffer:
            self._wait(deadline)
            block = self._socket.recv(65536)
            if not block:
                raise EOFError('native coverage worker exited')
            self._buffer.extend(block)
            if len(self._buffer) > MAX_FRAME_BYTES:
                raise ValueError('native response exceeds frame budget')
        line, _, rest = self._buffer.partition(b'\n')
        self._buffer = bytearray(rest)
        result = json.loads(line)
        if (not isinstance(result, dict) or type(result.get('ok')) is not bool
                or (result['ok'] and set(result) != {'ok', 'result'})
                or (not result['ok'] and (set(result) != {'ok', 'error'}
                    or not isinstance(result['error'], str) or not result['error']))):
            raise ValueError('invalid native response envelope')
        return result

    def call(self, method, *args, obj=None):
        with self._lock:
            if self._ended:
                raise XcovError("NPI_WORKER_LOST", "coverage worker is closed", operation=method)
            timeout = self.init_timeout_seconds if method in {"hello", "init"} else RPC_TIMEOUT_SECONDS
            if method in {'close', 'end'}:
                timeout = CLOSE_TIMEOUT_SECONDS
            started = time.monotonic()
            if self._deadline is not None:
                timeout = min(timeout, max(0.0, self._deadline - started))
            if method in {"init", "open"}:
                self._status(state="waiting", operation=method, timeout_seconds=timeout)
            try:
                if method in {"open", "load_exclude_file", "save_exclude_file"}:
                    args = (os.path.abspath(args[0]), *args[1:])
                payload = {"method": method, "object": self._encode(obj), "args": [self._encode(v) for v in args],
                           'release': self._releases, 'sample_test': self.sample_test}
                self._releases = []
                self.rpc_count += 1
                result = self._exchange(payload, started + timeout)
                decoded = self._decode(result['result']) if result['ok'] else None
            except (OSError, EOFError, ValueError) as exc:
                elapsed = time.monotonic() - started
                timed_out = isinstance(exc, TimeoutError)
                detail = {
                    "operation": method, "failure_kind": "timeout" if timed_out else "transport",
                    "elapsed_seconds": round(elapsed, 3), "timeout_seconds": timeout,
                    "cause_message": str(exc), "automatic_retry": False,
                }
                snapshot = _worker_connections(self.process.pid) if timed_out else {}
                self.shutdown(force=True)
                path = self._status(state="failed", process_returncode=self.process.returncode,
                                    network=snapshot, **detail)
                if path:
                    detail["diagnostic_path"] = path
                message = f"native coverage RPC {method} timed out after {timeout:g}s; worker terminated" if timed_out else "native coverage worker failed; reopen the session"
                if timed_out and method == "init":
                    detail["hint"] = "NPI initialization may wait for license/network access; inspect the worker diagnostic before explicitly reopening"
                raise XcovError("NPI_WORKER_LOST", message, **detail) from exc
            except BaseException:
                # Cancellation cannot leave a response queued for a later call.
                self.shutdown(force=True)
                raise
            if method in {"init", "open"}:
                self._status(state="completed" if result["ok"] else "failed", operation=method,
                             elapsed_seconds=round(time.monotonic() - started, 3), timeout_seconds=timeout)
            if not result["ok"]:
                self.shutdown(force=True)
                raise XcovError("NPI_NATIVE_FAILED", result["error"], operation=method)
            if method in MUTATIONS:
                self.revision += 1
            if method == 'test_handles' and decoded:
                self.sample_test = decoded[0].identity
            elif method == 'merge_test' and decoded is not None:
                self.sample_test = decoded.identity
            if method in {"close", "end"}:
                self.shutdown()
                if self.process.returncode != 0:
                    raise XcovError("NPI_WORKER_LOST", "native coverage worker did not exit cleanly", operation=method, value=str(self.process.returncode))
            return decoded

    def init(self, argv):
        return self.call("init")

    @contextmanager
    def operation(self):
        """All RPCs in one backend operation share the original 600s budget."""
        with self._lock:
            previous = self._deadline
            if previous is None:
                self._deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
            try:
                yield
            finally:
                self._deadline = previous

    def open(self, vdb, policy="default"):
        return self.call("open", vdb, policy)

    def merge_test(self, left, right):
        return self.call("merge_test", left, right)

    def release_handle(self, handle):
        with self._lock:
            # After confirmed worker death there are no native handles left.
            # Cleanup must not replace the original failed RPC with a close error.
            if self._ended and self.process.poll() is not None:
                return 1
            self._check_handle(handle)
            pending = [handle]
            while pending:
                item = pending.pop()
                if item.released:
                    continue
                if item.children is not None:
                    pending.extend(item.children)
                item.children = None
                item.properties.clear()
                item.released = True
                self._releases.append(item.identity)
                if item.identity == self.sample_test:
                    self.sample_test = 0
            if len(self._releases) >= 1024:
                self.call('flush')
            return 1

    def end(self):
        if self._ended:
            self.shutdown(force=True)
            return 1
        # call() owns cleanup and preserves the original timeout/crash detail.
        return self.call("end")

    def shutdown(self, *, force=False):
        if self._ended and self.process.poll() is not None:
            # A previously unconfirmed kill may have completed between retries.
            atexit.unregister(self.shutdown)
            return
        self._ended = True
        self._socket.close()
        if force and self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise XcovError('NPI_WORKER_CLEANUP_UNCONFIRMED',
                                'native worker exit could not be confirmed; retry cleanup') from exc
        finally:
            if self.process.poll() is not None:
                atexit.unregister(self.shutdown)

    def __del__(self):
        if hasattr(self, "_ended") and not self._ended:
            self.shutdown()


def open_native():
    worker = NativeCoverage()
    return worker, worker


def _worker_binary():
    return Path(__file__).resolve().parents[1] / 'libexec/xcov-npi-worker'


def native_operation(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        if not isinstance(self.cov, NativeCoverage):
            return method(self, *args, **kwargs)
        with self.cov.operation():
            return method(self, *args, **kwargs)
    return run
