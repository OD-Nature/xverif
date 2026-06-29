"""Coverage database helpers for Synopsys Python NPI scripts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence


Json = Dict[str, Any]

METRIC_METHODS = {
    "line": "line_metric_handle",
    "toggle": "toggle_metric_handle",
    "branch": "branch_metric_handle",
    "condition": "condition_metric_handle",
    "fsm": "fsm_metric_handle",
    "assert": "assert_metric_handle",
}


def _cov():
    from pynpi import cov  # type: ignore

    return cov


def open_covdb(vdb: str) -> Any:
    db = _cov().open(vdb)
    if not db:
        raise RuntimeError(f"cov.open failed: {vdb}")
    return db


def close_covdb(db: Any) -> None:
    db.close()


def test_names(db: Any) -> List[str]:
    return sorted(str(_safe_call(test, "name") or "") for test in _safe_list(db, "test_handles"))


def merged_test_handle(db: Any) -> Any:
    cov = _cov()
    merged = None
    for test in _safe_list(db, "test_handles"):
        merged = test if merged is None else cov.merge_test(merged, test)
    if merged is None:
        raise RuntimeError("coverage database has no tests")
    return merged


def coverage_items(
    db: Any,
    test: Any,
    metrics: Sequence[str] | None = None,
    scope: str | None = None,
    holes_only: bool = False,
) -> List[Json]:
    wanted = list(metrics or [*METRIC_METHODS.keys(), "functional"])
    rows: List[Json] = []
    code_metrics = [metric for metric in wanted if metric != "functional"]
    if code_metrics:
        for inst in _safe_list(db, "instance_handles"):
            try:
                _walk_instance(inst, test, code_metrics, scope, holes_only, rows)
            finally:
                _release(inst)
    if "functional" in wanted:
        _walk_functional(test, scope, holes_only, rows)
    return rows


def coverage_summary(rows: Iterable[Json]) -> Json:
    totals: Dict[str, Json] = {}
    for row in rows:
        metric = str(row.get("metric") or "unknown")
        bucket = totals.setdefault(metric, {"metric": metric, "covered": 0, "coverable": 0, "missing": 0})
        bucket["covered"] += int(row.get("covered") or 0)
        bucket["coverable"] += int(row.get("coverable") or 0)
        bucket["missing"] += int(row.get("missing") or 0)
    for bucket in totals.values():
        bucket["coverage_pct"] = coverage_pct(bucket["covered"], bucket["coverable"])
    return {"metrics": [totals[name] for name in sorted(totals)]}


def coverage_pct(covered: Any, coverable: Any) -> float | None:
    try:
        denom = int(coverable or 0)
        if denom <= 0:
            return None
        return round(100.0 * int(covered or 0) / denom, 4)
    except Exception:
        return None


def _walk_instance(
    inst: Any,
    test: Any,
    metrics: Sequence[str],
    scope: str | None,
    holes_only: bool,
    rows: List[Json],
) -> None:
    inst_full = _safe_call(inst, "full_name") or _safe_call(inst, "name")
    in_scope = scope is None or str(inst_full or "").startswith(scope)
    if in_scope:
        for metric in metrics:
            method = METRIC_METHODS.get(metric)
            if not method:
                continue
            metric_hdl = _safe_call(inst, method)
            if metric_hdl:
                try:
                    _walk_children(metric_hdl, metric, str(inst_full or ""), test, holes_only, rows, {}, None)
                finally:
                    _release(metric_hdl)
    for child in _safe_list(inst, "instance_handles"):
        try:
            _walk_instance(child, test, metrics, scope, holes_only, rows)
        finally:
            _release(child)


def _walk_children(
    hdl: Any,
    metric: str,
    scope: str,
    test: Any,
    holes_only: bool,
    rows: List[Json],
    path: Json,
    parent_source: Json | None,
) -> None:
    typ = _safe_call(hdl, "type")
    name = _safe_call(hdl, "name")
    full_name = _safe_call(hdl, "full_name") or name
    next_path = _path_update(metric, typ, name, full_name, path)
    evidence = {"file": _safe_call(hdl, "file_name"), "line": _safe_call(hdl, "line_no", test)}
    own_source = _source(typ, name, full_name, evidence)
    row_source = own_source or parent_source
    covered = _safe_call(hdl, "covered", test)
    coverable = _safe_call(hdl, "coverable", test)
    if coverable is not None:
        row = _row(metric, typ, scope, name, full_name, covered, coverable, test, hdl,
                   row_source["evidence"] if row_source else evidence, next_path)
        if row_source and row_source is not own_source:
            row["evidence_source"] = {
                "inherited": True,
                "type": row_source.get("type"),
                "name": row_source.get("name"),
                "full_name": row_source.get("full_name"),
            }
        if not holes_only or int(row.get("missing") or 0) > 0:
            rows.append(row)
    for child in _safe_list(hdl, "child_handles"):
        try:
            _walk_children(child, metric, scope, test, holes_only, rows, next_path, own_source or parent_source)
        finally:
            _release(child)


def _walk_functional(test: Any, scope: str | None, holes_only: bool, rows: List[Json]) -> None:
    metric_hdl = _safe_call(test, "testbench_metric_handle")
    if not metric_hdl:
        return
    try:
        for child in _safe_list(metric_hdl, "child_handles"):
            try:
                _walk_functional_child(child, test, scope, holes_only, rows, {}, None)
            finally:
                _release(child)
    finally:
        _release(metric_hdl)


def _walk_functional_child(
    hdl: Any,
    test: Any,
    scope_filter: str | None,
    holes_only: bool,
    rows: List[Json],
    path: Json,
    parent_source: Json | None,
) -> None:
    typ = _safe_call(hdl, "type")
    name = _safe_call(hdl, "name")
    next_path = dict(path)
    if typ == "npiCovCovergroup":
        next_path = {"covergroup": name}
    elif typ == "npiCovCoverpoint":
        next_path["coverpoint"] = name
    elif typ == "npiCovCross":
        next_path["cross"] = name
    elif typ == "npiCovCoverBin":
        next_path["bin"] = name
    full_name = ".".join(str(v) for v in next_path.values() if v not in (None, "")) or str(name or "")
    scope = _functional_scope(next_path.get("covergroup"))
    evidence = {"file": _safe_call(hdl, "file_name"), "line": _safe_call(hdl, "line_no", test)}
    own_source = _source(typ, name, full_name, evidence)
    row_source = own_source or parent_source
    covered = _safe_call(hdl, "covered", test)
    coverable = _safe_call(hdl, "coverable", test)
    if coverable is not None and (scope_filter is None or str(scope or full_name).startswith(scope_filter)):
        row = _row("functional", typ, scope, name, full_name, covered, coverable, test, hdl,
                   row_source["evidence"] if row_source else evidence, next_path)
        if row_source and row_source is not own_source:
            row["evidence_source"] = {
                "inherited": True,
                "type": row_source.get("type"),
                "name": row_source.get("name"),
                "full_name": row_source.get("full_name"),
            }
        if not holes_only or int(row.get("missing") or 0) > 0:
            rows.append(row)
    for child in _safe_list(hdl, "child_handles"):
        try:
            _walk_functional_child(child, test, scope_filter, holes_only, rows, next_path,
                                   own_source or parent_source)
        finally:
            _release(child)


def _row(
    metric: str,
    typ: Any,
    scope: Any,
    name: Any,
    full_name: Any,
    covered: Any,
    coverable: Any,
    test: Any,
    hdl: Any,
    evidence: Json,
    path: Json,
) -> Json:
    missing = _missing(covered, coverable)
    return {
        "metric": metric,
        "type": typ,
        "scope": scope,
        "name": name,
        "full_name": full_name,
        "covered": covered,
        "coverable": coverable,
        "missing": missing,
        "coverage_pct": coverage_pct(covered, coverable),
        "count": _safe_call(hdl, "count", test),
        "status": _status_flags(hdl, test, covered, coverable),
        "evidence": evidence,
        **{k: v for k, v in path.items() if v not in (None, "")},
    }


def _path_update(metric: str, typ: Any, name: Any, full_name: Any, path: Json) -> Json:
    out = dict(path)
    label = full_name or name
    if metric == "toggle":
        if typ == "npiCovSignal":
            out["toggle_signal"] = label
        elif typ == "npiCovSignalBit":
            out["toggle_bit"] = label
        elif typ == "npiCovToggleBin":
            out["toggle_transition"] = name
    elif metric == "branch":
        if typ == "npiCovBranch":
            out["branch"] = label
        elif typ == "npiCovBranchBin":
            out["branch_bin"] = name
    elif metric == "condition":
        if typ == "npiCovCondition":
            out["condition"] = label
        elif typ == "npiCovConditionBin":
            out["condition_bin"] = name
    return out


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
    return list(_safe_call(obj, name) or [])


def _release(hdl: Any) -> None:
    try:
        _cov().release_handle(hdl)
    except Exception:
        pass


def _missing(covered: Any, coverable: Any) -> int | None:
    try:
        return max(int(coverable or 0) - int(covered or 0), 0)
    except Exception:
        return None


def _status_flags(hdl: Any, test: Any, covered: Any, coverable: Any) -> List[str]:
    flags: List[str] = []
    for method, flag in [
        ("has_status_excluded", "excluded"),
        ("has_status_unreachable", "unreachable"),
        ("has_status_illegal", "illegal"),
        ("has_status_proven", "proven"),
        ("has_status_attempted", "attempted"),
        ("has_status_partially_attempted", "partially_attempted"),
    ]:
        if _safe_call(hdl, method, test):
            flags.append(flag)
    try:
        base = "covered" if int(covered or 0) >= int(coverable or 0) and int(coverable or 0) > 0 else "not_covered"
    except Exception:
        base = "not_covered"
    return [base, *flags]


def _source(typ: Any, name: Any, full_name: Any, evidence: Json) -> Json | None:
    if not evidence.get("file"):
        return None
    try:
        if int(evidence.get("line") or 0) <= 0:
            return None
    except Exception:
        return None
    return {"type": typ, "name": name, "full_name": full_name, "evidence": dict(evidence)}


def _functional_scope(covergroup: Any) -> str | None:
    if not covergroup:
        return None
    name = str(covergroup)
    if "::" not in name:
        return name.rsplit(".", 1)[0] if "." in name else None
    prefix = name.split("::", 1)[0]
    return prefix if "." in prefix else None
