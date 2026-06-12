from __future__ import annotations

from collections import defaultdict
import time
from typing import Any, Dict, Iterable, List, Optional

from .backend import METRICS
from .errors import XcovError, error_response
from .logging import (log_action_event, request_summary_for_log,
                      response_summary_for_log, update_session_manifest)
from .protocol import ok_response
from .query import (apply_output, coverage_pct, filter_items, filters_summary,
                    query_args, sort_items)
from .schemas import schema_for_action
from .session import SessionManager

Json = Dict[str, Any]

P0_ACTIONS = [
    "session.open", "session.status", "session.close",
    "tests.list", "metrics.list",
    "scope.summary", "scope.children", "scope.search",
    "cov.summary", "cov.holes", "cov.object.get", "cov.object.search",
    "functional.summary", "functional.holes",
    "source.map",
    "export.summary", "export.holes", "export.scope_tree", "export.functional",
]


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
                elif action in ("cov.summary", "cov.holes", "cov.object.search", "cov.object.get"):
                    rsp = self._cov(req, sess)
                elif action in ("functional.summary", "functional.holes"):
                    rsp = self._functional(req, sess)
                elif action == "source.map":
                    rsp = self._source_map(req, sess)
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
            rsp = error_response(req.get("action", ""), req.get("request_id", "req-unknown"),
                                 exc.code, exc.message, **exc.detail)
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
        rows += [{"name": a, "status": "p1"} for a in
                 ["index.build", "index.status", "exclude.summary", "assert.report"]]
        rows += [{"name": a, "status": "p2"} for a in
                 ["compare.tests", "compare.vdb", "exclude.load", "exclude.save"]]
        return ok_response(req, {"matched_count": len(rows), "returned": len(rows),
                                 "truncated": False, "output_path": None},
                           {"items": rows})

    def _schema(self, req: Json) -> Json:
        action = merged_action_args(req).get("action")
        if action not in P0_ACTIONS and action not in ("actions", "schema"):
            raise XcovError("ACTION_NOT_FOUND", "schema action not found", action=action)
        kind = str(merged_action_args(req).get("kind", "request"))
        try:
            schema = schema_for_action(str(action), kind)
        except KeyError:
            raise XcovError("ACTION_NOT_FOUND", "schema action not found", action=action, kind=kind)
        return ok_response(req, {"matched_count": 1, "returned": 1,
                                 "truncated": False, "output_path": None},
                           {"schema": schema})

    def _session_open(self, req: Json) -> Json:
        target = req.get("target", {})
        args = merged_action_args(req)
        vdb = target.get("vdb")
        if not vdb:
            raise XcovError("VDB_OPEN_FAILED", "target.vdb is required")
        sess = self.sessions.open(
            str(vdb), name=args.get("name"), fake=bool(args.get("fake")),
            reuse=bool(args.get("reuse", True)), reopen=bool(args.get("reopen", False)))
        summary = sess.public_json()
        summary.update({"matched_count": 1, "returned": 1,
                        "truncated": False, "output_path": None})
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
        query = query_args(args)
        rows = filter_items(sess.backend.tests(), query)
        summary, inline, warnings = apply_output("tests.list", args, rows)
        summary["session_id"] = sess.session_id
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _metrics_list(self, req: Json, sess) -> Json:
        args = merged_action_args(req)
        rows = sess.backend.metrics_for_scope(args.get("scope"), str(args.get("test", "merged")))
        summary, inline, warnings = apply_output("metrics.list", args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged")})
        return ok_response(req, summary, {"items": inline}, warnings)

    def _scope(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        scopes = _indexed_scopes(sess.backend.scopes())
        if action == "scope.search":
            rows = _scope_search_rows(scopes, args)
        else:
            metrics = args.get("metrics") or METRICS
            items = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                      test=str(args.get("test", "merged")))
            coverage = _scope_coverage(items, metrics)
            if action == "scope.summary":
                rows = _scope_summary_rows(scopes, coverage, args)
            else:
                rows = _scope_children_rows(scopes, coverage, args)
        rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged")})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _cov(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        metrics = args.get("metrics")
        if action == "cov.object.get":
            rows = _object_get_rows(sess, args, metrics)
        else:
            rows = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                      test=str(args.get("test", "merged")))
            if action == "cov.holes":
                rows = [r for r in rows if int(r.get("missing") or 0) > 0]
            if action == "cov.summary":
                rows = _summary_from_items(rows, str(args.get("group_by", "metric")))
            rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows)
        summary.update({"session_id": sess.session_id, "scope": args.get("scope"),
                        "test": args.get("test", "merged"), "metrics": metrics or METRICS})
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)

    def _functional(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        query = query_args(args)
        rows = sess.backend.items(metrics=["functional"], scope=args.get("scope"),
                                  test=str(args.get("test", "merged")),
                                  functional_only=True)
        rows = _filter_functional_levels(rows, args.get("levels"))
        if action == "functional.holes":
            rows = [r for r in rows if int(r.get("missing") or 0) > 0]
        else:
            rows = _summary_from_items(rows, str(args.get("group_by", "covergroup")))
        rows = filter_items(rows, query)
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
        for item in sess.backend.items(metrics=metrics, test=str(args.get("test", "merged"))):
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

    def _export(self, req: Json, sess) -> Json:
        action = req["action"]
        args = merged_action_args(req)
        output = dict(args.get("output") or {})
        output.setdefault("mode", "file")
        args["output"] = output
        if action == "export.summary":
            rows = _summary_from_items(sess.backend.items(metrics=args.get("metrics"),
                                                          scope=args.get("scope"),
                                                          test=str(args.get("test", "merged"))),
                                       str(args.get("group_by", "scope")))
        elif action == "export.holes":
            rows = [r for r in sess.backend.items(metrics=args.get("metrics"),
                                                  scope=args.get("scope"),
                                                  test=str(args.get("test", "merged")))
                    if int(r.get("missing") or 0) > 0]
        elif action == "export.scope_tree":
            metrics = args.get("metrics") or METRICS
            scopes = _indexed_scopes(sess.backend.scopes())
            items = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                      test=str(args.get("test", "merged")))
            coverage = _scope_coverage(items, metrics)
            rows = _scope_tree_rows(scopes, coverage, args)
        elif action == "export.functional":
            rows = sess.backend.items(metrics=["functional"], scope=args.get("scope"),
                                      test=str(args.get("test", "merged")),
                                      functional_only=True)
            rows = _filter_functional_levels(rows, args.get("levels"))
            if args.get("mode") == "holes":
                rows = [r for r in rows if int(r.get("missing") or 0) > 0]
        else:
            raise XcovError("ACTION_NOT_FOUND", "unknown export action", action=action)
        query = query_args(args)
        rows = filter_items(rows, query)
        rows = sort_items(rows, args.get("sort"))
        summary, inline, warnings = apply_output(action, args, rows, default_mode="file")
        summary["session_id"] = sess.session_id
        return ok_response(req, summary, {"filters": filters_summary(query), "items": inline}, warnings)


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


def _scope_search_rows(scopes: Dict[str, Json], args: Json) -> List[Json]:
    root = args.get("scope")
    rows = list(scopes.values())
    if root:
        rows = [r for r in rows if _is_descendant(str(r.get("full_name", "")), str(root))]
    return rows


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


def _scope_tree_rows(scopes: Dict[str, Json], coverage: Dict[str, Json], args: Json) -> List[Json]:
    root = args.get("scope")
    recursive = bool(args.get("recursive", True))
    out = []
    for full, row in scopes.items():
        if root:
            if recursive:
                selected = _is_descendant(full, str(root))
            else:
                selected = full == str(root) or _is_direct_child(full, str(root))
        else:
            selected = True
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


def _merge_scope_coverage(scope: Json, cov: Optional[Json]) -> Json:
    out = dict(scope)
    cov = cov or {"covered": 0, "coverable": 0, "missing": 0,
                  "coverage_pct": None, "metrics": []}
    out.update(cov)
    return out


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


def _object_get_rows(sess: Any, args: Json, metrics: Any) -> List[Json]:
    name = args.get("name")
    include_children = bool(args.get("include_children", False))
    max_children = int(args.get("max_children", 50))
    candidates = sess.backend.items(metrics=metrics, scope=args.get("scope"),
                                    test=str(args.get("test", "merged")))
    rows = []
    for row in candidates:
        full = str(row.get("full_name", ""))
        short = str(row.get("name", ""))
        if full == name or short == name:
            rows.append(row)
        elif include_children and name and full.startswith(str(name) + "."):
            rows.append(row)
    if include_children and max_children >= 0:
        rows = rows[:max_children]
    if not rows:
        raise XcovError("OBJECT_NOT_FOUND", "coverage object not found", name=name)
    return rows


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
