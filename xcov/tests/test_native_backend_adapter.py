"""Hermetic tests for the Verdi 2018 native NPI backend adapter.

这些测试不启动 native worker、不访问真实 VDB，只验证适配层与上游
CanonicalCoverageBackend 委托合同的静态契约。
"""

import json

import pytest

from xcov.backend import CoverageBackend
from xcov.coverage_contract import ALLOWED_FIELDS
from xcov.errors import XcovError
from xcov.native_backend import NativeNpiCoverageBackend, _strip_non_contract_fields


def test_native_backend_declares_upstream_worker_kind():
    assert NativeNpiCoverageBackend.worker_kind == "npi_native_2018"
    assert issubclass(NativeNpiCoverageBackend, CoverageBackend)


def test_strip_non_contract_fields_drops_expression_extensions():
    row = {
        "metric": "branch",
        "type": "npiCovBranchBin",
        "scope": "top.u_dut",
        "name": "else",
        "full_name": "top.u_dut.u_ctrl.branch_8.else",
        "covered": 0,
        "coverable": 1,
        "missing": 1,
        "count": 0,
        "coverage_pct": 0.0,
        "status": ["not_covered"],
        "evidence": {"file": "rtl/ctrl.sv", "line": 88},
        "branch": "if (enable)",
        "branch_bin": "else",
        "branch_expression": "if (enable)",
        "branch_ast": {"opcode": 3, "name": "enable"},
        "branch_term_values": [{"index": 0, "name": "enable", "value": "1"}],
    }
    clean = _strip_non_contract_fields(row)
    assert set(clean) <= ALLOWED_FIELDS
    assert clean["branch_bin"] == "else"
    assert clean["evidence"] == {"file": "rtl/ctrl.sv", "line": 88}
    assert not {"branch_expression", "branch_ast", "branch_term_values"} & set(clean)


def test_strip_non_contract_fields_keeps_evidence_source_and_toggle_fields():
    row = {
        "metric": "toggle",
        "type": "npiCovToggleBin",
        "name": "0 -> 1",
        "full_name": "top.u_dut.credit[0].0 -> 1",
        "toggle_signal": "top.u_dut.credit",
        "toggle_bit": "top.u_dut.credit[0]",
        "toggle_transition": "0 -> 1",
        "toggle_is_port": False,
        "status": ["not_covered"],
        "evidence_source": {"inherited": True, "type": "npiCovSignal",
                            "name": "credit", "full_name": "top.u_dut.credit"},
    }
    clean = _strip_non_contract_fields(row)
    assert set(clean) <= ALLOWED_FIELDS
    assert clean["toggle_signal"] == "top.u_dut.credit"
    assert clean["evidence_source"]["name"] == "credit"


def _backend_without_worker() -> NativeNpiCoverageBackend:
    backend = object.__new__(NativeNpiCoverageBackend)
    backend.vdb = "fake.vdb"
    backend._closed = False
    backend._request_id = 0
    backend._lock = __import__("threading").Lock()
    backend._summary_cache = {}
    backend._scopes_cache = None
    backend._items_cache = {}
    return backend


def test_summary_projects_to_closed_canonical_shape():
    backend = _backend_without_worker()
    backend._request = lambda action, args=None: {
        "test_count": 2,
        "top_scope_count": 1,
        "extra_field": "must-not-leak",
    }
    summary = backend.summary()
    assert summary == {"test_count": 2, "top_scope_count": 1}


def test_summary_after_close_uses_cached_projection():
    backend = _backend_without_worker()
    backend._summary_cache = {"test_count": 2, "top_scope_count": 1}
    backend._closed = True
    assert backend.summary() == {"test_count": 2, "top_scope_count": 1}


@pytest.mark.parametrize("operation, call_args", [
    ("scope_functional_from_urg", ()),
    ("scope_assert_from_urg", ()),
    ("gap_items", ("line",)),
    ("load_exclusions", ([],)),
    ("set_exclusion", ("ref", True)),
    ("save_exclusions", ("exclusions.el",)),
    ("unload_exclusions", ()),
    ("resolve_gap_payload", ({},)),
    ("resolve_container_records", ([],)),
    ("expand_xml_instances", ("root", False)),
])
def test_unsupported_operations_raise_structured_error(operation, call_args):
    backend = _backend_without_worker()
    method = getattr(backend, operation)
    with pytest.raises(XcovError) as excinfo:
        method(*call_args)
    assert excinfo.value.code == "NATIVE_BACKEND_UNSUPPORTED"
    assert excinfo.value.detail["operation"] == operation


def test_scope_metrics_aggregates_score_rows_per_scope():
    backend = _backend_without_worker()
    backend._items_cache = {}
    rows = [
        {"metric": "line", "type": "npiCovStmtBin", "scope": "top.u_dut",
         "covered": 1, "coverable": 2, "missing": 1, "status": ["not_covered"]},
        {"metric": "line", "type": "npiCovStmtBin", "scope": "top.u_dut",
         "covered": 1, "coverable": 1, "missing": 0, "status": ["covered"]},
        # context 行与 assert 计数行不参与聚合
        {"metric": "line", "type": "npiCovBlock", "scope": "top.u_dut",
         "covered": -1, "coverable": -1, "missing": 0, "status": ["covered"]},
        {"metric": "assert", "type": "npiCovAttemptBin", "scope": "top.u_dut",
         "covered": -1, "coverable": -1, "missing": 0, "count": 3,
         "status": ["attempted"]},
        {"metric": "assert", "type": "npiCovAssert", "scope": "top.u_dut.u_ctrl",
         "covered": 0, "coverable": 1, "missing": 1, "status": ["not_covered"]},
    ]
    backend._request = lambda action, args=None: [dict(row) for row in rows]
    result = backend.scope_metrics()
    assert result["top.u_dut"]["line"] == {
        "covered": 2, "coverable": 3, "missing": 1, "pct": 66.6667,
    }
    assert result["top.u_dut.u_ctrl"]["assert"] == {
        "covered": 0, "coverable": 1, "missing": 1, "pct": 0.0,
    }
    assert "functional" not in result["top.u_dut"]
    assert "attempt" not in json.dumps(result)


def test_items_strips_non_contract_fields_from_worker_rows():
    backend = _backend_without_worker()
    raw_row = {
        "metric": "condition",
        "type": "npiCovConditionBin",
        "name": "10",
        "full_name": "top.u_dut.u_ctrl.cond_9.10",
        "covered": 0,
        "coverable": 1,
        "missing": 1,
        "count": 0,
        "coverage_pct": 0.0,
        "status": ["not_covered"],
        "evidence": {"file": "rtl/ctrl.sv", "line": 91},
        "condition": "(enable && ready)",
        "condition_bin": "10",
        "condition_expression": "(enable && ready)",
        "condition_ast": {"opcode": 1},
        "condition_term_values": [{"index": 0, "name": "enable", "value": "1"}],
    }
    backend._request = lambda action, args=None: [dict(raw_row)]
    rows = backend.items(metrics=["condition"], test="merged")
    assert len(rows) == 1
    assert set(rows[0]) <= ALLOWED_FIELDS
    assert rows[0]["condition_bin"] == "10"
