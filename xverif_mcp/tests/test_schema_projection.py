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
    assert payload["purpose_en"] == "Read one signal value at a sampled waveform time."
    assert payload["purpose_zh"] == "读取单个信号在指定时间的值。"
    assert "api_version" not in payload["args_schema"]["properties"]
    assert {item["path"] for item in payload["parameter_guide"]} >= {"args.signal", "args.time"}
    assert payload["minimal_call"]["action"] == "value.at"


def test_response_view_requires_response_kind() -> None:
    result = project("value.at", "request", "response", _native_request())
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_response_kind_does_not_implicitly_change_view() -> None:
    result = project("value.at", "response", "mcp", _native_request())
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_session_actions_use_the_dedicated_mcp_tool() -> None:
    result = project("session.open", "request", "mcp", _native_request())
    payload = result["data"]
    assert payload["call_with"] == "xverif_debug_session_open"
    assert payload["required_session"] is False
    assert payload["args_schema"]["required"] == ["name"]


def test_session_selector_schema_and_repair_example_are_consistent() -> None:
    result = project("session.close", "request", "mcp", _native_request())
    payload = result["data"]
    assert payload["args_schema"]["anyOf"] == [{"required": ["name"]}, {"required": ["session_id"]}]
    assert payload["invalid_examples"][0]["call"] == {}
    assert payload["corrected_examples"][0]["call"] == {"name": "<name>"}
