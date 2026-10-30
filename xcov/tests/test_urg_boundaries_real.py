"""Real code-only VDB coverage; consume only the prepared FixtureStore resource."""
from __future__ import annotations

import json
from pathlib import Path

from xcov.actions import Dispatcher
from xcov.session import SessionManager


def test_real_no_functional_vdb_cold_warm(xverif_fixture, tmp_path):
    vdb = xverif_fixture("xcov.no_functional") / "no_functional.vdb"
    for expected_hit in (False, True):
        sessions = SessionManager()
        session = sessions.open(str(vdb), name="code-only", cache_dir=str(tmp_path))
        try:
            assert session.backend.cache_info["hit"] is expected_hit
            dispatcher = Dispatcher(sessions=sessions)
            responses = {}
            for action, args in (
                ("code_coverage.summary", {"scope": "code_only", "metrics": ["line"]}),
                ("functional_coverage.summary", {}),
                ("assert.summary", {}),
            ):
                response = dispatcher.dispatch({
                    "api_version": "xcov.v1", "request_id": action, "action": action,
                    "target": {"session_id": session.session_id}, "args": args,
                })
                assert response["ok"], json.dumps(response, ensure_ascii=False)
                responses[action] = response
            assert responses["code_coverage.summary"]["data"]["items"][0]["coverable"] > 0
            assert responses["functional_coverage.summary"]["data"]["items"] == []
            assert responses["assert.summary"]["data"]["items"] == []
            assert session.backend.npi_initialized is False
            entry = Path(session.backend.cache_info["entry"])
            manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
            assert set(manifest["artifacts"]) == {"session.xml", "tests.txt", "dashboard.txt", "modlist.txt"}
        finally:
            session.close(confirm_discard_reasons=True)
