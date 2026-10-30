"""Real TYPE coverage scores; consume the prepared catalog fixture only."""
from __future__ import annotations

import json

from xcov.actions import Dispatcher
from xcov.session import SessionManager


def test_real_functional_type_scores_cold_warm(xverif_fixture, tmp_path):
    vdb = xverif_fixture("xcov.functional_scores") / "functional_scores.vdb"
    expected = {
        "weighted_cg": (66.6667, 1, 3),
        "goals_cg": (25.0, 1, 4),
        "cross_goals_cg": (37.5, 3, 8),
        "type_only_cg": (50.0, 1, 2),
        "instances::cg": (100.0, 2, 2),
        "merged_instances::cg": (100.0, 2, 2),
    }
    for expected_hit in (False, True):
        sessions = SessionManager()
        session = sessions.open(str(vdb), name="type-scores", cache_dir=str(tmp_path))
        try:
            assert session.backend.cache_info["hit"] is expected_hit
            dispatcher = Dispatcher(sessions=sessions)
            def request(action, args):
                response = dispatcher.dispatch({
                    "api_version": "xcov.v1", "request_id": action, "action": action,
                    "target": {"session_id": session.session_id}, "args": args,
                })
                assert response["ok"], json.dumps(response, ensure_ascii=False)
                return response
            response = request("functional_coverage.summary", {"scope": "functional_scores"})
            rows = {row["covergroup"]: row for row in response["data"]["items"]}
            assert len(rows) == 8
            assert response["summary"]["analysis_complete"] is False
            assert response["summary"]["scan_complete"] is True
            assert response["warnings"]
            for name, values in expected.items():
                row = rows[f"functional_scores::{name}"]
                assert (row["coverage_pct"], row["covered"], row["coverable"]) == values
            for name in ("empty_cg", "zero_weight_cg"):
                row = rows[f"functional_scores::{name}"]
                assert all(row[key] is None for key in ("coverage_pct", "covered", "coverable", "missing"))
            points = request("functional_coverage.summary", {"group_by": "coverpoint"})
            assert points["summary"]["analysis_complete"] is False
            assert len([row for row in points["data"]["items"] if row["coverpoint"].endswith("::cp")]) == 3
            scope = request("scope.summary", {"scope": "functional_scores", "metrics": ["functional"]})
            assert scope["summary"]["analysis_complete"] is False
            assert scope["warnings"]
            metrics = request("metrics.list", {"scope": "functional_scores"})
            functional = next(row for row in metrics["data"]["items"] if row["metric"] == "functional")
            assert functional["coverage_pct"] is functional["covered"] is functional["coverable"] is None
            assert session.backend.npi_initialized is False
        finally:
            session.close(confirm_discard_reasons=True)
