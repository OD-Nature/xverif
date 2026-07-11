#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

XCOV_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(XCOV_ROOT))

from xcov.actions import Dispatcher  # noqa: E402


def request(dispatcher: Dispatcher, action: str, *, target: dict, args: dict | None = None) -> dict:
    response = dispatcher.dispatch({
        "api_version": "xcov.v1",
        "request_id": f"self-test-{action}",
        "action": action,
        "target": target,
        "args": args or {},
        "output": {"response_format": "json"},
    })
    if not response.get("ok"):
        raise RuntimeError(json.dumps(response, ensure_ascii=False))
    return response


def inject_npi_library_path() -> None:
    verdi_home = os.environ.get("XVERIF_XCOV_VERDI_HOME") or os.environ.get("VERDI_HOME")
    if not verdi_home:
        raise RuntimeError("VERDI_HOME or XVERIF_XCOV_VERDI_HOME is required")
    candidates = [
        Path(verdi_home) / "share/NPI/lib/LINUX64",
        Path(verdi_home) / "share/NPI/lib/linux64",
    ]
    npi_lib = next((path for path in candidates if path.is_dir()), None)
    if npi_lib is None:
        raise RuntimeError(f"Verdi NPI library directory not found under {verdi_home}")
    current = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{npi_lib}:{current}" if current else str(npi_lib)


def assert_close(actual: float | None, expected: float, label: str) -> None:
    if actual is None or abs(float(actual) - expected) > 0.0002:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="xcov real VDB self-test")
    parser.add_argument("vdb")
    parser.add_argument("--scope", default="xcov_basic_tb.u_dut")
    parser.add_argument("--expected-worker")
    ns = parser.parse_args()

    vdb = Path(ns.vdb).resolve()
    coverage_db = vdb / "snps/coverage/db"
    if not coverage_db.is_dir() or not any(path.is_file() for path in coverage_db.rglob("*")):
        raise RuntimeError(f"incomplete coverage database: {vdb}")

    inject_npi_library_path()
    dispatcher = Dispatcher()
    session_id = "xcov_self_test"
    opened = request(
        dispatcher,
        "session.open",
        target={"vdb": str(vdb)},
        args={"name": session_id},
    )
    target = {"session_id": session_id}
    try:
        worker = opened["summary"].get("worker")
        if ns.expected_worker and worker != ns.expected_worker:
            raise AssertionError(f"expected worker {ns.expected_worker}, got {worker}")
        tests = request(dispatcher, "tests.list", target=target)
        if tests["summary"].get("matched_count") != 2:
            raise AssertionError(f"expected 2 coverage tests, got {tests['summary']}")
        scope = request(
            dispatcher,
            "scope.summary",
            target=target,
            args={"scope": ns.scope},
        )
        items = scope.get("data", {}).get("items") or []
        if len(items) != 1:
            raise AssertionError(f"expected one scope row, got {items}")
        item = items[0]
        metric_pcts = [
            float(item[f"{metric}_pct"])
            for metric in ("line", "toggle", "branch", "condition", "fsm", "assert", "functional")
            if item.get(f"{metric}_pct") is not None
        ]
        if len(metric_pcts) < 3:
            raise AssertionError(f"expected line/toggle/branch metrics, got {item}")
        score = round(sum(metric_pcts) / len(metric_pcts), 4)
        assert_close(item.get("coverage_pct"), score, "Verdi-style score")
        raw = round(float(item["covered"]) / float(item["coverable"]) * 100.0, 4)
        assert_close(item.get("raw_coverage_pct"), raw, "raw weighted coverage")
        if item.get("score_basis") != "average_metric_pct":
            raise AssertionError(f"unexpected score basis: {item.get('score_basis')}")
        if item.get("score_item_count") != len(metric_pcts):
            raise AssertionError(f"unexpected score item count: {item}")
        print(json.dumps({
            "ok": True,
            "worker": worker,
            "test_count": tests["summary"].get("matched_count"),
            "scope": ns.scope,
            "coverage_pct": item.get("coverage_pct"),
            "raw_coverage_pct": item.get("raw_coverage_pct"),
            "metrics": {metric: item.get(f"{metric}_pct") for metric in ("line", "toggle", "branch")},
        }, ensure_ascii=False, indent=2))
    finally:
        request(dispatcher, "session.close", target=target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
