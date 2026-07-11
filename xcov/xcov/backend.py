from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .errors import XcovError
from .logging import log_lifecycle_event
from .query import coverage_pct

Json = Dict[str, Any]

METRICS = ["line", "toggle", "branch", "condition", "fsm", "assert", "functional"]
METRIC_METHODS = {
    "line": "line_metric_handle",
    "toggle": "toggle_metric_handle",
    "branch": "branch_metric_handle",
    "condition": "condition_metric_handle",
    "fsm": "fsm_metric_handle",
    "assert": "assert_metric_handle",
    "functional": "testbench_metric_handle",
    "power": "power_metric_handle",
}


def _missing(covered: Any, coverable: Any) -> int | None:
    try:
        return int(coverable) - int(covered)
    except Exception:
        return None


class CoverageBackend:
    def close(self) -> None:
        pass

    def tests(self) -> List[Json]:
        raise NotImplementedError

    def summary(self) -> Json:
        tests = self.tests()
        top_scopes = self.top_scopes()
        return {"test_count": len(tests), "top_scope_count": len(top_scopes)}

    def top_scopes(self) -> List[Json]:
        scopes = self.scopes()
        return [s for s in scopes if "." not in str(s.get("full_name", ""))] or scopes

    def scopes(self) -> List[Json]:
        raise NotImplementedError

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        raise NotImplementedError

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        raise NotImplementedError


class FakeCoverageBackend(CoverageBackend):
    def __init__(self, vdb: str = "fake.vdb") -> None:
        self.vdb = vdb
        self._items = [
            {"metric": "line", "type": "npiCovStmtBin", "scope": "top.u_dut",
             "name": "stmt_12", "full_name": "top.u_dut.stmt_12",
             "covered": 1, "coverable": 1, "missing": 0, "count": 5,
             "coverage_pct": 100.0, "status": ["covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 12}},
            {"metric": "toggle", "type": "npiCovToggleBin", "scope": "top.u_dut.u_fifo",
             "name": "0 -> 1", "full_name": "top.u_dut.u_fifo.credit[0].0 -> 1",
             "toggle_signal": "top.u_dut.u_fifo.credit",
             "toggle_bit": "top.u_dut.u_fifo.credit[0]",
             "toggle_transition": "0 -> 1",
             "toggle_is_port": False,
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/fifo.sv", "line": 44}},
            {"metric": "toggle", "type": "npiCovToggleBin", "scope": "top.u_dut",
             "name": "1 -> 0", "full_name": "top.u_dut.PRESETn.1 -> 0",
             "toggle_signal": "top.u_dut.PRESETn",
             "toggle_bit": "top.u_dut.PRESETn",
             "toggle_transition": "1 -> 0",
             "toggle_is_port": True,
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/uart_top.sv", "line": 5}},
            {"metric": "branch", "type": "npiCovBranchBin", "scope": "top.u_dut.u_ctrl",
             "name": "else", "full_name": "top.u_dut.u_ctrl.branch_8.else",
             "branch": "if (enable)",
             "branch_bin": "else",
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 88}},
            {"metric": "branch", "type": "npiCovBranchBin", "scope": "top.u_dut.u_ctrl",
             "name": "000000100", "full_name": "top.u_dut.u_ctrl.branch_9.000000100",
             "branch": "case (filter)",
             "branch_bin": "000000100",
             "branch_expression": "case (filter)",
             "branch_terms": "filter:2",
             "branch_term_values": [{"index": 0, "name": "filter", "value": "2"}],
             "branch_ast": {"opcode": 3, "name": "filter", "expression": "filter"},
             "branch_mask": {"encoding": "one_hot", "branch_arm_index": 2},
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 95}},
            {"metric": "condition", "type": "npiCovConditionBin", "scope": "top.u_dut.u_ctrl",
             "name": "10", "full_name": "top.u_dut.u_ctrl.cond_9.10",
             "condition": "(enable && ready)",
             "condition_bin": "10",
             "condition_terms": "enable;ready",
             "condition_expression": "enable && ready",
             "condition_term_values": [
                 {"index": 0, "name": "enable", "value": "1"},
                 {"index": 1, "name": "ready", "value": "0"},
             ],
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 91},
             "evidence_source": {"inherited": True, "type": "npiCovCondition",
                                 "name": "(enable && ready)",
                                 "full_name": "top.u_dut.u_ctrl.cond_9"}},
            {"metric": "assert", "type": "npiCovAssert", "scope": "top.u_dut.u_ctrl",
             "name": "p_ready", "full_name": "top.u_dut.u_ctrl.p_ready",
             "assert_kind": "assertion", "assert_object": "top.u_dut.u_ctrl.p_ready",
             "severity": 0, "category": 0,
             "covered": 0, "coverable": 1, "missing": 1, "count": -1,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 120}},
            {"metric": "assert", "type": "npiCovAttemptBin", "scope": "top.u_dut.u_ctrl",
             "name": "Attempt", "full_name": "top.u_dut.u_ctrl.p_ready.Attempt",
             "assert_kind": "assertion", "assert_object": "top.u_dut.u_ctrl.p_ready",
             "covered": -1, "coverable": -1, "missing": 0, "count": 10,
             "coverage_pct": None, "status": ["attempted"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 120}},
            {"metric": "assert", "type": "npiCovSuccessBin", "scope": "top.u_dut.u_ctrl",
             "name": "Success", "full_name": "top.u_dut.u_ctrl.p_ready.Success",
             "assert_kind": "assertion", "assert_object": "top.u_dut.u_ctrl.p_ready",
             "covered": -1, "coverable": -1, "missing": 0, "count": 8,
             "coverage_pct": None, "status": ["covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 120}},
            {"metric": "assert", "type": "npiCovFailureBin", "scope": "top.u_dut.u_ctrl",
             "name": "Failure", "full_name": "top.u_dut.u_ctrl.p_ready.Failure",
             "assert_kind": "assertion", "assert_object": "top.u_dut.u_ctrl.p_ready",
             "covered": -1, "coverable": -1, "missing": 0, "count": 1,
             "coverage_pct": None, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 120}},
            {"metric": "assert", "type": "npiCovIncompleteBin", "scope": "top.u_dut.u_ctrl",
             "name": "Incomplete", "full_name": "top.u_dut.u_ctrl.p_ready.Incomplete",
             "assert_kind": "assertion", "assert_object": "top.u_dut.u_ctrl.p_ready",
             "covered": -1, "coverable": -1, "missing": 0, "count": 1,
             "coverage_pct": None, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 120}},
            {"metric": "assert", "type": "npiCovCoverSequence", "scope": "top.u_dut.u_ctrl",
             "name": "seq_ready", "full_name": "top.u_dut.u_ctrl.seq_ready",
             "assert_kind": "cover_sequence", "assert_object": "top.u_dut.u_ctrl.seq_ready",
             "severity": 0, "category": 0,
             "covered": 1, "coverable": 1, "missing": 0, "count": -1,
             "coverage_pct": 100.0, "status": ["covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 130}},
            {"metric": "assert", "type": "npiCovFirstmatchBin", "scope": "top.u_dut.u_ctrl",
             "name": "Firstmatch", "full_name": "top.u_dut.u_ctrl.seq_ready.Firstmatch",
             "assert_kind": "cover_sequence", "assert_object": "top.u_dut.u_ctrl.seq_ready",
             "covered": -1, "coverable": -1, "missing": 0, "count": 3,
             "coverage_pct": None, "status": ["covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 130}},
            {"metric": "functional", "type": "npiCovCovergroup", "scope": "top.u_dut",
             "name": "cg_credit", "full_name": "top.u_dut.cg_credit",
             "covergroup": "cg_credit", "covered": 0, "coverable": 1, "missing": 1,
             "count": -1, "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 21}},
            {"metric": "functional", "type": "npiCovCoverpoint", "scope": "top.u_dut",
             "name": "cp_level", "full_name": "top.u_dut.cg_credit.cp_level",
             "covergroup": "cg_credit", "coverpoint": "cp_level", "covered": 0,
             "coverable": 1, "missing": 1, "count": -1, "coverage_pct": 0.0,
             "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 22}},
            {"metric": "functional", "type": "npiCovCoverBin", "scope": "top.u_dut",
             "name": "zero_credit", "full_name": "top.u_dut.cg_credit.cp_level.zero_credit",
             "covergroup": "cg_credit", "coverpoint": "cp_level", "cross": None,
             "bin": "zero_credit", "covered": 0, "coverable": 1, "missing": 1,
             "count": 0, "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 22},
             "evidence_source": {"inherited": True, "type": "npiCovCoverpoint",
                                 "name": "cp_level",
                                 "full_name": "top.u_dut.cg_credit.cp_level"}},
        ]

    def tests(self) -> List[Json]:
        return [{"name": f"{self.vdb}/test"}]

    def summary(self) -> Json:
        return {"test_count": 1, "top_scope_count": len(self.top_scopes())}

    def top_scopes(self) -> List[Json]:
        top_names = sorted({str(i["scope"]).split(".")[0] for i in self._items})
        return [_scope_row(n) for n in top_names]

    def scopes(self) -> List[Json]:
        names = sorted(_scope_closure(i["scope"] for i in self._items))
        return [_scope_row(n) for n in names]

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        self._check_test(test)
        rows = self.items(scope=scope, test=test)
        out = []
        for metric in sorted({r["metric"] for r in rows}):
            subset = [r for r in rows if r["metric"] == metric]
            coverable = sum(int(r.get("coverable") or 0) for r in subset)
            covered = sum(int(r.get("covered") or 0) for r in subset)
            out.append({"metric": metric, "coverable": coverable, "covered": covered,
                        "missing": coverable - covered,
                        "coverage_pct": coverage_pct(covered, coverable)})
        return out

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        self._check_test(test)
        rows = list(self._items)
        if metrics:
            rows = [r for r in rows if r.get("metric") in metrics]
        if scope:
            rows = [r for r in rows if str(r.get("scope", "")).startswith(scope)]
        if functional_only:
            rows = [r for r in rows if r.get("metric") == "functional"]
        return [dict(r) for r in rows]

    def _check_test(self, test: str) -> None:
        if test == "each":
            raise XcovError("TEST_MODE_NOT_SUPPORTED",
                            'test="each" is not implemented yet; use test="merged" or a concrete test name')


@dataclass
class NpiCoverageBackend(CoverageBackend):
    vdb: str
    python_kind: str = "current"
    cov: Any = None
    npisys: Any = None
    db: Any = None
    merged_test: Any = None
    test_map: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        log_lifecycle_event("adhoc", "npi.init.begin", True, {"vdb": self.vdb})
        verdi_home = os.environ.get("XVERIF_XCOV_VERDI_HOME") or os.environ.get("VERDI_HOME")
        if not verdi_home:
            log_lifecycle_event("adhoc", "npi.init.failed", False,
                                {"vdb": self.vdb, "reason": "VERDI_HOME is required"})
            raise XcovError("NPI_INIT_FAILED", "VERDI_HOME is required")
        sys.path.append(os.path.abspath(os.path.join(verdi_home, "share/NPI/python")))
        try:
            from pynpi import cov, npisys  # type: ignore
        except Exception as exc:
            log_lifecycle_event("adhoc", "npi.import.failed", False,
                                {"vdb": self.vdb, "error": str(exc)})
            raise XcovError("NPI_INIT_FAILED", f"failed to import pynpi: {exc}") from exc
        self.cov = cov
        self.npisys = npisys
        with _redirect_stdout_to_stderr():
            init_ok = npisys.init(sys.argv)
        if init_ok != 1:
            log_lifecycle_event("adhoc", "npi.init.failed", False,
                                {"vdb": self.vdb, "init_ok": init_ok})
            raise XcovError("NPI_INIT_FAILED", "npisys.init failed")
        log_lifecycle_event("adhoc", "npi.init.ok", True, {"vdb": self.vdb})
        log_lifecycle_event("adhoc", "vdb.open.begin", True, {"vdb": self.vdb})
        with _redirect_stdout_to_stderr():
            self.db = cov.open(self.vdb)
        if not self.db:
            log_lifecycle_event("adhoc", "vdb.open.failed", False, {"vdb": self.vdb})
            raise XcovError("VDB_OPEN_FAILED", "cov.open returned empty handle", vdb=self.vdb)
        log_lifecycle_event("adhoc", "vdb.open.ok", True, {"vdb": self.vdb})
        tests = self.db.test_handles()
        for test in tests:
            self.test_map[test.name()] = test
        self.merged_test = None
        for test in tests:
            self.merged_test = test if self.merged_test is None else cov.merge_test(self.merged_test, test)

    def close(self) -> None:
        try:
            if self.db:
                log_lifecycle_event("adhoc", "vdb.close.begin", True, {"vdb": self.vdb})
                with _redirect_stdout_to_stderr():
                    self.db.close()
                log_lifecycle_event("adhoc", "vdb.close.ok", True, {"vdb": self.vdb})
        finally:
            if self.npisys:
                log_lifecycle_event("adhoc", "npi.end.begin", True, {"vdb": self.vdb})
                with _redirect_stdout_to_stderr():
                    self.npisys.end()
                log_lifecycle_event("adhoc", "npi.end.ok", True, {"vdb": self.vdb})

    def tests(self) -> List[Json]:
        return [{"name": name} for name in sorted(self.test_map)]

    def _test_handle(self, test: str) -> Any:
        if test in ("merged", "", None):
            return self.merged_test
        if test == "each":
            raise XcovError("TEST_MODE_NOT_SUPPORTED",
                            'test="each" is not implemented yet; use test="merged" or a concrete test name')
        if test in self.test_map:
            return self.test_map[test]
        raise XcovError("TEST_NOT_FOUND", "test not found", test=test)

    def summary(self) -> Json:
        return {"test_count": len(self.test_map), "top_scope_count": None}

    def top_scopes(self) -> List[Json]:
        rows: List[Json] = []
        for inst in self.db.instance_handles():
            rows.append(self._scope_row_from_inst(inst))
        return rows

    def scopes(self) -> List[Json]:
        rows: List[Json] = []
        for inst in self.db.instance_handles():
            self._walk_scopes(inst, rows)
            self.cov.release_handle(inst)
        return rows

    def _scope_row_from_inst(self, inst: Any) -> Json:
        full_name = _safe_call(inst, "full_name") or _safe_call(inst, "name")
        return {
            "name": _safe_call(inst, "name"),
            "full_name": full_name,
            "parent": _scope_parent(str(full_name or "")),
            "depth": _scope_depth(str(full_name or "")),
            "type": _safe_call(inst, "type"),
            "def_name": _safe_call(inst, "def_name"),
            "evidence": {"file": _safe_call(inst, "file_name"), "line": _safe_call(inst, "line_no")},
        }

    def _walk_scopes(self, inst: Any, rows: List[Json]) -> None:
        rows.append(self._scope_row_from_inst(inst))
        for child in _safe_list(inst, "instance_handles"):
            self._walk_scopes(child, rows)
            self.cov.release_handle(child)

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        items = self.items(scope=scope, test=test)
        rows: List[Json] = []
        for metric in METRICS:
            subset = [r for r in items if r.get("metric") == metric]
            if not subset:
                continue
            coverable = sum(int(r.get("coverable") or 0) for r in subset)
            covered = sum(int(r.get("covered") or 0) for r in subset)
            rows.append({"metric": metric, "coverable": coverable, "covered": covered,
                         "missing": coverable - covered,
                         "coverage_pct": coverage_pct(covered, coverable)})
        return rows

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        test_hdl = self._test_handle(test)
        wanted = metrics or METRICS
        if functional_only and "functional" not in wanted:
            wanted = ["functional"]
        rows: List[Json] = []
        design_metrics = [metric for metric in wanted if metric != "functional"]
        if design_metrics and not functional_only:
            for inst in self.db.instance_handles():
                self._walk_items(inst, test_hdl, design_metrics, scope, rows)
                self.cov.release_handle(inst)
        if "functional" in wanted:
            self._walk_functional_items(test_hdl, scope, rows)
        return rows

    def _walk_items(self, inst: Any, test_hdl: Any, wanted: List[str],
                    scope: Optional[str], rows: List[Json]) -> None:
        inst_full = _safe_call(inst, "full_name") or _safe_call(inst, "name")
        if scope is None or str(inst_full).startswith(scope):
            for metric in wanted:
                method = METRIC_METHODS.get(metric)
                if not method or not hasattr(inst, method):
                    continue
                metric_hdl = _safe_call(inst, method)
                if metric_hdl:
                    try:
                        self._walk_metric(metric_hdl, metric, inst_full, test_hdl, rows)
                    finally:
                        self.release_if_handle(metric_hdl)
        for child in _safe_list(inst, "instance_handles"):
            self._walk_items(child, test_hdl, wanted, scope, rows)
            self.cov.release_handle(child)

    def release_if_handle(self, hdl: Any) -> None:
        if hdl:
            try:
                self.cov.release_handle(hdl)
            except Exception:
                pass

    def _walk_metric(self, hdl: Any, metric: str, scope: str, test_hdl: Any,
                     rows: List[Json]) -> None:
        for child in _safe_list(hdl, "child_handles"):
            self._walk_leaf(child, metric, scope, test_hdl, rows, {}, None)
            self.cov.release_handle(child)

    def _walk_functional_items(self, test_hdl: Any, scope: Optional[str],
                               rows: List[Json]) -> None:
        metric_hdl = _safe_call(test_hdl, "testbench_metric_handle")
        if not metric_hdl:
            return
        try:
            for child in _safe_list(metric_hdl, "child_handles"):
                self._walk_functional_leaf(child, test_hdl, rows, {}, scope, None)
                self.cov.release_handle(child)
        finally:
            self.release_if_handle(metric_hdl)

    def _walk_functional_leaf(self, hdl: Any, test_hdl: Any, rows: List[Json],
                              functional_path: Json, scope_filter: Optional[str],
                              parent_source: Optional[Json]) -> None:
        typ = _safe_call(hdl, "type")
        name = _safe_call(hdl, "name")
        path = dict(functional_path)
        if typ == "npiCovCovergroup":
            path = {"covergroup": name}
        elif typ == "npiCovCoverpoint":
            path["coverpoint"] = name
        elif typ == "npiCovCross":
            path["cross"] = name
        elif typ == "npiCovCoverBin":
            path["bin"] = name
        scope = _functional_scope(path.get("covergroup"))
        full_name = _functional_full_name(path, _safe_call(hdl, "full_name") or name)
        raw_evidence = {"file": _safe_call(hdl, "file_name"),
                        "line": _safe_call(hdl, "line_no", test_hdl)}
        own_source = _functional_source(typ, name, full_name, raw_evidence)
        row_source = own_source or parent_source
        evidence = dict(row_source["evidence"]) if row_source else raw_evidence
        if scope_filter is None or str(scope or full_name).startswith(scope_filter):
            covered = _safe_call(hdl, "covered", test_hdl)
            coverable = _safe_call(hdl, "coverable", test_hdl)
            count = _safe_call(hdl, "count", test_hdl)
            if coverable is not None:
                status = _status_flags(hdl, test_hdl, covered, coverable)
                rows.append({
                    "metric": "functional",
                    "type": typ,
                    "scope": scope,
                    "name": name,
                    "full_name": full_name,
                    "covered": covered,
                    "coverable": coverable,
                    "missing": _missing(covered, coverable),
                    "count": count,
                    "coverage_pct": coverage_pct(covered, coverable),
                    "status": status,
                    "evidence": evidence,
                    **path,
                })
                if row_source and row_source is not own_source:
                    rows[-1]["evidence_source"] = {
                        "inherited": True,
                        "type": row_source.get("type"),
                        "name": row_source.get("name"),
                        "full_name": row_source.get("full_name"),
                    }
        for child in _safe_list(hdl, "child_handles"):
            self._walk_functional_leaf(child, test_hdl, rows, path, scope_filter,
                                       own_source or parent_source)
            self.cov.release_handle(child)

    def _walk_leaf(self, hdl: Any, metric: str, scope: str, test_hdl: Any,
                   rows: List[Json], coverage_path: Json,
                   parent_source: Optional[Json]) -> None:
        typ = _safe_call(hdl, "type")
        name = _safe_call(hdl, "name")
        full_name = _safe_call(hdl, "full_name") or name
        path = _code_coverage_path(metric, typ, hdl, test_hdl, name, full_name,
                                   coverage_path, self.release_if_handle)
        if metric == "functional":
            if typ == "npiCovCovergroup":
                path["covergroup"] = name
            elif typ == "npiCovCoverpoint":
                path["coverpoint"] = name
            elif typ == "npiCovCross":
                path["cross"] = name
            elif typ == "npiCovCoverBin":
                path["bin"] = name
        covered = _safe_call(hdl, "covered", test_hdl)
        coverable = _safe_call(hdl, "coverable", test_hdl)
        count = _safe_call(hdl, "count", test_hdl)
        raw_evidence = {"file": _safe_call(hdl, "file_name"),
                        "line": _safe_call(hdl, "line_no", test_hdl)}
        own_source = _coverage_source(typ, name, full_name, raw_evidence)
        row_source = own_source or parent_source
        evidence = dict(row_source["evidence"]) if row_source else raw_evidence
        if coverable is not None:
            status = _status_flags(hdl, test_hdl, covered, coverable)
            row = {
                "metric": metric,
                "type": typ,
                "scope": scope,
                "name": name,
                "full_name": full_name,
                "covered": covered,
                "coverable": coverable,
                "missing": _missing(covered, coverable),
                "count": count,
                "coverage_pct": coverage_pct(covered, coverable),
                "status": status,
                "evidence": evidence,
                **path,
            }
            value = _coverage_value(hdl, test_hdl)
            if value is not None:
                row["value"] = value
            if metric == "toggle":
                transition = _toggle_transition(hdl, test_hdl, name)
                if transition is not None:
                    row["toggle_transition"] = transition
            if row_source and row_source is not own_source:
                row["evidence_source"] = {
                    "inherited": True,
                    "type": row_source.get("type"),
                    "name": row_source.get("name"),
                    "full_name": row_source.get("full_name"),
                }
            if (metric == "branch" and typ == "npiCovBranchBin"
                    and _branch_mask_hint_enabled()
                    and "branch_bin" in row):
                bv = row["branch_bin"]
                if isinstance(bv, str):
                    hint = _branch_mask_hint(bv)
                    if hint is not None:
                        row["branch_mask"] = hint
            rows.append(row)
        for child in _safe_list(hdl, "child_handles"):
            self._walk_leaf(child, metric, scope, test_hdl, rows, path,
                            own_source or parent_source)
            self.cov.release_handle(child)


def _code_coverage_path(metric: str, typ: Any, hdl: Any, test_hdl: Any,
                        name: Any, full_name: Any, coverage_path: Json,
                        release_handle: Any) -> Json:
    path = dict(coverage_path)
    label = str(full_name or name or "")
    short = str(name or full_name or "")
    if metric == "toggle":
        if typ == "npiCovSignal":
            path["toggle_signal"] = label
            is_port = _safe_call(hdl, "is_port", test_hdl)
            if is_port not in (None, -1, "-1"):
                path["toggle_is_port"] = bool(is_port)
        elif typ == "npiCovSignalBit":
            path["toggle_bit"] = label
            parent = _parent_from_bit(label)
            path.setdefault("toggle_signal", parent or label)
            is_port = _safe_call(hdl, "is_port", test_hdl)
            if is_port not in (None, -1, "-1"):
                path["toggle_is_port"] = bool(is_port)
        elif typ == "npiCovToggleBin":
            path.setdefault("toggle_transition", _toggle_transition(hdl, test_hdl, short))
    elif metric == "assert":
        kind = _assert_kind(typ)
        if kind:
            path["assert_kind"] = kind
            path["assert_object"] = label or short
            severity = _safe_call(hdl, "severity", test_hdl)
            category = _safe_call(hdl, "category", test_hdl)
            if severity not in (None, -1, "-1"):
                path["severity"] = severity
            if category not in (None, -1, "-1"):
                path["category"] = category
        elif typ in ASSERT_BIN_TYPES:
            path.setdefault("assert_bin", short)
    elif metric == "condition":
        if typ == "npiCovCondition":
            path["condition"] = label or short
            terms = _term_summary(hdl, "condition_term_handles", test_hdl, release_handle)
            if terms:
                path["condition_terms"] = terms
        elif typ == "npiCovConditionBin":
            path["condition_bin"] = _coverage_value(hdl, test_hdl) or short
    elif metric == "branch":
        if typ == "npiCovBranch":
            path["branch"] = label or short
            terms = _term_summary(hdl, "branch_term_handles", test_hdl, release_handle)
            if terms:
                path["branch_terms"] = terms
        elif typ == "npiCovBranchBin":
            path["branch_bin"] = _coverage_value(hdl, test_hdl) or short
    return {k: v for k, v in path.items() if v not in (None, "")}


ASSERT_OBJECT_KINDS = {
    "npiCovAssert": "assertion",
    "npiCovCoverProperty": "cover_property",
    "npiCovCoverSequence": "cover_sequence",
}

ASSERT_BIN_TYPES = {
    "npiCovAttemptBin",
    "npiCovSuccessBin",
    "npiCovFailureBin",
    "npiCovIncompleteBin",
    "npiCovFirstmatchBin",
}


def _assert_kind(typ: Any) -> str | None:
    return ASSERT_OBJECT_KINDS.get(str(typ or ""))


def _parent_from_bit(label: str) -> str | None:
    if "[" in label and label.endswith("]"):
        return label.rsplit("[", 1)[0]
    if "." in label:
        return label.rsplit(".", 1)[0]
    return None


def _coverage_value(hdl: Any, test_hdl: Any) -> Any:
    value = _safe_call(hdl, "value", test_hdl)
    if value is None:
        value = _safe_call(hdl, "value")
    if value in (None, ""):
        return None
    if value == -1 or value == "-1":
        return None
    return value


def _toggle_transition(hdl: Any, test_hdl: Any, fallback: Any) -> str | None:
    value = _safe_call(hdl, "toggle_type", test_hdl)
    if value is None:
        value = _safe_call(hdl, "toggle_type")
    if value in (None, "", -1, "-1"):
        value = fallback
    return str(value) if value not in (None, "") else None


def _term_summary(hdl: Any, method: str, test_hdl: Any, release_handle: Any) -> str | None:
    parts: List[str] = []
    for term in _safe_list(hdl, method):
        try:
            label = _safe_call(term, "name") or _safe_call(term, "full_name")
            value = _coverage_value(term, test_hdl)
            if label and value is not None and str(value) != str(label):
                parts.append(f"{label}:{value}")
            elif label:
                parts.append(str(label))
            elif value is not None:
                parts.append(str(value))
        finally:
            release_handle(term)
    return ";".join(parts) if parts else None


def _coverage_source(typ: Any, name: Any, full_name: Any, evidence: Json) -> Json | None:
    if not _valid_evidence(evidence):
        return None
    return {
        "type": typ,
        "name": name,
        "full_name": full_name,
        "evidence": dict(evidence),
    }


def _safe_call(obj: Any, name: str, *args: Any) -> Any:
    try:
        fn = getattr(obj, name)
    except Exception:
        return None
    try:
        return fn(*args)
    except Exception:
        try:
            return fn()
        except Exception:
            return None


def _safe_list(obj: Any, name: str) -> List[Any]:
    value = _safe_call(obj, name)
    return list(value or [])


def _scope_parent(full_name: str) -> str | None:
    if "." not in full_name:
        return None
    return full_name.rsplit(".", 1)[0]


def _scope_depth(full_name: str) -> int:
    return full_name.count(".")


def _scope_row(full_name: str) -> Json:
    return {
        "name": full_name.rsplit(".", 1)[-1],
        "full_name": full_name,
        "parent": _scope_parent(full_name),
        "depth": _scope_depth(full_name),
        "type": "npiCovInstance",
    }


def _scope_closure(scopes: Iterable[str]) -> List[str]:
    names = set()
    for scope in scopes:
        parts = str(scope).split(".")
        for idx in range(1, len(parts) + 1):
            names.add(".".join(parts[:idx]))
    return sorted(names)


def _functional_scope(covergroup: Any) -> str | None:
    if not covergroup:
        return None
    name = str(covergroup)
    if "::" not in name:
        return name.rsplit(".", 1)[0] if "." in name else None
    prefix = name.split("::", 1)[0]
    return prefix if "." in prefix else None


def _functional_full_name(path: Json, fallback: Any) -> str:
    parts = [
        path.get("covergroup"),
        path.get("coverpoint") or path.get("cross"),
        path.get("bin"),
    ]
    names = [str(part) for part in parts if part not in (None, "")]
    if names:
        return ".".join(names)
    return str(fallback or "")


def _functional_source(typ: Any, name: Any, full_name: Any, evidence: Json) -> Json | None:
    if not _valid_evidence(evidence):
        return None
    return {
        "type": typ,
        "name": name,
        "full_name": full_name,
        "evidence": dict(evidence),
    }


def _valid_evidence(evidence: Json) -> bool:
    if not evidence.get("file"):
        return False
    try:
        return int(evidence.get("line") or 0) > 0
    except Exception:
        return False


def _status_flags(hdl: Any, test_hdl: Any, covered: Any, coverable: Any) -> List[str]:
    flags: List[str] = []
    for method, flag in [
        ("has_status_excluded", "excluded"),
        ("has_status_partially_excluded", "partially_excluded"),
        ("has_status_excluded_at_compile_time", "excluded_at_compile_time"),
        ("has_status_excluded_at_report_time", "excluded_at_report_time"),
        ("has_status_unreachable", "unreachable"),
        ("has_status_illegal", "illegal"),
        ("has_status_proven", "proven"),
        ("has_status_attempted", "attempted"),
        ("has_status_partially_attempted", "partially_attempted"),
    ]:
        try:
            if getattr(hdl, method)(test_hdl):
                flags.append(flag)
        except Exception:
            pass
    try:
        if int(covered or 0) >= int(coverable or 0) and int(coverable or 0) > 0:
            flags.insert(0, "covered")
        else:
            flags.insert(0, "not_covered")
    except Exception:
        flags.insert(0, "not_covered")
    return flags


def _branch_mask_hint_enabled() -> bool:
    return str(os.environ.get("XVERIF_XCOV_BRANCH_MASK_HINT", "1")).lower() not in {
        "0", "false", "no", "off",
    }


def _branch_mask_hint(mask: str) -> dict | None:
    """Decode branch bin bitmask into human-readable hints.

    Returns None when *mask* is empty or contains characters other than
    ``0``, ``1``, or ``-``.

    Encoding classifications:

    * ``path``      — mask contains ``-`` (don't-care) positions; used for
                      FSM always-block branches.
    * ``one_hot``   — exactly one ``1``, no ``-``; bit position (LSB=0)
                      indexes the case item or branch arm.
    * ``multi_bit`` — multiple ``1`` positions, no ``-``; encodes a path
                      through nested if-else chains.
    """
    if not mask or not all(c in "01-" for c in mask):
        return None
    ones = [i for i, ch in enumerate(reversed(mask)) if ch == "1"]
    zeros = [i for i, ch in enumerate(reversed(mask)) if ch == "0"]
    dontcares = sum(1 for ch in mask if ch == "-")
    hint: dict = {}
    if dontcares > 0:
        hint["encoding"] = "path"
        hint["active_bits"] = len(ones) + len(zeros)
        hint["dontcare_bits"] = dontcares
    elif len(ones) == 1:
        hint["encoding"] = "one_hot"
        hint["branch_arm_index"] = ones[0]
    else:
        hint["encoding"] = "multi_bit"
        hint["one_positions"] = ones
    return hint


@contextmanager
def _redirect_stdout_to_stderr():
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
