from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CliRunner, CommandRunner, RunResult


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
    command_runner: CommandRunner,
    cli_runner: CliRunner,
    xdebug_root: Path,
    artifact_root: Path,
    tmp_path: Path,
) -> None:
    fixture_dir = xdebug_root / "testdata" / "waveform" / "stream_v1"
    config_path = fixture_dir / "config" / "streams.json"

    build = command_runner.run(
        ["make", "clean", "run"],
        cwd=fixture_dir,
        timeout_sec=1200,
        metadata={"suite": "stream_v1_real", "fixture": str(fixture_dir)},
    )
    if build.returncode != 0 or build.timed_out:
        _require_success(
            build,
            case_name="stream-v1-real-build",
            artifact_root=artifact_root,
        )

    fsdb = fixture_dir / "out" / "waves.fsdb"
    expected_path = fixture_dir / "out" / "stream_expected.json"
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
        assert loaded["data"]["summary"]["loaded"] == len(expected)

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
        assert listed["data"]["summary"]["count"] == len(expected)
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
                            "clock": "stream_v1_top.clk",
                            "vld": "stream_v1_top.ipkt_vld",
                            "rdy": "stream_v1_top.ipkt_rdy",
                            "sop": "stream_v1_top.ipkt_sop",
                            "eop": "stream_v1_top.ipkt_eop",
                            "channel_id": "stream_v1_top.ipkt_chid",
                            "channel_id_valid": "sop",
                            "allow_interleaving": True,
                            "beat_fields": {"data": "stream_v1_top.ipkt_data"},
                        }
                    ],
                },
            },
            timeout_sec=120,
        )
        assert invalid_interleaving.response is not None
        assert invalid_interleaving.response["ok"] is False
        assert "allow_interleaving requires channel_id_valid=every_beat" in invalid_interleaving.stdout_raw

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
            assert shown["data"]["summary"]["stream"] == stream_name

            validated = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.validate",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "start": "0ns",
                        "end": "250us",
                        "max_edges": 512,
                    },
                },
                case_name="stream-v1-validate-" + stream_name,
                artifact_root=artifact_root,
            )
            assert validated["data"]["summary"]["ok"] is True

            summary = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "summary",
                        "start": "0ns",
                        "end": "250us",
                        "limit": 64,
                    },
                },
                case_name="stream-v1-summary-" + stream_name,
                artifact_root=artifact_root,
            )["data"]["summary"]
            assert summary["transfer_count"] == counts["transfer_count"]
            assert summary["transfer_count"] >= 10000
            if "stall_cycles" in counts:
                assert summary["stall_cycles"] == counts["stall_cycles"]
                assert summary["stall_windows"] > 0
            if "packet_count" in counts:
                assert summary["packet_count"] == counts["packet_count"]
                assert summary["packet_count"] > 0
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
                        "start": "0ns",
                        "end": "250us",
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
                        "start": "0ns",
                        "end": "250us",
                    },
                },
                case_name="stream-v1-last-transfer-" + stream_name,
                artifact_root=artifact_root,
            )
            assert last["data"]["row"]["transfer"] is True

            window = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "stream.query",
                    "target": target,
                    "args": {
                        "stream": stream_name,
                        "query": "transfer_window",
                        "start": "0ns",
                        "end": "250us",
                        "limit": 8,
                    },
                },
                case_name="stream-v1-transfer-window-" + stream_name,
                artifact_root=artifact_root,
            )
            assert len(window["data"]["rows"]) == 8
            assert window["data"]["truncated"] is True

        first_packet = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_packet",
                    "query": "first_packet",
                    "start": "0ns",
                    "end": "250us",
                },
            },
            case_name="stream-v1-first-packet",
            artifact_root=artifact_root,
        )
        assert first_packet["data"]["found"] is True
        assert first_packet["data"]["packet"]["packet_index"] == 0
        assert first_packet["data"]["packet"]["stable_fields"]["opcode"]["value"] == "8'ha0"
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
                    "start": "0ns",
                    "end": "250us",
                },
            },
            case_name="stream-v1-packet-at",
            artifact_root=artifact_root,
        )
        assert packet_at["data"]["found"] is True
        assert packet_at["data"]["packet"]["packet_index"] == 3
        assert packet_at["data"]["packet"]["stable_fields"]["opcode"]["value"] == "8'ha3"
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
                    "start": "0ns",
                    "end": "250us",
                    "limit": 1,
                },
            },
            case_name="stream-v1-packet-at-xout",
            artifact_root=artifact_root,
        )
        assert "stable_fields: opcode=8'ha3" in packet_at_xout
        assert "fields: data=32'h4000000c seq=16'h000c" in packet_at_xout
        assert "first_fields: data=32'h4000000c seq=16'h000c" in packet_at_xout
        assert "last_fields: data=32'h4000000f seq=16'h000f" in packet_at_xout
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
                    "start": "0ns",
                    "end": "250us",
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
                    "start": "0ns",
                    "end": "250us",
                },
            },
            case_name="stream-v1-stable-mismatch",
            artifact_root=artifact_root,
        )
        assert mismatch_packet["data"]["packet"]["stable_mismatches"]
        assert mismatch_packet["data"]["summary"]["stable_mismatch_count"] > 0

        stalls = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "stall_window",
                    "start": "0ns",
                    "end": "250us",
                    "limit": 4,
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
                    "start": "0ns",
                    "end": "250us",
                    "limit": 4,
                },
            },
            case_name="stream-v1-negedge-packet-window",
            artifact_root=artifact_root,
        )
        assert len(packets["data"]["packets"]) == 4
        assert packets["data"]["summary"]["clock_edge"] == "negedge"
        packets_xout = _query_xout(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_bp_packet_negedge",
                    "query": "packet_window",
                    "start": "0ns",
                    "end": "250us",
                    "limit": 2,
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
                    "start": "0ns",
                    "end": "250us",
                    "limit": 4,
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
                    "query": "match_field",
                    "start": "0ns",
                    "end": "250us",
                    "limit": 8,
                    "match": {"field": "low8", "op": "==", "value": "8'h5a"},
                },
            },
            case_name="stream-v1-match-field",
            artifact_root=artifact_root,
        )
        assert match["data"]["summary"]["match_count"] > 0
        assert match["data"]["rows"][0]["fields"]["low8"]["value"] == "8'h5a"
        match_xout = _query_xout(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "stream.query",
                "target": target,
                "args": {
                    "stream": "ready_stream",
                    "query": "match_field",
                    "start": "0ns",
                    "end": "250us",
                    "limit": 2,
                    "match": {"field": "low8", "op": "==", "value": "8'h5a"},
                },
            },
            case_name="stream-v1-match-field-xout",
            artifact_root=artifact_root,
        )
        assert "low8=8'h5a" in match_xout
        assert "data=32'h2000015a" in match_xout
        assert "channel_id" in match_xout
        assert "bits:" not in match_xout

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
                    "start": "0ns",
                    "end": "250us",
                    "limit": 8,
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
                    "format": "tsv",
                    "start": "0ns",
                    "end": "250us",
                    "output_file": str(transfer_out),
                },
            },
            case_name="stream-v1-export-transfer",
            artifact_root=artifact_root,
        )
        assert Path(exported["data"]["output_file"]).is_file()
        assert Path(exported["data"]["meta_file"]).is_file()
        assert exported["data"]["row_count"] == expected["ready_stream"]["transfer_count"]

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
                    "format": "tsv",
                    "start": "0ns",
                    "end": "250us",
                    "output_file": str(packet_out),
                },
            },
            case_name="stream-v1-export-packet",
            artifact_root=artifact_root,
        )
        assert Path(packet_exported["data"]["output_file"]).is_file()
        assert Path(packet_exported["data"]["meta_file"]).is_file()
        assert packet_exported["data"]["row_count"] == expected["ready_packet"]["packet_count"]

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
                    "format": "tsv",
                    "start": "0ns",
                    "end": "250us",
                    "output_file": str(packet_beats_out),
                },
            },
            case_name="stream-v1-export-packet-beats",
            artifact_root=artifact_root,
        )
        assert Path(packet_beats_exported["data"]["output_file"]).is_file()
        assert Path(packet_beats_exported["data"]["meta_file"]).is_file()
        assert packet_beats_exported["data"]["row_count"] == expected["ready_packet"]["transfer_count"]
        assert "packet_index\tchannel_id\tbeat_index" in packet_beats_out.read_text(encoding="utf-8").splitlines()[0]
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "target": target,
                "args": {"session_id": session["id"]},
            },
            timeout_sec=60,
        )
