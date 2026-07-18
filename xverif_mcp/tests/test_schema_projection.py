from __future__ import annotations

import json
from pathlib import Path

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


def test_mcp_projection_exposes_compact_schema_without_native_envelope() -> None:
    result = project("value.at", "request", "mcp", _native_request())
    payload = result["data"]
    assert payload["call_with"] == "xverif_debug_query"
    assert payload["purpose_en"] == (
        "Read one signal at an exact waveform time, optionally using clock-sampled context."
    )
    assert payload["purpose_zh"] == "读取单个信号在指定时间的值。"
    assert "api_version" not in payload["args_schema"]["properties"]
    assert payload["minimal_call"]["action"] == "value.at"
    assert {"purpose", "parameter_guide", "common_examples", "corrected_examples"}.isdisjoint(payload)


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


def test_session_selector_schema_and_invalid_example_are_consistent() -> None:
    result = project("session.close", "request", "mcp", _native_request())
    payload = result["data"]
    assert payload["args_schema"]["anyOf"] == [{"required": ["name"]}, {"required": ["session_id"]}]
    assert payload["invalid_examples"][0]["call"] == {}


def test_all_action_projections_have_one_field_contract_and_one_success_example() -> None:
    root = Path(__file__).resolve().parents[2]
    actions = json.loads((root / "xdebug/specs/actions/actions.yaml").read_text(encoding="utf-8"))["actions"]
    redundant = {"purpose", "parameter_guide", "common_examples", "corrected_examples"}
    for action in actions:
        if action["status"] == "removed":
            continue
        schema = json.loads((root / "xdebug" / action["schemas"]["request"]).read_text(encoding="utf-8"))
        payload = project(action["name"], "request", "mcp", {"ok": True, "data": {"schema": schema}})["data"]
        assert redundant.isdisjoint(payload), action["name"]
        assert "args_schema" in payload and "minimal_call" in payload, action["name"]
        assert not _contains_key(payload["args_schema"], "x-description-zh"), action["name"]
        assert not any(item.startswith(("必须提供：", "还必须满足以下一组参数：", "当 "))
                       for item in payload["constraints"]), action["name"]


def test_stream_cache_scope_is_visible_in_mcp_projection() -> None:
    root = Path(__file__).resolve().parents[2]
    for action in ("stream.query", "stream.export", "stream.validate"):
        schema = json.loads((
            root / "xdebug/schemas/v1/actions" /
            (action + ".request.schema.json")
        ).read_text(encoding="utf-8"))
        payload = project(
            action, "request", "mcp",
            {"ok": True, "data": {"schema": schema}},
        )["data"]
        cache_scope = payload["args_schema"]["properties"]["cache_scope"]
        assert cache_scope["enum"] == ["full", "range"]
        assert cache_scope["default"] == "full"
        assert any("cache_scope" in item for item in payload["constraints"])
    validate_schema = json.loads((
        root / "xdebug/schemas/v1/actions/stream.validate.request.schema.json"
    ).read_text(encoding="utf-8"))
    validate_args = project(
        "stream.validate", "request", "mcp",
        {"ok": True, "data": {"schema": validate_schema}},
    )["data"]["args_schema"]
    assert validate_args["allOf"][0]["then"]["not"]["required"] == [
        "cache_scope"
    ]


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False
