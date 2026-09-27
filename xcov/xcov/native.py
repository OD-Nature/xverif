"""Isolated native coverage RPC; no vendor Python binding or raw pointers."""
from __future__ import annotations

import json
import ipaddress
import math
import os
from pathlib import Path
import socket
import subprocess
import threading
import tempfile
import time

from .eda import resolve_verdi_home
from .errors import XcovError
from .logging import log_root


INIT_TIMEOUT_ENV = "XVERIF_XCOV_NATIVE_INIT_TIMEOUT_SECONDS"
RPC_TIMEOUT_SECONDS = 120.0


def _init_timeout_seconds():
    raw = os.environ.get(INIT_TIMEOUT_ENV, str(RPC_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or not 0 < value <= 3600:
        raise XcovError("NPI_TIMEOUT_INVALID", "native init timeout must be finite and in (0, 3600] seconds", variable=INIT_TIMEOUT_ENV)
    return value


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
    def __init__(self, worker, identity):
        self.worker = worker
        self.identity = identity

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)
        return lambda *args: self.worker.call(method, *args, obj=self)


class NativeCoverage:
    def __init__(self):
        self.init_timeout_seconds = _init_timeout_seconds()
        home = Path(resolve_verdi_home())
        binary = Path(__file__).resolve().parents[1] / "libexec/xcov-npi-worker"
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise XcovError("NPI_WORKER_MISSING", "build and install xcov/libexec/xcov-npi-worker")
        env = os.environ.copy()
        env["VERDI_HOME"] = str(home)
        # SPI VDB loading crashes in libsnpsmalloc::mem_malloc on this runtime.
        # Keep the allocator selection local to the coverage worker.
        env["VCS_USE_MALLOC"] = "1"
        env["LD_LIBRARY_PATH"] = str(home / "share/NPI/lib/LINUX64") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        log_dir = log_root().resolve() / "native"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_directory = Path(tempfile.mkdtemp(prefix="worker-", dir=log_dir))
        self._lock = threading.RLock()
        self._socket, child = socket.socketpair()
        self._socket.settimeout(RPC_TIMEOUT_SECONDS)
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
        self._reader = self._socket.makefile("rb")
        self._ended = False
        self.diagnostic_path = self.log_directory / "native-status.json"

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
            if value.worker is not self:
                raise XcovError("NPI_HANDLE_INVALID", "handle belongs to a different coverage worker")
            return {"handle": value.identity}
        return value

    def _decode(self, value):
        if isinstance(value, dict) and set(value) == {"handle"}:
            return NativeHandle(self, value["handle"])
        if isinstance(value, list):
            return [self._decode(item) for item in value]
        return value

    def call(self, method, *args, obj=None):
        with self._lock:
            if self._ended:
                raise XcovError("NPI_WORKER_LOST", "coverage worker is closed", operation=method)
            timeout = self.init_timeout_seconds if method == "init" else RPC_TIMEOUT_SECONDS
            self._socket.settimeout(timeout)
            started = time.monotonic()
            if method in {"init", "open"}:
                self._status(state="waiting", operation=method, timeout_seconds=timeout)
            try:
                if method in {"open", "load_exclude_file", "save_exclude_file"}:
                    args = (os.path.abspath(args[0]), *args[1:])
                payload = {"method": method, "object": self._encode(obj), "args": [self._encode(v) for v in args]}
                self._socket.sendall((json.dumps(payload) + "\n").encode())
                line = self._reader.readline()
                if not line:
                    raise EOFError("native coverage worker exited")
                result = json.loads(line)
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
            if method in {"init", "open"}:
                self._status(state="completed" if result["ok"] else "failed", operation=method,
                             elapsed_seconds=round(time.monotonic() - started, 3), timeout_seconds=timeout)
            if not result["ok"]:
                raise XcovError("NPI_NATIVE_FAILED", result["error"], operation=method)
            decoded = self._decode(result["result"])
            if method in {"close", "end"}:
                self.shutdown()
                if self.process.returncode != 0:
                    raise XcovError("NPI_WORKER_LOST", "native coverage worker did not exit cleanly", operation=method, value=str(self.process.returncode))
            return decoded

    def init(self, argv):
        return self.call("init")

    def open(self, vdb, policy="default"):
        return self.call("open", vdb, policy)

    def merge_test(self, left, right):
        return self.call("merge_test", left, right)

    def release_handle(self, handle):
        return self.call("release_handle", handle)

    def end(self):
        if self._ended:
            return 1
        try:
            return self.call("end")
        finally:
            self.shutdown()
            if self.process.returncode != 0:
                raise XcovError("NPI_WORKER_LOST", "native coverage worker did not exit cleanly", operation="end", value=str(self.process.returncode))

    def shutdown(self, *, force=False):
        if self._ended:
            return
        self._ended = True
        self._reader.close()
        self._socket.close()
        if force and self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def __del__(self):
        if hasattr(self, "_ended") and not self._ended:
            self.shutdown()


def open_native():
    worker = NativeCoverage()
    return worker, worker
