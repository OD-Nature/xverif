from __future__ import annotations

from collections import defaultdict
import os
import time
from typing import Any, Dict, Iterable, List, Optional

from .backend import METRICS
from .errors import XcovError, error_response
from .logging import (log_action_event, request_summary_for_log,
                      response_summary_for_log, update_session_manifest)
from .protocol import ok_response
from .provenance import validate_run_manifest
from .query import (apply_output, coverage_pct, filter_items, filters_summary,
                    query_args, resolve_artifact_path, sort_items)
from .schemas import schema_for_action
from .session import SessionManager

Json = Dict[str, Any]

P0_ACTIONS = [
    "session.open", "session.status", "session.close",
    "tests.list", "metrics.list",
    "scope.summary", "scope.children", "scope.search",
    "code_coverage.summary", "code_coverage.holes",
    "function_coverage.summary", "function_coverage.holes",
    "source.map", "source.annotate", "assert.summary",
    "export.code_coverage", "export.function_coverage", "export.assert",
]


def _safe_error_response(req: Json, exc: XcovError) -> Json:
    detail = dict(exc.detail)
    if "action" in detail:
        detail["requested_action"] = detail.pop("action")
    response = error_response(req.get("action", ""), req.get("request_id", "req-unknown"),
                              exc.code, exc.message, **detail)
    if exc.code == "RESOURCE_PROVENANCE_MISMATCH":
        response["summary"]["status"] = "manifest_mismatch"
        response["data"] = {"manifest": detail.get("manifest", {})}
    return response


class Dispatcher:
    def __init__(self, sessions: SessionManager | None = None) -> None:
        self.sessions = sessions or SessionManager()

    def dispatch(self, req: Json) -> Json:
        start = time.monotonic()
        action = req.get("action", "")
        sid = _log_session_id(req)
        log_action_event("public", sid, action, "begin", True, 0,
                         {"request": request_summary_for_log(req)})
        try:
            action = req["action"]
            if action == "actions":
                rsp = self._actions(req)
            elif action == "schema":
                rsp = self._schema(req)
            elif action == "session.open":
                rsp = self._session_open(req)
            elif action == "session.status":
                rsp = self._session_status(req)
            elif action == "session.close":
                rsp = self._session_close(req)
            else:
                sess = self._session(req)
                if action == "tests.list":
                    rsp = self._tests_list(req, sess)
                elif action == "metrics.list":
                    rsp = self._metrics_list(req, sess)
                elif action in ("scope.summary", "scope.children", "scope.search"):
                    rsp = self._scope(req, sess)
                elif action in ("code_coverage.summary", "code_coverage.holes"):
                    rsp = self._code_coverage(req, sess)
                elif action in ("function_coverage.summary", "function_coverage.holes"):
                    rsp = self._functional(req, sess)
                elif action == "source.map":
                    rsp = self._source_map(req, sess)
                elif action == "source.annotate":
                    rsp = self._source_annotate(req, sess)
                elif action == "assert.summary":
                    rsp = self._assert_report(req, sess)
                elif action.startswith("export."):
                    rsp = self._export(req, sess)
                else:
                    raise XcovError("ACTION_NOT_FOUND", "unknown action", action=action)
            elapsed = int((time.monotonic() - start) * 1000)
            log_action_event("public", _response_log_session_id(req, rsp), action, "end",
                             bool(rsp.get("ok")), elapsed,
                             {"response": response_summary_for_log(rsp)})
            return rsp
        except XcovError as exc:
            rsp = _safe_error_response(req, exc)
            elapsed = int((time.monotonic() - start) * 1000)
            log_action_event("public", sid, action, "end", False, elapsed,
                             {"response": response_summary_for_log(rsp)})
            return rsp
        except Exception as exc:
            rsp = error_response(req.get("action", ""), req.get("request_id", "req-unknown"),
                                 "INTERNAL_ERROR", str(exc))
            elapsed = int((time.monotonic() - start) * 1000)
            log_action_event("public", sid, action, "end", False, elapsed,
                             {"response": response_summary_for_log(rsp)})
            return rsp

    def _session(self, req: Json):
        sid = req.get("target", {}).get("session_id")
        if not sid:
            raise XcovError("SESSION_NOT_FOUND", "target.session_id is required")
        return self.sessions.get(str(sid))

    def _actions(self, req: Json) -> Json:
        rows = [{"name": a, "status": "p0", "api_version": "xcov.v1"} for a in P0_ACTIONS]
        return ok_response(req, {"matched_count": len(rows), "returned": len(rows),
                                 "truncated": False, "output_path": None},
                           {"items": rows})

    def _schema(self, req: Json) -> Json:
        action = merged_action_args(req).get("action")
        if action not in P0_ACTIONS and action not in ("actions", "schema"):
            raise XcovError("ACTION_NOT_FOUND", "schema action not found", requested_action=action)
        kind = str(merged_action_args(req).get("kind", "request"))
        try:
            schema = schema_for_action(str(action), kind)
        except KeyError:
            raise XcovError("ACTION_NOT_FOUND", "schema action not found",
                            requested_action=action, kind=kind)
        return ok_response(req, {"matched_count": 1, "returned": 1,
                                 "truncated": False, "output_path": None},
                           {"schema": schema})

    def _session_open(self, req: Json) -> Json:
        target = req.get("target", {})
        args = merged_action_args(req)
        vdb = target.get("vdb")
        if not vdb:
            raise XcovError("VDB_OPEN_FAILED", "target.vdb is required")
        manifest_details = validate_run_manifest(target)
        sess = self.sessions.open(
            str(vdb), name=args.get("name"), fake=bool(args.get("fake")),
            reuse=bool(args.get("reuse", True)), reopen=bool(args.get("reopen", False)))
        summary = sess.public_json()
        summary.update({"matched_count": 1, "returned": 1,
                        "truncated": False, "output_path": None,
                        "resource_snapshot": {
                            "vdb": sess.vdb,
                            "run_manifest": manifest_details,
                        }})
        session_json = sess.public_json()
        update_session_manifest(sess.session_id, session_json)
        return ok_response(req, summary, {"session": session_json})

    def _session_status(self, req: Json) -> Json:
        sess = self._session(req)
        summary = sess.public_json()
        summary.update({"cached_indexes": "lazy", "matched_count": 1, "returned": 1,
                        "truncated": False, "output_path": None})
        return ok_response(req, summary, {"session": sess.public_json()})

    def _session_close(self, req: Json) -> Json:
        sid = req.get("target", {}).get("session_id")
        sess = self.sessions.close(str(sid))
        summary = sess.public_json()
        summary.update({"matched_count": 1, "returned": 1,
                        "truncated": False, "output_path": None})
        session_json = sess.public_json()
        update_session_manifest(sess.session_id, session_json)
        return ok_response(req, summary, {"session": session_json})

    def _tests_list(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        args.setdefault("query", {}).setdefault("match_field", "name")
        query = query_args(args)
        rows = filter_items(sess.backend.tests(), query)
        summary, inline, warnings = apply_output("tests.list", args, rows)
        summary["session_id"] = sess.session_id
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _metrics_list(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        items = sess.backend.items(scope=args.get("scope"), test=str(args.get("test", "merged")))
        rows = _summary_from_items(_coverage_score_rows(items), "metric")
        summary, inline, warnings = apply_output("metrics.list", args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged")})
        return ok_response(req, summary, {"items": inline}, warnings)

    def _scope(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        scopes = _indexed_scopes(sess.backend.scopes())
        metrics = args.get("metrics") or METRICS
        items = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                  test=str(args.get("test", "merged")))
        items = _coverage_score_rows(items)
        coverage = _scope_coverage(items, metrics)
        if action == "scope.summary":
            rows = _scope_summary_rows(scopes, coverage, args)
            rows = _project_scope_summary_rows(rows)
        elif action == "scope.children":
            rows = _scope_children_rows(scopes, coverage, args)
            rows = _project_scope_brief_rows(rows)
        else:
            rows = _scope_search_rows(scopes, coverage, args)
            rows = _project_scope_brief_rows(rows)
        rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged")})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _code_coverage(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        metrics = args.get("metrics") or _code_metrics()
        already_filtered = False
        if action == "code_coverage.holes":
            scopes = _indexed_scopes(sess.backend.scopes())
            items = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                      test=str(args.get("test", "merged")))
            rows = _code_coverage_hole_scope_rows(scopes, _coverage_score_rows(items), metrics, args)
            rows = _project_code_coverage_hole_rows(rows)
        else:
            rows = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                      test=str(args.get("test", "merged")))
            rows = _coverage_score_rows(rows)
            rows = _summary_from_items(rows, str(args.get("group_by", "metric")))
            rows = filter_items(rows, query)
            rows = _project_code_coverage_summary_rows(rows)
            already_filtered = True
        if not already_filtered:
            rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged"), "metrics": metrics})
        if action == "code_coverage.holes":
            summary["note"] = ("Detailed uncovered code coverage items are available via "
                               "export.code_coverage. For complex processing, use x-npi "
                               "and learn the pynpi coverage APIs.")
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _functional(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        rows = sess.backend.items(metrics=["functional"], scope=args.get("scope"),
                                  test=str(args.get("test", "merged")),
                                  functional_only=True)
        rows = _filter_functional_levels(rows, args.get("levels"))
        if action == "function_coverage.holes":
            rows = [r for r in rows if int(r.get("missing") or 0) > 0]
            rows = filter_items(rows, query)
            rows = _project_function_coverage_hole_rows(rows)
        else:
            group_by = str(args.get("group_by", "covergroup"))
            rows = _functional_summary_rows(rows, group_by)
            rows = filter_items(rows, query)
            rows = _project_function_coverage_summary_rows(rows, group_by)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows)
        summary.update({"session_id": sess.session_id, "test": args.get("test", "merged")})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _source_map(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        query = query_args(args)
        file_name = args.get("file")
        line = args.get("line")
        window = int(args.get("window", 0))
        if file_name is None or line is None:
            raise XcovError("SCHEMA_INVALID", "source.map requires file and line")
        metrics = args.get("metrics")
        lo, hi = int(line) - window, int(line) + window
        rows = []
        items = sess.backend.items(metrics=metrics, test=str(args.get("test", "merged")))
        for item in _coverage_score_rows(items):
            ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            if str(ev.get("file", "")).endswith(str(file_name)) and ev.get("line") is not None:
                try:
                    if lo <= int(ev["line"]) <= hi:
                        rows.append(item)
                except Exception:
                    pass
        rows = filter_items(rows, query)
        summary, inline, warnings = apply_output("source.map", args, rows)
        summary.update({"session_id": sess.session_id, "file": file_name, "line": line,
                        "window": window})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _source_annotate(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        query = query_args(args)
        file_name = args.get("file")
        line = args.get("line")
        window = int(args.get("window", 3))
        include_source_text = bool(args.get("include_source_text", True))
        include_covered = bool(args.get("include_covered", True))
        if file_name is None or line is None:
            raise XcovError("SCHEMA_INVALID", "source.annotate requires file and line")
        metrics = args.get("metrics")
        lo, hi = int(line) - window, int(line) + window
        items = sess.backend.items(metrics=metrics, test=str(args.get("test", "merged")))
        rows = []
        by_line: Dict[int, List[Json]] = defaultdict(list)
        source_path = str(file_name)
        for item in _coverage_score_rows(items):
            ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            if not _file_matches(ev.get("file"), file_name) or ev.get("line") is None:
                continue
            try:
                item_line = int(ev["line"])
            except Exception:
                continue
            if lo <= item_line <= hi:
                if ev.get("file"):
                    source_path = str(ev["file"])
                if include_covered or int(item.get("missing") or 0) > 0:
                    by_line[item_line].append(item)
        source_lines = _read_source_window(source_path, lo, hi) if include_source_text else {}
        for line_no in range(lo, hi + 1):
            line_items = filter_items(by_line.get(line_no, []), query)
            if line_items or line_no in source_lines:
                rows.append({
                    "file": str(file_name),
                    "line": line_no,
                    "source": source_lines.get(line_no),
                    "annotations": [_source_annotation(item) for item in line_items],
                    "annotation_count": len(line_items),
                })
        summary, inline, warnings = apply_output("source.annotate", args, rows)
        if include_source_text and not source_lines:
            summary["note"] = ("source text is unavailable from file path; coverage annotations "
                               "still use NPI evidence")
        summary.update({"session_id": sess.session_id, "file": file_name, "line": line,
                        "window": window, "include_source_text": include_source_text})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _assert_report(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        query = query_args(args)
        rows, _sections = _assert_report_rows(sess.backend.items(metrics=["assert"], scope=args.get("scope"),
                                                                test=str(args.get("test", "merged"))),
                                              include_source=False)
        rows = _project_assert_summary_rows(rows)
        rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output("assert.summary", args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged")})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _export(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        threshold = float(args.get("threshold_pct", 100.0))
        output_path = _export_output_path(args)
        if action == "export.code_coverage":
            rows = _coverage_score_rows(sess.backend.items(
                metrics=args.get("metrics") or _code_metrics(),
                scope=args.get("scope"),
                test=str(args.get("test", "merged"))))
            markdown, exported_count = _code_coverage_markdown(rows, threshold)
        elif action == "export.function_coverage":
            rows = sess.backend.items(metrics=["functional"], scope=args.get("scope"),
                                      test=str(args.get("test", "merged")),
                                      functional_only=True)
            markdown, exported_count = _function_coverage_markdown(
                rows, threshold, covergroup_filter=args.get("covergroup"))
        elif action == "export.assert":
            rows, sections = _assert_report_rows(sess.backend.items(
                metrics=["assert"], scope=args.get("scope"),
                test=str(args.get("test", "merged"))),
                include_source=True)
            markdown, exported_count = _assert_markdown(rows, sections, threshold)
        else:
            raise XcovError("ACTION_NOT_FOUND", "unknown export action", action=action)
        resolved = _write_markdown_artifact(output_path, markdown,
                                            bool((args.get("output") or {}).get("allow_absolute_path")))
        summary = {
            "session_id": sess.session_id,
            "scope": args.get("scope"),
            "test": args.get("test", "merged"),
            "threshold_pct": threshold,
            "matched_count": exported_count,
            "returned": 0,
            "truncated": False,
            "output_mode": "file",
            "output_path": resolved,
            "artifact_format": "md",
            "note": ("Markdown export only. For complex processing, use x-npi and "
                     "learn the pynpi coverage APIs."),
        }
        return ok_response(req, summary, {"items": []})


def merged_action_args(req: Json) -> Json:
    args = dict(req.get("args") or {})
    if "limits" in req and "limits" not in args:
        args["limits"] = req["limits"]
    if "output" in req and "output" not in args:
        args["output"] = req["output"]
    return args


def _log_session_id(req: Json) -> str:
    target = req.get("target") if isinstance(req.get("target"), dict) else {}
    args = req.get("args") if isinstance(req.get("args"), dict) else {}
    if target.get("session_id"):
        return str(target["session_id"])
    if req.get("action") == "session.open" and args.get("name"):
        return str(args["name"])
    return "adhoc"


def _response_log_session_id(req: Json, rsp: Json) -> str:
    data = rsp.get("data") if isinstance(rsp.get("data"), dict) else {}
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    if session.get("session_id"):
        return str(session["session_id"])
    return _log_session_id(req)


def _scope_name(full_name: str) -> str:
    return full_name.rsplit(".", 1)[-1]


def _scope_parent(full_name: str) -> Optional[str]:
    if "." not in full_name:
        return None
    return full_name.rsplit(".", 1)[0]


def _scope_depth(full_name: str) -> int:
    return full_name.count(".")


def _scope_row(full_name: str, base: Optional[Json] = None) -> Json:
    row = dict(base or {})
    row.setdefault("full_name", full_name)
    row.setdefault("name", _scope_name(full_name))
    row.setdefault("parent", _scope_parent(full_name))
    row.setdefault("depth", _scope_depth(full_name))
    row.setdefault("type", "npiCovInstance")
    return row


def _scope_ancestors(scope: str) -> Iterable[str]:
    parts = str(scope).split(".")
    for idx in range(1, len(parts) + 1):
        yield ".".join(parts[:idx])


def _indexed_scopes(scopes: List[Json]) -> Dict[str, Json]:
    by_name: Dict[str, Json] = {}
    for row in scopes:
        full = str(row.get("full_name") or row.get("name") or "")
        if not full:
            continue
        by_name[full] = _scope_row(full, row)
        for ancestor in _scope_ancestors(full):
            by_name.setdefault(ancestor, _scope_row(ancestor))
    return dict(sorted(by_name.items(), key=lambda kv: (int(kv[1].get("depth") or 0), kv[0])))


def _is_descendant(scope: str, root: str) -> bool:
    return scope == root or scope.startswith(root + ".")


def _is_direct_child(scope: str, parent: Optional[str]) -> bool:
    return _scope_parent(scope) == parent


def _scope_search_rows(scopes: Dict[str, Json], coverage: Dict[str, Json], args: Json) -> List[Json]:
    root = args.get("scope")
    rows = list(scopes.values())
    if root:
        rows = [r for r in rows if _is_descendant(str(r.get("full_name", "")), str(root))]
    return [_merge_scope_coverage(r, coverage.get(str(r.get("full_name") or ""))) for r in rows]


def _scope_summary_rows(scopes: Dict[str, Json], coverage: Dict[str, Json], args: Json) -> List[Json]:
    root = args.get("scope")
    if root:
        full = str(root)
        base = scopes.get(full, _scope_row(full))
        return [_merge_scope_coverage(base, coverage.get(full))]
    top_names = [name for name, row in scopes.items() if int(row.get("depth") or 0) == 0]
    return [_merge_scope_coverage(scopes[name], coverage.get(name)) for name in top_names]


def _scope_children_rows(scopes: Dict[str, Json], coverage: Dict[str, Json], args: Json) -> List[Json]:
    root = args.get("scope")
    parent = str(root) if root else None
    recursive = bool(args.get("recursive", False))
    out = []
    for full, row in scopes.items():
        if root:
            selected = _is_descendant(full, parent) and full != parent if recursive else _is_direct_child(full, parent)
        else:
            selected = int(row.get("depth") or 0) == 0
        if selected:
            out.append(_merge_scope_coverage(row, coverage.get(full)))
    return out


def _scope_coverage(items: List[Json], metrics: List[str]) -> Dict[str, Json]:
    grouped: Dict[str, Dict[str, List[Json]]] = defaultdict(lambda: defaultdict(list))
    for item in items:
        scope = str(item.get("scope") or "")
        if not scope:
            continue
        metric = str(item.get("metric") or "unknown")
        for ancestor in _scope_ancestors(scope):
            grouped[ancestor][metric].append(item)
    out: Dict[str, Json] = {}
    for scope, by_metric in grouped.items():
        metric_rows = []
        total_covered = 0
        total_coverable = 0
        for metric in metrics:
            subset = by_metric.get(metric, [])
            if metric == "functional":
                subset = _functional_summary_level_rows(subset, "covergroup")
            if not subset:
                continue
            coverable = sum(int(i.get("coverable") or 0) for i in subset)
            covered = sum(int(i.get("covered") or 0) for i in subset)
            total_covered += covered
            total_coverable += coverable
            metric_rows.append({"metric": metric, "covered": covered, "coverable": coverable,
                                "missing": coverable - covered,
                                "coverage_pct": coverage_pct(covered, coverable)})
        out[scope] = {"covered": total_covered, "coverable": total_coverable,
                      "missing": total_coverable - total_covered,
                      "coverage_pct": coverage_pct(total_covered, total_coverable),
                      "metrics": metric_rows}
    return out


CODE_SCORE_TYPES = {
    "line": {"npiCovStmtBin"},
    "toggle": {"npiCovToggleBin"},
    "condition": {"npiCovConditionBin"},
    "branch": {"npiCovBranchBin"},
    "fsm": {"npiCovTransBin"},
    "assert": {"npiCovAssert", "npiCovCoverProperty", "npiCovCoverSequence"},
}


def _coverage_score_rows(items: List[Json]) -> List[Json]:
    """Rows that contribute to URG dashboard-style code coverage totals."""
    rows: List[Json] = []
    for item in items:
        metric = str(item.get("metric") or "")
        if metric == "functional":
            rows.append(item)
            continue
        wanted = CODE_SCORE_TYPES.get(metric)
        if wanted is None:
            rows.append(item)
            continue
        if str(item.get("type") or "") not in wanted:
            continue
        if not _has_nonnegative_ratio(item):
            continue
        rows.append(item)
    return rows


def _has_nonnegative_ratio(item: Json) -> bool:
    try:
        return int(item.get("covered")) >= 0 and int(item.get("coverable")) >= 0
    except Exception:
        return False


def _merge_scope_coverage(scope: Json, cov: Optional[Json]) -> Json:
    out = dict(scope)
    cov = cov or {"covered": 0, "coverable": 0, "missing": 0,
                  "coverage_pct": None, "metrics": []}
    for key in ("covered", "coverable", "missing", "coverage_pct"):
        out[key] = cov.get(key)
    ev = out.pop("evidence", None)
    if isinstance(ev, dict):
        out["file"] = ev.get("file")
        out["line"] = ev.get("line")
    metrics = cov.get("metrics") if isinstance(cov.get("metrics"), list) else []
    for metric in METRICS:
        row = next((m for m in metrics if m.get("metric") == metric), None)
        out[f"{metric}_pct"] = row.get("coverage_pct") if row else None
    return out


def _project_columns(row: Json, columns: List[str]) -> Json:
    return {key: row.get(key) for key in columns}


def _project_scope_brief_rows(rows: List[Json]) -> List[Json]:
    return [_project_columns(row, ["name", "full_name", "coverage_pct"]) for row in rows]


def _project_scope_summary_rows(rows: List[Json]) -> List[Json]:
    columns = [
        "name", "full_name", "covered", "coverable", "missing", "coverage_pct",
        "line_pct", "toggle_pct", "branch_pct", "condition_pct",
        "fsm_pct", "assert_pct", "functional_pct", "file", "line",
    ]
    return [_project_columns(row, columns) for row in rows]


def _project_code_coverage_summary_rows(rows: List[Json]) -> List[Json]:
    forbidden = {"name", "full_name", "functional_pct"}
    return [{key: value for key, value in row.items() if key not in forbidden}
            for row in rows]


def _project_code_coverage_hole_rows(rows: List[Json]) -> List[Json]:
    columns = [
        "name", "full_name", "coverage_pct",
        "line_pct", "toggle_pct", "branch_pct", "condition_pct",
        "fsm_pct", "assert_pct",
    ]
    return [_project_columns(row, columns) for row in rows]


def _project_function_coverage_summary_rows(rows: List[Json], group_by: str) -> List[Json]:
    columns = [
        group_by, "covered", "coverable", "missing",
        "coverage_pct",
    ]
    return [_project_columns(row, columns) for row in rows]


def _project_function_coverage_hole_rows(rows: List[Json]) -> List[Json]:
    out: List[Json] = []
    for row in rows:
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        projected = _project_columns(row, [
            "covergroup", "coverpoint", "cross", "bin",
            "covered", "coverable", "count", "coverage_pct", "status",
        ])
        projected["file"] = ev.get("file")
        projected["line"] = ev.get("line")
        out.append(projected)
    return out


def _project_assert_summary_rows(rows: List[Json]) -> List[Json]:
    columns = [
        "name", "full_name", "covered", "coverable", "missing",
        "coverage_pct", "status", "attempts", "real_successes",
        "without_attempts",
    ]
    return [_project_columns(row, columns) for row in rows]


def _code_metrics() -> List[str]:
    return [m for m in METRICS if m != "functional"]


def _code_coverage_hole_scope_rows(scopes: Dict[str, Json], items: List[Json],
                                   metrics: List[str], args: Json) -> List[Json]:
    coverage = _scope_coverage(items, metrics)
    current = _scope_summary_rows(scopes, coverage, args)
    children = _scope_children_rows(scopes, coverage, args)
    seen = set()
    rows = []
    for row in current + children:
        full = row.get("full_name")
        if full in seen:
            continue
        seen.add(full)
        rows.append(row)
    return [row for row in rows if any(_pct_is_below_100(row.get(f"{metric}_pct")) for metric in metrics)]


def _pct_is_below_100(value: Any) -> bool:
    try:
        return float(value) < 100.0
    except Exception:
        return False


def _summary_from_items(items: List[Json], group_by: str) -> List[Json]:
    groups: Dict[str, List[Json]] = defaultdict(list)
    for item in items:
        if group_by == "source_file":
            ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            key = str(ev.get("file") or "<unknown>")
        else:
            key = str(item.get(group_by) or item.get("metric") or "<unknown>")
        groups[key].append(item)
    rows: List[Json] = []
    for key, subset in groups.items():
        coverable = sum(int(i.get("coverable") or 0) for i in subset)
        covered = sum(int(i.get("covered") or 0) for i in subset)
        rows.append({group_by: key, "covered": covered, "coverable": coverable,
                     "missing": coverable - covered,
                     "coverage_pct": coverage_pct(covered, coverable),
                     "metric": key if group_by == "metric" else "summary",
                     "name": key, "full_name": key})
    return rows


def _file_matches(actual: Any, requested: Any) -> bool:
    if actual is None or requested is None:
        return False
    actual_s = str(actual)
    requested_s = str(requested)
    return actual_s == requested_s or actual_s.endswith(requested_s)


def _read_source_window(path: str, lo: int, hi: int) -> Dict[int, str]:
    out: Dict[int, str] = {}
    if lo < 1:
        lo = 1
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for idx, text in enumerate(fh, start=1):
                if idx < lo:
                    continue
                if idx > hi:
                    break
                out[idx] = text.rstrip("\n")
    except OSError:
        return {}
    return out


def _source_annotation(item: Json) -> Json:
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    out: Json = {
        "metric": item.get("metric"),
        "type": item.get("type"),
        "name": item.get("name"),
        "full_name": item.get("full_name"),
        "covered": item.get("covered"),
        "coverable": item.get("coverable"),
        "missing": item.get("missing"),
        "status": item.get("status"),
        "file": ev.get("file"),
        "line": ev.get("line"),
    }
    for key in ("branch", "branch_bin", "branch_terms", "condition", "condition_bin",
                "condition_terms", "toggle_signal", "toggle_bit", "toggle_transition",
                "assert_kind", "assert_object"):
        if item.get(key) not in (None, ""):
            out[key] = item.get(key)
    return out


def _toggle_transition_summary(rows: List[Json]) -> Json:
    out: Json = {}
    for wanted in ("0 -> 1", "1 -> 0", "npiCovToggle01", "npiCovToggle10"):
        matching = [row for row in rows if str(row.get("toggle_transition")) == wanted]
        if not matching:
            continue
        covered = sum(int(row.get("covered") or 0) for row in matching)
        coverable = sum(int(row.get("coverable") or 0) for row in matching)
        key = {"npiCovToggle01": "0 -> 1", "npiCovToggle10": "1 -> 0"}.get(wanted, wanted)
        out[key] = {"covered": covered, "coverable": coverable,
                    "missing": coverable - covered, "coverage_pct": coverage_pct(covered, coverable)}
    return out


ASSERT_OBJECT_TYPES = {"npiCovAssert", "npiCovCoverProperty", "npiCovCoverSequence"}
ASSERT_BIN_TO_FIELD = {
    "npiCovAttemptBin": "attempts",
    "npiCovSuccessBin": "real_successes",
    "npiCovFailureBin": "failures",
    "npiCovIncompleteBin": "incomplete",
    "npiCovFirstmatchBin": "first_match",
}


def _assert_report_rows(items: List[Json], include_source: bool) -> tuple[List[Json], Json]:
    objects = [row for row in items if row.get("type") in ASSERT_OBJECT_TYPES]
    bins_by_object: Dict[str, List[Json]] = defaultdict(list)
    for row in items:
        if row.get("type") in ASSERT_BIN_TO_FIELD:
            obj = row.get("assert_object") or _parent_assert_object(row.get("full_name"))
            if obj:
                bins_by_object[str(obj)].append(row)
    rows: List[Json] = []
    for obj in objects:
        full = str(obj.get("assert_object") or obj.get("full_name") or obj.get("name") or "")
        counts = _assert_counts(bins_by_object.get(full, []))
        row: Json = {
            "kind": obj.get("assert_kind") or _assert_kind_from_type(obj.get("type")),
            "name": obj.get("name"),
            "full_name": full,
            "category": obj.get("category"),
            "severity": obj.get("severity"),
            "covered": obj.get("covered"),
            "coverable": obj.get("coverable"),
            "missing": obj.get("missing"),
            "coverage_pct": obj.get("coverage_pct"),
            "status": obj.get("status"),
            **counts,
        }
        if include_source:
            row["evidence"] = obj.get("evidence")
        rows.append(row)
    sections = {
        "category_summary": _count_by(rows, "category"),
        "severity_summary": _count_by(rows, "severity"),
        "assert_summary": _kind_summary(rows, "assertion"),
        "cover_property_summary": _kind_summary(rows, "cover_property"),
        "cover_sequence_summary": _kind_summary(rows, "cover_sequence"),
    }
    return rows, sections


def _assert_counts(rows: List[Json]) -> Json:
    counts: Json = {
        "attempts": 0,
        "real_successes": 0,
        "failures": 0,
        "incomplete": 0,
        "first_match": 0,
    }
    for row in rows:
        field = ASSERT_BIN_TO_FIELD.get(str(row.get("type") or ""))
        if not field:
            continue
        try:
            counts[field] += int(row.get("count") or 0)
        except Exception:
            pass
    if counts["attempts"] == 0:
        counts["without_attempts"] = 1
    else:
        counts["without_attempts"] = 0
    return counts


def _assert_kind_from_type(typ: Any) -> str:
    return {
        "npiCovAssert": "assertion",
        "npiCovCoverProperty": "cover_property",
        "npiCovCoverSequence": "cover_sequence",
    }.get(str(typ or ""), "assertion")


def _parent_assert_object(full_name: Any) -> str | None:
    if not full_name or "." not in str(full_name):
        return None
    return str(full_name).rsplit(".", 1)[0]


def _count_by(rows: List[Json], field: str) -> List[Json]:
    grouped: Dict[str, int] = defaultdict(int)
    for row in rows:
        key = row.get(field)
        if key in (None, -1, "-1", ""):
            key = "unknown"
        grouped[str(key)] += 1
    return [{field: key, "count": count} for key, count in sorted(grouped.items())]


def _kind_summary(rows: List[Json], kind: str) -> Json:
    subset = [row for row in rows if row.get("kind") == kind]
    return {
        "kind": kind,
        "total": len(subset),
        "success": sum(1 for row in subset if int(row.get("missing") or 0) == 0),
        "failure": sum(1 for row in subset if int(row.get("failures") or 0) > 0),
        "incomplete": sum(1 for row in subset if int(row.get("incomplete") or 0) > 0),
        "without_attempts": sum(int(row.get("without_attempts") or 0) for row in subset),
        "attempts": sum(int(row.get("attempts") or 0) for row in subset),
        "real_successes": sum(int(row.get("real_successes") or 0) for row in subset),
        "first_match": sum(int(row.get("first_match") or 0) for row in subset),
    }


def _first_evidence(rows: List[Json]) -> Json:
    for row in rows:
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if ev.get("file") or ev.get("line") is not None:
            return dict(ev)
    return {}


def _export_output_path(args: Json) -> str:
    output = args.get("output") if isinstance(args.get("output"), dict) else {}
    path = output.get("path")
    if not path:
        raise XcovError("OUTPUT_PATH_REQUIRED", "output.path is required")
    return str(path)


def _write_markdown_artifact(path: str, text: str, allow_absolute_path: bool) -> str:
    resolved = resolve_artifact_path(path, allow_absolute_path=allow_absolute_path)
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        with open(resolved, "w", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
    except OSError as exc:
        raise XcovError("OUTPUT_WRITE_FAILED", str(exc), path=resolved) from exc
    return resolved


def _coverage_sort_key(row: Json) -> tuple[float, str]:
    pct = row.get("coverage_pct")
    try:
        pct_f = float(pct)
    except Exception:
        pct_f = 101.0
    return (pct_f, str(row.get("full_name") or row.get("name") or ""))


def _below_threshold(row: Json, threshold: float) -> bool:
    pct = row.get("coverage_pct")
    try:
        return float(pct) < threshold
    except Exception:
        return int(row.get("missing") or 0) > 0


def _evidence_loc(row: Json) -> str:
    ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    file_name = ev.get("file")
    line = ev.get("line")
    if file_name and line is not None:
        return f"{file_name}:{line}"
    if file_name:
        return str(file_name)
    return ""


def _md(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _yes_no_covered(value: Any) -> str:
    try:
        return "yes" if int(value) > 0 else "no"
    except Exception:
        return "unknown"


def _code_coverage_markdown(rows: List[Json], threshold: float) -> tuple[str, int]:
    rows = [row for row in rows if row.get("metric") in _code_metrics() and _below_threshold(row, threshold)]
    rows.sort(key=_coverage_sort_key)
    lines = [
        "# Code Coverage Holes",
        "",
        f"Threshold: {threshold:g}%",
        "",
    ]
    exported = 0
    for metric in _code_metrics():
        subset = [row for row in rows if row.get("metric") == metric]
        lines.extend([f"## {metric}", ""])
        if not subset:
            lines.extend(["No items below threshold.", ""])
            continue
        if metric == "toggle":
            lines.extend([
                "| scope | signal | bit | 0->1 covered | 1->0 covered | coverage_pct | file:line |",
                "|---|---|---|---|---|---:|---|",
            ])
            for item in _toggle_export_rows(subset):
                exported += 1
                lines.append(
                    f"| {_md(item.get('scope'))} | {_md(item.get('signal'))} | {_md(item.get('bit'))} | "
                    f"{_md(item.get('0_to_1_covered'))} | {_md(item.get('1_to_0_covered'))} | "
                    f"{_md(item.get('coverage_pct'))} | {_md(item.get('location'))} |"
                )
        elif metric in {"branch", "condition", "fsm"}:
            label = {"branch": "branch/bin", "condition": "condition/bin", "fsm": "state/transition"}[metric]
            lines.extend([
                f"| scope | {label} | covered | coverage_pct | file:line |",
                "|---|---|---|---:|---|",
            ])
            for row in subset:
                exported += 1
                lines.append(
                    f"| {_md(row.get('scope'))} | {_md(_code_item_label(row))} | "
                    f"{_yes_no_covered(row.get('covered'))} | {_md(row.get('coverage_pct'))} | {_md(_evidence_loc(row))} |"
                )
        else:
            lines.extend([
                "| scope | object | covered | coverage_pct | file:line |",
                "|---|---|---|---:|---|",
            ])
            for row in subset:
                exported += 1
                lines.append(
                    f"| {_md(row.get('scope'))} | {_md(row.get('full_name') or row.get('name'))} | "
                    f"{_yes_no_covered(row.get('covered'))} | {_md(row.get('coverage_pct'))} | {_md(_evidence_loc(row))} |"
                )
        lines.append("")
    return "\n".join(lines), exported


def _toggle_export_rows(rows: List[Json]) -> List[Json]:
    grouped: Dict[tuple[str, str], List[Json]] = defaultdict(list)
    for row in rows:
        signal = str(row.get("toggle_signal") or row.get("full_name") or row.get("name") or "")
        bit = str(row.get("toggle_bit") or signal)
        grouped[(signal, bit)].append(row)
    out: List[Json] = []
    for (signal, bit), subset in grouped.items():
        transitions = _toggle_transition_summary(subset)
        covered = sum(int(row.get("covered") or 0) for row in subset)
        coverable = sum(int(row.get("coverable") or 0) for row in subset)
        out.append({
            "scope": subset[0].get("scope"),
            "signal": signal,
            "bit": bit,
            "0_to_1_covered": _yes_no_covered((transitions.get("0 -> 1") or {}).get("covered")),
            "1_to_0_covered": _yes_no_covered((transitions.get("1 -> 0") or {}).get("covered")),
            "coverage_pct": coverage_pct(covered, coverable),
            "location": _evidence_loc(_first_evidence_row(subset)),
        })
    return sorted(out, key=_coverage_sort_key)


def _first_evidence_row(rows: List[Json]) -> Json:
    ev = _first_evidence(rows)
    return {"evidence": ev}


def _code_item_label(row: Json) -> str:
    metric = row.get("metric")
    if metric == "branch":
        return " / ".join(str(v) for v in (row.get("branch"), row.get("branch_bin")) if v not in (None, ""))
    if metric == "condition":
        return " / ".join(str(v) for v in (row.get("condition"), row.get("condition_bin")) if v not in (None, ""))
    if metric == "fsm":
        return str(row.get("fsm_transition") or row.get("full_name") or row.get("name") or "")
    return str(row.get("full_name") or row.get("name") or "")


def _function_coverage_markdown(rows: List[Json], threshold: float,
                                covergroup_filter: Any = None) -> tuple[str, int]:
    if covergroup_filter:
        rows = [row for row in rows if _covergroup_matches(row.get("covergroup"), str(covergroup_filter))]
    groups: Dict[str, List[Json]] = defaultdict(list)
    for row in rows:
        cg = row.get("covergroup")
        if cg:
            groups[str(cg)].append(row)
    lines = [
        "# Function Coverage Holes",
        "",
        f"Threshold: {threshold:g}%",
        "",
    ]
    exported = 0
    for cg in sorted(groups):
        subset = groups[cg]
        cg_row = next((row for row in subset if _functional_level(row) == "covergroup"), None)
        loc = _evidence_loc(cg_row or {})
        header = f"## {cg}"
        if loc:
            header += f" ({loc})"
        lines.extend([header, ""])
        parents = [row for row in subset if _functional_level(row) in {"coverpoint", "cross"}]
        for parent in sorted(parents, key=lambda r: str(r.get("full_name") or r.get("name") or "")):
            parent_name = parent.get("coverpoint") or parent.get("cross") or parent.get("name")
            lines.extend([f"### {parent_name}", ""])
            bins = [
                row for row in subset
                if _functional_level(row) == "bin"
                and (row.get("coverpoint") == parent.get("coverpoint")
                     or row.get("cross") == parent.get("cross"))
                and _below_threshold(row, threshold)
            ]
            if not bins:
                lines.extend(["No bins below threshold.", ""])
                continue
            lines.extend([
                "| bin | covered | coverable | count | coverage_pct |",
                "|---|---:|---:|---:|---:|",
            ])
            for row in sorted(bins, key=_coverage_sort_key):
                exported += 1
                lines.append(
                    f"| {_md(row.get('bin') or row.get('name'))} | {_md(row.get('covered'))} | "
                    f"{_md(row.get('coverable'))} | {_md(row.get('count'))} | {_md(row.get('coverage_pct'))} |"
                )
            lines.append("")
    if not groups:
        lines.extend(["No covergroups matched.", ""])
    return "\n".join(lines), exported


def _covergroup_matches(covergroup: Any, pattern: str) -> bool:
    if covergroup is None:
        return False
    import fnmatch
    return fnmatch.fnmatchcase(str(covergroup), pattern)


def _assert_markdown(rows: List[Json], sections: Json, threshold: float) -> tuple[str, int]:
    selected = [
        row for row in rows
        if _below_threshold(row, threshold)
        or int(row.get("failures") or 0) > 0
        or int(row.get("incomplete") or 0) > 0
        or int(row.get("without_attempts") or 0) > 0
    ]
    selected.sort(key=_coverage_sort_key)
    lines = [
        "# Assertion Coverage",
        "",
        f"Threshold: {threshold:g}%",
        "",
        "## Summary",
        "",
    ]
    for key in ("assert_summary", "cover_property_summary", "cover_sequence_summary"):
        row = sections.get(key) if isinstance(sections, dict) else None
        if isinstance(row, dict):
            lines.append(
                f"- {key}: total={row.get('total')} success={row.get('success')} "
                f"failure={row.get('failure')} incomplete={row.get('incomplete')} "
                f"without_attempts={row.get('without_attempts')}"
            )
    lines.extend(["", "## Items", ""])
    if selected:
        lines.extend([
            "| kind | object | attempts | real_successes | failures | incomplete | first_match | coverage_pct | file:line |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for row in selected:
            lines.append(
                f"| {_md(row.get('kind'))} | {_md(row.get('full_name') or row.get('name'))} | "
                f"{_md(row.get('attempts'))} | {_md(row.get('real_successes'))} | "
                f"{_md(row.get('failures'))} | {_md(row.get('incomplete'))} | "
                f"{_md(row.get('first_match'))} | {_md(row.get('coverage_pct'))} | {_md(_evidence_loc(row))} |"
            )
    else:
        lines.append("No assertion items below threshold.")
    lines.append("")
    return "\n".join(lines), len(selected)


def _functional_summary_rows(rows: List[Json], group_by: str) -> List[Json]:
    if group_by == "covergroup":
        return _functional_covergroup_score_rows(rows)
    return _summary_from_items(_functional_summary_level_rows(rows, group_by), group_by)


def _functional_covergroup_score_rows(rows: List[Json]) -> List[Json]:
    by_cg: Dict[str, List[Json]] = defaultdict(list)
    for row in rows:
        cg = row.get("covergroup")
        if cg:
            by_cg[str(cg)].append(row)
    out: List[Json] = []
    for cg, subset in by_cg.items():
        direct = [row for row in subset if _functional_level(row) in {"coverpoint", "cross"}]
        raw = next((row for row in subset if _functional_level(row) == "covergroup"), None)
        score_rows = direct or ([raw] if raw else [])
        pct_values = [
            float(row["coverage_pct"]) for row in score_rows
            if row and row.get("coverage_pct") is not None
        ]
        score_pct = round(sum(pct_values) / len(pct_values), 4) if pct_values else None
        raw_covered = raw.get("covered") if raw else None
        raw_coverable = raw.get("coverable") if raw else None
        out_row = {
            "covergroup": cg,
            "metric": "summary",
            "name": cg,
            "full_name": cg,
            "coverage_pct": score_pct,
            "score_basis": "average_direct_coverpoint_cross_pct" if direct else "covergroup_raw_pct",
            "score_item_count": len(score_rows),
            "raw_covered": raw_covered,
            "raw_coverable": raw_coverable,
            "raw_missing": _safe_missing(raw_covered, raw_coverable),
            "raw_coverage_pct": coverage_pct(raw_covered, raw_coverable),
        }
        if raw:
            out_row.update({
                "covered": raw.get("covered"),
                "coverable": raw.get("coverable"),
                "missing": raw.get("missing"),
            })
        out.append(out_row)
    return out


def _safe_missing(covered: Any, coverable: Any) -> int | None:
    try:
        return int(coverable) - int(covered)
    except Exception:
        return None


def _functional_level(row: Json) -> str:
    typ = str(row.get("type") or "")
    type_to_level = {
        "npiCovCovergroup": "covergroup",
        "npiCovCoverpoint": "coverpoint",
        "npiCovCross": "cross",
        "npiCovCoverBin": "bin",
    }
    if typ in type_to_level:
        return type_to_level[typ]
    if row.get("bin") is not None:
        return "bin"
    if row.get("cross") is not None:
        return "cross"
    if row.get("coverpoint") is not None:
        return "coverpoint"
    return "covergroup"


def _filter_functional_levels(rows: List[Json], levels: Any) -> List[Json]:
    if not levels:
        return rows
    wanted = {str(level) for level in levels}
    return [row for row in rows if _functional_level(row) in wanted]


def _functional_summary_level_rows(rows: List[Json], group_by: str) -> List[Json]:
    if group_by not in {"covergroup", "coverpoint", "cross", "bin"}:
        return rows
    return [row for row in rows if _functional_level(row) == group_by]
