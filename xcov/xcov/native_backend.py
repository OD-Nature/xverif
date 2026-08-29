from __future__ import annotations

import json
import os
import select
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backend import CoverageBackend, METRICS
from .coverage_contract import ALLOWED_FIELDS
from .errors import XcovError
from .query import coverage_pct

Json = Dict[str, Any]

# 2018 worker 在 branch/condition context 上额外输出的表达式/term/AST 扩展字段
# 不在上游封闭行合同 ALLOWED_FIELDS 内；适配层在返回前剥离，保持行合同可校验。
# 表达式分析能力的重移植是独立后续工作（worker 二进制仍保留该输出）。
_NON_CONTRACT_FIELDS_NOTE = (
    "branch_ast, branch_expression, branch_term_values, condition_ast, "
    "condition_expression, condition_term_values are dropped by the adapter"
)


def _strip_non_contract_fields(row: Any) -> Json:
    if not isinstance(row, dict):
        return row
    return {key: value for key, value in row.items() if key in ALLOWED_FIELDS}


class NativeNpiCoverageBackend(CoverageBackend):
    """Verdi 2018 coverage backend using a persistent C++ NPI worker.

    实现上游 CanonicalCoverageBackend 委托合同中的 worker 可服务子集
    （close/tests/summary/scopes/items）。exclusion、gap、容器解析等依赖
    pynpi/URG 的新协议能力以结构化错误显式拒绝，不做静默 fallback。
    """

    worker_kind = "npi_native_2018"

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
                env=self._worker_env(),
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

    def _worker_env(self) -> Dict[str, str]:
        """为 2018 worker 子进程准备 NPI 运行环境。

        npi_init 会在 LD_LIBRARY_PATH 各条目下查找 NPI 资源目录 etc/；rpath 只
        负责动态库加载，不覆盖该查找。注入仅作用于 worker 子进程，不污染宿主
        shell（见 xcov/docs/npi_2018_debug_notes.md 第 6 节）。
        """
        env = dict(os.environ)
        verdi_home = env.get("XVERIF_XCOV_VERDI_HOME") or env.get("VERDI_HOME", "")
        if not verdi_home:
            return env
        for relative in ("share/NPI/lib/LINUX64", "share/NPI/lib/linux64"):
            npi_lib = Path(verdi_home) / relative
            if not npi_lib.is_dir():
                continue
            entries = [str(npi_lib)]
            entries.extend(
                value for value in env.get("LD_LIBRARY_PATH", "").split(os.pathsep) if value
            )
            env["LD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(entries))
            break
        return env

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
        raw = dict(self._request("summary") or {}) if not self._closed else dict(self._summary_cache)
        self._summary_cache = {
            "test_count": raw.get("test_count"),
            "top_scope_count": raw.get("top_scope_count"),
        }
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
            self._items_cache[key] = [
                _strip_non_contract_fields(row)
                for row in (self._request("items", args) or [])
            ]
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

    def scope_metrics(self) -> Dict[str, Json]:
        """按 instance scope 聚合 score 行，映射到上游 canonical 指标合同。

        functional 不在 2018 worker 的 items 协议内，聚合结果天然不含该指标；
        上游 action 对缺失指标按 null 处理。
        """
        from .coverage_contract import coverage_row_kind

        rows = self.items()
        aggregated: Dict[str, Dict[str, Dict[str, int]]] = {}
        for row in rows:
            if coverage_row_kind(row) != "score":
                continue
            scope = row.get("scope")
            metric = row.get("metric")
            if not scope or metric not in METRICS:
                continue
            per_metric = aggregated.setdefault(str(scope), {})
            agg = per_metric.setdefault(metric, {"covered": 0, "coverable": 0})
            agg["covered"] += max(0, int(row.get("covered") or 0))
            agg["coverable"] += max(0, int(row.get("coverable") or 0))
        out: Dict[str, Json] = {}
        for scope, per_metric in aggregated.items():
            metrics: Json = {}
            for metric, agg in per_metric.items():
                covered = agg["covered"]
                coverable = agg["coverable"]
                metrics[metric] = {
                    "covered": covered,
                    "coverable": coverable,
                    "missing": coverable - covered,
                    "pct": round(100.0 * covered / coverable, 4) if coverable else None,
                }
            out[scope] = metrics
        return out

    def scope_functional_from_urg(self) -> List[Json]:
        self._unsupported("scope_functional_from_urg")

    def scope_assert_from_urg(self) -> List[Json]:
        self._unsupported("scope_assert_from_urg")

    def exact_scope_items(self, metrics: List[str], scope: str, test: str = "merged") -> List[Json]:
        self._unsupported("exact_scope_items")

    def functional_items_filtered(self, covergroups: set, test: str = "merged") -> List[Json]:
        self._unsupported("functional_items_filtered")

    def gap_items(self, metric: str, scope: Optional[str] = None,
                  test: str = "merged") -> List[Json]:
        self._unsupported("gap_items")

    def load_exclusions(self, paths: List[str], test: str = "merged") -> List[Json]:
        self._unsupported("load_exclusions")

    def set_exclusion(self, coverage_ref: str, excluded: bool, test: str = "merged") -> Json:
        self._unsupported("set_exclusion")

    def save_exclusions(self, path: str, test: str = "merged") -> None:
        self._unsupported("save_exclusions")

    def unload_exclusions(self, test: str = "merged") -> None:
        self._unsupported("unload_exclusions")

    def attach_gap_locators(self, payload: Json, test: str = "merged") -> Json:
        self._unsupported("attach_gap_locators")

    def set_exclusion_locator(self, locator: Json, excluded: bool = True,
                              test: str = "merged") -> Json:
        self._unsupported("set_exclusion_locator")

    def resolve_gap_payload(self, payload: Json, test: str = "merged") -> Json:
        self._unsupported("resolve_gap_payload")

    def resolve_container_records(self, records: List[Json], test: str = "merged") -> List[Json]:
        self._unsupported("resolve_container_records")

    def expand_xml_instances(self, root: str, recursive: bool) -> List[str]:
        self._unsupported("expand_xml_instances")

    def _unsupported(self, operation: str) -> None:
        raise XcovError(
            "NATIVE_BACKEND_UNSUPPORTED",
            "the Verdi 2018 native NPI worker does not implement this "
            "operation; it requires the upstream pynpi/URG backend path",
            operation=operation,
        )
