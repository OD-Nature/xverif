from __future__ import annotations

import json
import os
import select
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backend import CoverageBackend, METRICS
from .errors import XcovError
from .query import coverage_pct

Json = Dict[str, Any]


class NativeNpiCoverageBackend(CoverageBackend):
    """Verdi 2018 coverage backend using a persistent C++ NPI worker."""

    def __init__(self, vdb: str) -> None:
        self.vdb = vdb
        self._closed = False
        self._request_id = 0
        self._lock = threading.Lock()
        self._summary_cache: Json = {}
        self._scopes_cache: Optional[List[Json]] = None
        self._items_cache: Dict[tuple, List[Json]] = {}
        self._startup_timeout = float(os.environ.get("XVERIF_XCOV_NATIVE_START_TIMEOUT", "180"))
        self._query_timeout = float(os.environ.get("XVERIF_XCOV_NATIVE_QUERY_TIMEOUT", "300"))
        coverage_db = Path(vdb) / "snps" / "coverage" / "db"
        if not coverage_db.is_dir() or not any(path.is_file() for path in coverage_db.rglob("*")):
            raise XcovError(
                "INVALID_VDB",
                "coverage database is missing or contains no data files",
                vdb=os.path.abspath(vdb),
            )
        default_bin = Path(__file__).resolve().parents[1] / "native" / "xcov-npi-worker"
        worker = Path(os.environ.get("XVERIF_XCOV_NATIVE_BIN", str(default_bin)))
        if not worker.is_file() or not os.access(worker, os.X_OK):
            raise XcovError(
                "NATIVE_WORKER_NOT_FOUND",
                "native NPI worker is not built; run make -C xcov native",
                worker=str(worker),
            )
        try:
            self._proc = subprocess.Popen(
                [str(worker), os.path.abspath(vdb)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise XcovError("NATIVE_WORKER_START_FAILED", str(exc), worker=str(worker)) from exc

        ready_line = self._readline(self._startup_timeout, "startup")
        if not ready_line:
            rc = self._proc.poll()
            raise XcovError(
                "NATIVE_WORKER_START_FAILED",
                "native NPI worker exited before ready",
                exit_code=rc,
            )
        try:
            ready = json.loads(ready_line)
        except json.JSONDecodeError as exc:
            self.close()
            raise XcovError(
                "NATIVE_PROTOCOL_ERROR", "invalid native worker ready response"
            ) from exc
        if not ready.get("ok") or ready.get("protocol") != "xcov.native.v1":
            self.close()
            raise XcovError(
                "NATIVE_WORKER_START_FAILED",
                str(ready.get("error") or "native worker initialization failed"),
            )
        self._summary_cache = dict(self._request("summary") or {})

    def _readline(self, timeout: float, phase: str) -> str:
        if not self._proc.stdout:
            return ""
        ready, _, _ = select.select([self._proc.stdout], [], [], timeout)
        if not ready:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            raise XcovError(
                "NATIVE_WORKER_TIMEOUT",
                f"native NPI worker {phase} timed out",
                timeout_seconds=timeout,
            )
        return self._proc.stdout.readline()

    def _request(self, action: str, args: Optional[Json] = None) -> Any:
        if self._closed:
            raise XcovError("NATIVE_WORKER_CLOSED", "native NPI worker is closed")
        with self._lock:
            self._request_id += 1
            request = {"id": self._request_id, "action": action, "args": args or {}}
            if not self._proc.stdin or not self._proc.stdout:
                raise XcovError("NATIVE_PROTOCOL_ERROR", "native worker pipes are unavailable")
            try:
                self._proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                self._proc.stdin.flush()
                line = self._readline(self._query_timeout, action)
            except (BrokenPipeError, OSError) as exc:
                raise XcovError("NATIVE_WORKER_EXITED", str(exc)) from exc
            if not line:
                raise XcovError(
                    "NATIVE_WORKER_EXITED",
                    "native NPI worker exited while processing request",
                    exit_code=self._proc.poll(),
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise XcovError("NATIVE_PROTOCOL_ERROR", "invalid native worker response") from exc
            if response.get("id") != self._request_id:
                raise XcovError("NATIVE_PROTOCOL_ERROR", "native worker response id mismatch")
            if not response.get("ok"):
                error = response.get("error") if isinstance(response.get("error"), dict) else {}
                raise XcovError(
                    str(error.get("code") or "NATIVE_QUERY_FAILED"),
                    str(error.get("message") or "native NPI query failed"),
                )
            return response.get("data")

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._proc.poll() is None:
                try:
                    self._request("close")
                except XcovError:
                    self._proc.terminate()
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        finally:
            self._closed = True

    def tests(self) -> List[Json]:
        return list(self._request("tests") or [])

    def summary(self) -> Json:
        if self._closed:
            return dict(self._summary_cache)
        self._summary_cache = dict(self._request("summary") or {})
        return dict(self._summary_cache)

    def scopes(self) -> List[Json]:
        if self._scopes_cache is None:
            self._scopes_cache = list(self._request("scopes") or [])
        return [dict(row) for row in self._scopes_cache]

    def top_scopes(self) -> List[Json]:
        scopes = self.scopes()
        return [row for row in scopes if not row.get("parent")]

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        args: Json = {
            "metrics": metrics or METRICS,
            "test": test,
            "functional_only": bool(functional_only),
        }
        if scope:
            args["scope"] = scope
        key = (tuple(sorted(args["metrics"])), scope or "", test, bool(functional_only))
        if key not in self._items_cache:
            self._items_cache[key] = list(self._request("items", args) or [])
        return [dict(row) for row in self._items_cache[key]]

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        rows = self.items(scope=scope, test=test)
        out: List[Json] = []
        for metric in METRICS:
            subset = [row for row in rows if row.get("metric") == metric]
            if not subset:
                continue
            coverable = sum(max(0, int(row.get("coverable") or 0)) for row in subset)
            covered = sum(max(0, int(row.get("covered") or 0)) for row in subset)
            out.append({
                "metric": metric,
                "covered": covered,
                "coverable": coverable,
                "missing": coverable - covered,
                "coverage_pct": coverage_pct(covered, coverable),
            })
        return out
