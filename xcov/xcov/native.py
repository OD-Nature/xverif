"""Isolated native coverage RPC; no vendor Python binding or raw pointers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import tempfile

from .eda import resolve_verdi_home
from .errors import XcovError
from .logging import log_root


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
        self._socket.settimeout(120)
        try:
            self.process = subprocess.Popen(
                [str(binary), str(child.fileno())], pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL, stdout=2, stderr=2, env=env, cwd=self.log_directory,
            )
        except BaseException:
            self._socket.close()
            raise
        finally:
            child.close()
        self._reader = self._socket.makefile("rb")
        self._ended = False

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
                self.shutdown()
                raise XcovError("NPI_WORKER_LOST", "native coverage worker failed; reopen the session", operation=method, cause_message=str(exc)) from exc
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

    def shutdown(self):
        if self._ended:
            return
        self._ended = True
        self._reader.close()
        self._socket.close()
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
