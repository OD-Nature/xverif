"""Real MCP coverage lifecycle; requires the catalog VDB and licensed EDA."""
from __future__ import annotations
import json
from pathlib import Path
import anyio
import pytest
from test_mcp_sdk_smoke import _server, _call_server_tool

def test_cov_session_real_lifecycle(monkeypatch: pytest.MonkeyPatch, xverif_fixture):
    """通过真实 xcov --stdio-loop 子进程测试 session 生命周期."""
    overrides = {
        "XVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "XVERIF_MCP_BACKEND": "direct",
    }
    test_vdb = str(xverif_fixture("xcov.comprehensive") / "comprehensive.vdb")
    server = _server(monkeypatch, overrides)

    async def _run():
        opened = await server.mcp.call_tool(
            "xverif_cov_session_open",
            {"name": "cov_real", "vdb": test_vdb},
        )
        queried_json = await server.mcp.call_tool(
            "xverif_cov_query",
            {"session_id": "cov_real", "action": "code_coverage.summary",
             "args": {"metrics": ["toggle", "branch"], "limits": {"max_items": 1}},
             "output_format": "json"},
        )
        queried_xout = await server.mcp.call_tool(
            "xverif_cov_query",
            {"session_id": "cov_real", "action": "code_coverage.summary",
             "args": {"group_by": "metric"},
             "output_format": "xout"},
        )
        closed = await server.mcp.call_tool(
            "xverif_cov_session_close",
            {"session_id": "cov_real"},
        )
        return opened, queried_json, queried_xout, closed

    opened, queried_json, queried_xout, _ = anyio.run(_run)
    opened_payload = json.loads(opened[0].text)
    queried_payload = json.loads(queried_json[0].text)
    queried_xout_text = queried_xout[0].text
    assert opened_payload["ok"] is True
    assert opened_payload["session"]["state"] == "alive"
    assert queried_payload["summary"]["returned_count"] == 1
    assert queried_xout_text.startswith("@xcov.code_coverage.summary.v1")
    assert "XOUT_BEGIN" not in queried_xout_text
    assert "XOUT_END" not in queried_xout_text


def test_batch_real_lifecycle(tmp_path, monkeypatch: pytest.MonkeyPatch, xverif_fixture):
    """xverif_batch with real cov session + ping + bit_eval in one file."""
    batch_file = tmp_path / "batch.ndjson"
    output_file = tmp_path / "results.ndjson"

    overrides = {
        "XVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "XVERIF_MCP_BACKEND": "direct",
    }
    test_vdb = str(xverif_fixture("xcov.comprehensive") / "comprehensive.vdb")
    server = _server(monkeypatch, overrides)

    batch_file.write_text("\n".join([
        json.dumps({"tool": "xverif_cov_session_open",
                     "args": {"name": "cov_real", "vdb": test_vdb}}),
        json.dumps({"tool": "xverif_cov_query",
                     "args": {"session_id": "cov_real", "action": "code_coverage.summary",
                              "args": {"metrics": ["line"], "limits": {"max_items": 2}},
                              "output_format": "json"}}),
        json.dumps({"tool": "xverif_cov_session_close",
                     "args": {"session_id": "cov_real"}}),
        json.dumps({"tool": "xverif_ping", "args": {}}),
        json.dumps({"tool": "xverif_bit_eval",
                     "args": {"expr": "2 + 3"}}),
    ]) + "\n")

    content, _ = _call_server_tool(
        server,
        "xverif_batch",
        {"batch_file": str(batch_file), "output_file": str(output_file)},
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["total"] == 5
    assert payload["ok_count"] == 5
    assert payload["failed_count"] == 0

    lines = [json.loads(l) for l in output_file.read_text().splitlines() if l]
    assert len(lines) == 5
    assert all(r["ok"] for r in lines)
