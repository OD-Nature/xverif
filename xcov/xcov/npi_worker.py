"""One coverage database per native process; no vendor state crosses sessions."""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from .errors import XcovError

STARTUP_TIMEOUT_SEC = 120
REQUEST_TIMEOUT_SEC = 600
CLOSE_TIMEOUT_SEC = 5
STOP_TIMEOUT_SEC = 5

OPERATIONS = frozenset({
    "tests", "summary", "top_scopes", "scopes", "scope_metrics",
    "scope_functional_from_urg", "scope_assert_from_urg", "items",
    "exact_scope_items", "functional_items_filtered", "gap_items",
    "load_exclusions", "set_exclusion", "save_exclusions", "unload_exclusions",
    "attach_gap_locators", "set_exclusion_locator", "resolve_gap_payload",
    "resolve_container_records", "expand_xml_instances", "close",
})


class NpiWorker:
    def __init__(self, vdb: str, exclusion_policy: str) -> None:
        self._lock = threading.RLock()
        self._buffer = bytearray()
        self._closed = False
        env = dict(os.environ)
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
        self.process = subprocess.Popen(
            [sys.executable, "-m", "xcov.npi_worker", str(os.getpid()), vdb, exclusion_policy],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env,
        )
        assert self.process.stdin is not None and self.process.stdout is not None
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        atexit.register(self._stop)
        try:
            ready = self._receive(time.monotonic() + STARTUP_TIMEOUT_SEC)
            self._result(ready)
        except BaseException:
            self._stop()
            raise

    @staticmethod
    def _result(message: dict) -> Any:
        if not message["ok"]:
            error = message["error"]
            raise XcovError(error["code"], error["message"], **error["detail"])
        return message.get("result")

    def _wait(self, fd: int, deadline: float, *, writing: bool = False) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise XcovError("NPI_WORKER_TIMEOUT", "NPI worker exceeded its operation deadline")
        readable, writable, _ = select.select(
            [] if writing else [fd], [fd] if writing else [], [], remaining,
        )
        if not readable and not writable:
            raise XcovError("NPI_WORKER_TIMEOUT", "NPI worker exceeded its operation deadline")

    def _receive(self, deadline: float) -> dict:
        fd = self.process.stdout.fileno()
        while b"\n" not in self._buffer:
            self._wait(fd, deadline)
            chunk = os.read(fd, 65536)
            if not chunk:
                raise XcovError("NPI_WORKER_EXITED", "NPI worker exited before returning a result")
            self._buffer.extend(chunk)
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = bytearray(rest)
        try:
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
                raise ValueError("invalid worker response")
            return value
        except (ValueError, UnicodeError) as exc:
            raise XcovError("NPI_WORKER_PROTOCOL_ERROR", "invalid NPI worker response") from exc

    def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        if operation not in OPERATIONS:
            raise ValueError(f"unsupported NPI worker operation: {operation}")
        with self._lock:
            if self._closed:
                raise XcovError("NPI_WORKER_CLOSED", "NPI coverage session is closed")
            timeout = CLOSE_TIMEOUT_SEC if operation == "close" else REQUEST_TIMEOUT_SEC
            deadline = time.monotonic() + timeout
            payload = memoryview((json.dumps({"operation": operation, "args": args, "kwargs": kwargs}) + "\n").encode())
            fd = self.process.stdin.fileno()
            try:
                while payload:
                    self._wait(fd, deadline, writing=True)
                    payload = payload[os.write(fd, payload):]
                message = self._receive(deadline)
            except (OSError, XcovError) as exc:
                self._stop()
                if isinstance(exc, XcovError):
                    raise
                raise XcovError("NPI_WORKER_EXITED", "NPI worker communication failed") from exc
            return self._result(message)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                self._stop()
                return
            try:
                self.call("close")
                try:
                    code = self.process.wait(timeout=CLOSE_TIMEOUT_SEC)
                except subprocess.TimeoutExpired as exc:
                    raise XcovError("NPI_WORKER_TIMEOUT", "NPI worker did not exit after database close") from exc
                if code != 0:
                    raise XcovError("NPI_WORKER_EXITED", f"NPI worker failed during shutdown (return code {code})")
            finally:
                self._stop()

    def _stop(self) -> None:
        if self._closed and self.process.poll() is not None:
            return
        self._closed = True
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=STOP_TIMEOUT_SEC)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=STOP_TIMEOUT_SEC)
                    except subprocess.TimeoutExpired as exc:
                        raise XcovError(
                            "NPI_WORKER_CLEANUP_UNCONFIRMED",
                            "NPI worker did not exit after SIGKILL; cleanup must be retried",
                        ) from exc
        finally:
            self.process.stdin.close()
            self.process.stdout.close()
            if self.process.poll() is not None:
                atexit.unregister(self._stop)


def _serve() -> int:
    # Keep protocol output separate from vendor stdout, including late banners.
    output = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    backend = None

    def send(result: Any = None, error: XcovError | None = None) -> None:
        message = {"ok": error is None, "result": result}
        if error is not None:
            message["error"] = {"code": error.code, "message": error.message, "detail": error.detail}
        output.write(json.dumps(message) + "\n")
        output.flush()

    try:
        # Linux parent-death signal also covers an owner killed without closing stdin.
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "cannot set NPI worker parent-death signal")
        if os.getppid() != int(sys.argv[1]):
            return 1
        from .backend import _LocalNpiCoverageBackend
        backend = _LocalNpiCoverageBackend(sys.argv[2], exclusion_policy=sys.argv[3])
        send()
        for line in sys.stdin:
            request = json.loads(line)
            operation = request["operation"]
            if operation not in OPERATIONS:
                raise ValueError("unknown NPI operation")
            try:
                args = request["args"]
                if operation == "functional_items_filtered":
                    args[0] = set(args[0])
                result = getattr(backend, operation)(*args, **request["kwargs"])
                send(result)
            except XcovError as exc:
                send(error=exc)
            if operation == "close":
                return 0
        return 0
    except XcovError as exc:
        send(error=exc)
        return 1
    except Exception as exc:
        send(error=XcovError(
            "NPI_WORKER_FAILED", str(exc) or "unexpected NPI worker failure",
            cause_type=type(exc).__name__,
        ))
        return 1
    finally:
        if backend is not None:
            backend.close()
        output.close()


if __name__ == "__main__":
    raise SystemExit(_serve())
