from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CliRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = result.response
    if (
        result.returncode == 0
        and not result.timed_out
        and isinstance(response, dict)
        and response.get("ok") is True
    ):
        return response
    artifact_dir = ArtifactWriter(artifact_root).write(
        case_name,
        result,
        extra=extra,
    )
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout:\n%s\nstderr:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


def _query(
    cli_runner: CliRunner,
    request: dict[str, Any],
    *,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, Any]:
    result = cli_runner.run(request, timeout_sec=timeout_sec)
    return _require_success(
        result,
        case_name=case_name,
        artifact_root=artifact_root,
        extra=extra,
    )


def _query_xout(
    cli_runner: CliRunner,
    request: dict[str, Any],
    *,
    case_name: str,
    artifact_root: Path,
    timeout_sec: float = 180.0,
) -> str:
    result = cli_runner.run(request, output_format="xout", timeout_sec=timeout_sec)
    if result.returncode == 0 and not result.timed_out and isinstance(result.response, str):
        return result.response
    artifact_dir = ArtifactWriter(artifact_root).write(case_name, result)
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout:\n%s\nstderr:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.stream
@pytest.mark.regression
@pytest.mark.slow
def test_stream_v1_real_waveform_actions(
    cli_runner: CliRunner,
    xdebug_root: Path,
    artifact_root: Path,
    tmp_path: Path,
    xverif_fixture: Any,
) -> None:
    fixture_dir = xdebug_root / "testdata" / "waveform" / "stream_v1"
    config_path = fixture_dir / "config" / "streams.json"

    resources = xverif_fixture("xdebug.stream_v1")
    fsdb = resources / "out" / "waves.fsdb"
    expected_path = resources / "out" / "stream_expected.json"
    assert fsdb.is_file() and fsdb.stat().st_size > 0
    assert expected_path.is_file()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))["streams"]

    open_response = _query(
        cli_runner,
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": "stream_v1_real"},
        },
        case_name="stream-v1-session-open",
        artifact_root=artifact_root,
    )
    session = open_response.get("session") or open_response["data"]["session"]
    target = {"session_id": session["id"]}

    try:
        loaded = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "target": target,
                "args": {"config_path": str(config_path), "mode": "replace"},
            },
            case_name="stream-v1-config-load",
            artifact_root=artifact_root,
            extra={"config": json.loads(config_path.read_text(encoding="utf-8"))},
        )
        assert loaded["summary"]["loaded"] == len(expected)
        assert len(loaded["data"]["validation"]) == len(expected)
        ready_preflight = next(
            item for item in loaded["data"]["validation"]
            if item["stream"] == "ready_packet"
        )
        assert ready_preflight["status"] == "ok"
        assert ready_preflight["sampling"] == {
            "clock": "clk", "edge": "posedge", "sample_point": "before"
        }
        assert ready_preflight["packet_rules"] == {
            "packet_enabled": True,
            "channel_id_valid": "every_beat",
            "allow_interleaving": False,
        }
        assert all(
            signal["status"] == "ok"
            and signal["resolved_path"]
            and signal["width"] > 0
            for signal in ready_preflight["signals"]
        )

        removed_data_fields_path = tmp_path / "removed-data-fields.json"
        removed_data_fields_path.write_text(
            json.dumps({
                "streams": [{
                    "name": "removed_data_fields",
                    "signals": {
                        "clk": "stream_v1_top.clk",
                        "vld": "stream_v1_top.vo_vld",
                        "payload": "stream_v1_top.vo_data",
                    },
                    "clock": "clk",
                    "vld": "vld",
                    "data_fields": {"payload": "payload"},
                }]
            }),
            encoding="utf-8",
        )
        removed_data_fields = cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "target": target,
                "args": {"config_path": str(removed_data_fields_path), "mode": "append"},
            },
            timeout_sec=120,
        )
        assert removed_data_fields.response is not None
        assert removed_data_fields.response["ok"] is False
        assert removed_data_fields.response["error"]["code"] == "INVALID_ARGUMENT"
        assert "data_fields is not supported; use beat_fields" in removed_data_fields.response["error"]["message"]

        listed = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.list",
                "target": target,
                "args": {},
            },
            case_name="stream-v1-config-list",
            artifact_root=artifact_root,
        )
        assert listed["summary"]["count"] == len(expected)
        assert {
            row["name"] for row in listed["data"]["streams"]
        } == set(expected.keys())

        invalid_interleaving = cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "stream.config.load",
                "target": target,
                "args": {
                    "mode": "append",
                    "streams": [
                            {
                                "name": "bad_interleave_channel_valid",
                                "signals": {
                                    "clk": "stream_v1_top.clk",
                                    "vld": "stream_v1_top.ipkt_vld",
                                    "rdy": "stream_v1_top.ipkt_rdy",
                                    "sop": "stream_v1_top.ipkt_sop",
                                    "eop": "stream_v1_top.ipkt_eop",
                                    "chid": "stream_v1_top.ipkt_chid",
                                    "data": "stream_v1_top.ipkt_data",
                                },
                                "clock": "clk",
                                "vld": "vld",
                                "rdy": "rdy",
                                "sop": "sop",
                                "eop": "eop",
                                "channel_id": "chid",
                                "channel_id_valid": "sop",
                                "allow_interleaving": True,
                                "beat_fields": {"data": "data"},
                        }
                    ],
                },
            },
            timeout_sec=120,
        )
        assert invalid_interleaving.response is not None
        assert invalid_interleaving.response["ok"] is False
        invalid_error = invalid_interleaving.response["error"]
        assert invalid_error["code"] == "INVALID_ARGUMENT"
        assert invalid_error["error_layer"] == "handler"
        assert invalid_error["invalid_arg"] == "args.streams"
        assert "allow_interleaving requires channel_id_valid=every_beat" in invalid_error["message"]

        for stream_name, counts in expected.items():
            shown = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.show",
                    "target": target,
                    "args": {"stream": stream_name},
                },
                case_name="stream-v1-show-" + stream_name,
                artifact_root=artifact_root,
            )
            assert shown["summary"]["stream"] == stream_name
            assert shown["data"]["validation"]["status"] == "ok"

            validated = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.validate",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "time_range": {"begin": "0ns", "end": "250us"},
                        "line_limit": 512,
                    },
                },
                case_name="stream-v1-validate-" + stream_name,
                artifact_root=artifact_root,
            )
            assert validated["summary"]["ok"] is True

            summary = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "summary",
                    "time_range": {"begin": "0ns", "end": "250us"},
                        "line_limit": 64,
                    },
                },
                case_name="stream-v1-summary-" + stream_name,
                artifact_root=artifact_root,
            )["summary"]
            assert summary["transfer_count"] == counts["transfer_count"]
            assert summary["transfer_count"] >= 10000
            assert summary["retained_transfer_count"] == 64
            assert summary["response_truncated"] is True
            if "stall_cycles" in counts:
                assert summary["stall_cycles"] == counts["stall_cycles"]
                assert summary["stall_windows"] > 0
            if "packet_count" in counts:
                assert summary["complete_packet_count"] == counts["packet_count"]
                assert summary["partial_packet_count"] == 0
                assert summary["packet_count_status"] == "exact"
                assert summary["complete_packet_count"] > 0
            else:
                assert summary["complete_packet_count"] == 0
                assert summary["partial_packet_count"] == 0
                assert summary["packet_count_status"] == "not_configured"
            if "ready_bp_conflict_count" in counts:
                assert (
                    summary["ready_bp_conflict_count"]
                    == counts["ready_bp_conflict_count"]
                )

            first = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "first_transfer",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    },
                },
                case_name="stream-v1-first-transfer-" + stream_name,
                artifact_root=artifact_root,
            )
            assert first["data"]["row"]["transfer"] is True

            last = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "last_transfer",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    },
                },
                case_name="stream-v1-last-transfer-" + stream_name,
                artifact_root=artifact_root,
            )
            assert last["data"]["row"]["transfer"] is True
            assert last["data"]["row"]["time"] == summary["last_transfer_time"]

            window = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "transfer_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                        "line_limit": 8,
                    },
                },
                case_name="stream-v1-transfer-window-" + stream_name,
                artifact_root=artifact_root,
            )
            assert len(window["data"]["rows"]) == 8
            assert window["meta"]["truncated"] is True

        partial_packet = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "summary",
                    "time_range": {"begin": "65ns", "end": "75ns"},
                    "line_limit": 8,
                },
            },
            case_name="stream-v1-partial-packet-count",
            artifact_root=artifact_root,
        )["summary"]
        assert partial_packet["complete_packet_count"] == 0
        assert partial_packet["partial_packet_count"] == 1
        assert partial_packet["packet_count_status"] == "ambiguous"

        first_packet = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "first_packet",
                    "time_range": {"begin": "0ns", "end": "250us"},
                },
            },
            case_name="stream-v1-first-packet",
            artifact_root=artifact_root,
        )
        assert first_packet["data"]["found"] is True
        assert first_packet["data"]["packet"]["packet_index"] == 0
        assert first_packet["data"]["packet"]["packet_stable_fields"]["opcode"]["value"] == "8'ha0"
        assert first_packet["data"]["packet"]["beat_fields_preview"]["total_beats"] == 4
        assert first_packet["data"]["packet"]["beat_fields_preview"]["head"][0]["fields"]["data"]["value"] == "32'h40000000"

        packet_at = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "packet_at",
                    "packet_index": 3,
                    "time_range": {"begin": "0ns", "end": "250us"},
                },
            },
            case_name="stream-v1-packet-at",
            artifact_root=artifact_root,
        )
        assert packet_at["data"]["found"] is True
        assert packet_at["data"]["packet"]["packet_index"] == 3
        assert packet_at["data"]["packet"]["packet_stable_fields"]["opcode"]["value"] == "8'ha3"
        packet_at_xout = _query_xout(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "packet_at",
                    "packet_index": 3,
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 1,
                },
            },
            case_name="stream-v1-packet-at-xout",
            artifact_root=artifact_root,
        )
        assert "packet_stable_fields    : opcode=8'ha3" in packet_at_xout
        assert "18     185ns  0           data=32'h4000000c seq=16'h000c" in packet_at_xout
        assert "first_fields: data=32'h4000000c seq=16'h000c" in packet_at_xout
        assert "last_fields : data=32'h4000000f seq=16'h000f" in packet_at_xout
        assert "bits:" not in packet_at_xout
        assert "known: true" not in packet_at_xout

        packet_oob = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "packet_at",
                    "packet_index": 999999,
                    "time_range": {"begin": "0ns", "end": "250us"},
                },
            },
            case_name="stream-v1-packet-at-oob",
            artifact_root=artifact_root,
        )
        assert packet_oob["data"]["found"] is False
        assert packet_oob["data"]["packet"] is None

        mismatch_packet = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "bp_packet",
                    "query": "first_packet",
                    "time_range": {"begin": "0ns", "end": "250us"},
                },
            },
            case_name="stream-v1-stable-mismatch",
            artifact_root=artifact_root,
        )
        assert mismatch_packet["data"]["packet"]["packet_stable_mismatches"]
        assert mismatch_packet["summary"]["packet_stable_mismatch_count"] > 0

        stalls = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "stall_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 4,
                },
            },
            case_name="stream-v1-ready-stall-window",
            artifact_root=artifact_root,
        )
        assert stalls["data"]["stalls"]
        assert stalls["data"]["stalls"][0]["reason"] == "rdy_low"

        packets = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_bp_packet_negedge",
                    "query": "packet_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 4,
                },
            },
            case_name="stream-v1-negedge-packet-window",
            artifact_root=artifact_root,
        )
        assert len(packets["data"]["packets"]) == 4
        assert packets["summary"]["edge"] == "negedge"
        packets_xout = _query_xout(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_bp_packet_negedge",
                    "query": "packet_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 2,
                },
            },
            case_name="stream-v1-packet-window-xout",
            artifact_root=artifact_root,
        )
        assert "data=32'h60000000 seq=16'h0000" in packets_xout
        assert "data=32'h60000003 seq=16'h0003" in packets_xout
        assert "2'h0" in packets_xout
        assert "bits:" not in packets_xout

        interleaved = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "interleaved_packet",
                    "query": "packet_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 4,
                },
            },
            case_name="stream-v1-interleaved-packet-window",
            artifact_root=artifact_root,
        )
        assert len(interleaved["data"]["packets"]) == 4
        assert {packet["channel_id"]["value"] for packet in interleaved["data"]["packets"]} == {"2'h0", "2'h1"}
        assert all(packet["beat_count"] == 4 for packet in interleaved["data"]["packets"])

        match = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "transfer_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 8,
                    "filter": {"fields": {
                        "low8": {"mode": "exact", "values": ["8'h5a", "8'h5b"]},
                        "is_wr": {"mode": "range", "begin": "1'b0", "end": "1'b1"},
                        "data": {"mode": "mask", "value": "32'h0000005a", "mask": "32'h000000ff"},
                    }},
                },
            },
            case_name="stream-v1-filter-beat-fields",
            artifact_root=artifact_root,
        )
        assert match["summary"]["matched_transfer_count"] > 8
        assert match["summary"]["filter_applied"] is True
        assert match["summary"]["unresolved_filter_count"] == 0
        assert len(match["data"]["rows"]) == 8
        assert match["data"]["rows"][0]["fields"]["low8"]["value"] == "8'h5a"
        match_xout = _query_xout(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "transfer_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 2,
                    "filter": {"fields": {
                        "low8": {"mode": "exact", "values": ["8'h5a"]},
                    }},
                },
            },
            case_name="stream-v1-filter-beat-fields-xout",
            artifact_root=artifact_root,
        )
        assert "low8=8'h5a" in match_xout
        assert "data=32'h2000015a" in match_xout
        assert "channel_id" in match_xout
        assert "bits:" not in match_xout
        assert "unresolved_filter_count: 因所选 SOP/EOP 边界" in match_xout

        scalar_data_filter = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "valid_only",
                    "query": "transfer_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 2,
                    "filter": {"fields": {
                        "data": {"mode": "exact", "values": ["32'h1000005a"]},
                    }},
                },
            },
            case_name="stream-v1-filter-scalar-data",
            artifact_root=artifact_root,
        )
        assert scalar_data_filter["summary"]["matched_transfer_count"] == 1
        assert scalar_data_filter["data"]["rows"][0]["fields"]["data"]["value"] == "32'h1000005a"

        for case_name, stream_name, query, invalid_filter, invalid_arg in (
            (
                "packet-position-required", "ready_packet", "packet_window",
                {"fields": {"opcode": {"mode": "exact", "values": ["8'ha0"]}}},
                "args.filter.position",
            ),
            (
                "beat-position-forbidden", "ready_stream", "transfer_window",
                {"position": "sop", "fields": {"low8": {"mode": "exact", "values": ["8'h5a"]}}},
                "args.filter.position",
            ),
            (
                "filter-query-mismatch", "ready_stream", "stall_window",
                {"fields": {"low8": {"mode": "exact", "values": ["8'h5a"]}}},
                "args.query",
            ),
        ):
            invalid = cli_runner.run(
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": query,
                        "time_range": {"begin": "0ns", "end": "250us"},
                        "filter": invalid_filter,
                    },
                },
                timeout_sec=120,
            )
            assert invalid.response is not None and invalid.response["ok"] is False, case_name
            assert invalid.response["error"]["code"] == "INVALID_ARGUMENT"
            assert invalid.response["error"]["invalid_arg"] == invalid_arg

        packet_filter = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "packet_window",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 1,
                    "filter": {
                        "position": "sop",
                        "fields": {
                            "opcode": {"mode": "exact", "values": ["8'ha3"]},
                            "seq": {"mode": "range", "begin": "16'd12", "end": "16'd12"},
                            "data": {"mode": "mask", "value": "32'h0c", "mask": "32'hff"},
                        },
                    },
                },
            },
            case_name="stream-v1-filter-packet-sop",
            artifact_root=artifact_root,
        )
        assert packet_filter["summary"]["matched_packet_count"] == 1
        assert packet_filter["summary"]["unresolved_filter_count"] == 0
        assert packet_filter["data"]["packets"][0]["packet_index"] == 3
        assert packet_filter["data"]["packets"][0]["beat_count"] == 4

        partial_filter = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "summary",
                    "time_range": {"begin": "65ns", "end": "75ns"},
                    "filter": {
                        "position": "eop",
                        "fields": {"opcode": {"mode": "exact", "values": ["8'ha0"]}},
                    },
                },
            },
            case_name="stream-v1-filter-partial-boundary",
            artifact_root=artifact_root,
        )
        assert partial_filter["summary"]["matched_packet_count"] == 0
        assert partial_filter["summary"]["unresolved_filter_count"] == 1

        channel = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "transfer_window",
                    "channel": "3",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "line_limit": 8,
                },
            },
            case_name="stream-v1-channel-filter",
            artifact_root=artifact_root,
        )
        assert channel["data"]["rows"]
        assert all(row["channel_id"]["value"] == "2'h3" for row in channel["data"]["rows"])

        transfer_out = tmp_path / "ready_stream.tsv"
        exported = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.export",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "kind": "transfer",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "output": {"path": str(transfer_out), "file_format": "tsv"},
                },
            },
            case_name="stream-v1-export-transfer",
            artifact_root=artifact_root,
        )
        assert Path(exported["summary"]["output"]["path"]).is_file()
        assert Path(exported["summary"]["output"]["meta_path"]).is_file()
        assert exported["summary"]["row_count"] == expected["ready_stream"]["transfer_count"]

        packet_out = tmp_path / "ready_packet.tsv"
        packet_exported = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.export",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "kind": "packet",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "output": {"path": str(packet_out), "file_format": "tsv"},
                },
            },
            case_name="stream-v1-export-packet",
            artifact_root=artifact_root,
        )
        assert Path(packet_exported["summary"]["output"]["path"]).is_file()
        assert Path(packet_exported["summary"]["output"]["meta_path"]).is_file()
        assert packet_exported["summary"]["row_count"] == expected["ready_packet"]["packet_count"]

        packet_beats_out = tmp_path / "ready_packet_beats.tsv"
        packet_beats_exported = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.export",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "kind": "packet_beats",
                    "time_range": {"begin": "0ns", "end": "250us"},
                    "output": {"path": str(packet_beats_out), "file_format": "tsv"},
                },
            },
            case_name="stream-v1-export-packet-beats",
            artifact_root=artifact_root,
        )
        assert Path(packet_beats_exported["summary"]["output"]["path"]).is_file()
        assert Path(packet_beats_exported["summary"]["output"]["meta_path"]).is_file()
        assert packet_beats_exported["summary"]["row_count"] == expected["ready_packet"]["transfer_count"]
        assert "packet_index\tchannel_id\tbeat_index" in packet_beats_out.read_text(encoding="utf-8").splitlines()[0]
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "target": target,
            },
            timeout_sec=60,
        )
