from __future__ import annotations

from xverif_mcp.schema_projection import project


def _native_request() -> dict:
    return {
        "ok": True,
        "data": {
            "schema_path": "schemas/v1/actions/value.at.request.schema.json",
            "schema": {
                "x-description-zh": "读取一个采样点的值。",
                "properties": {
                    "args": {
                        "type": "object", "required": ["signal", "time"],
                        "properties": {
                            "signal": {"type": "string", "description": "目标叶子信号。"},
                            "time": {"type": "string", "description": "目标时间。"},
                        }, "additionalProperties": False,
                    },
                    "limits": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
        },
    }


def test_mcp_projection_exposes_args_guide_without_native_envelope() -> None:
    result = project("value.at", "request", "mcp", _native_request())
    payload = result["data"]
    assert payload["call_with"] == "xverif_debug_query"
    assert "api_version" not in payload["args_schema"]["properties"]
    assert {item["path"] for item in payload["parameter_guide"]} >= {"args.signal", "args.time"}
    assert payload["minimal_call"]["action"] == "value.at"


def test_response_view_requires_response_kind() -> None:
    result = project("value.at", "request", "response", _native_request())
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
