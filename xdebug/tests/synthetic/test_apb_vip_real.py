from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CliRunner, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    case_name: str,
    artifact_root: Path,
    manifest: dict[str, Any],
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
        manifest=manifest,
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
    manifest: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = cli_runner.run(request, timeout_sec=120)
    return _require_success(
        result,
        case_name=case_name,
        artifact_root=artifact_root,
        manifest=manifest,
        extra=extra,
    )


def _resources_ready(fixture_dir: Path, manifest: dict[str, Any]) -> bool:
    resources = manifest["resources"]
    fsdb = fixture_dir / resources["fsdb"]
    daidir = fixture_dir / resources["daidir"]
    sim_log = fixture_dir / resources["simulation_log"]
    return (
        fsdb.is_file()
        and fsdb.stat().st_size > 0
        and daidir.is_dir()
        and sim_log.is_file()
    )


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.apb
@pytest.mark.vip
@pytest.mark.regression
@pytest.mark.slow
def test_apb_vip_real_wait_state_and_error_actions(
    command_runner: CommandRunner,
    cli_runner: CliRunner,
    xdebug_root: Path,
    artifact_root: Path,
) -> None:
    fixture_dir = xdebug_root / "testdata" / "waveform" / "apb_vip_real"
    manifest = json.loads(
        (fixture_dir / "manifest.json").read_text(encoding="utf-8")
    )
    if not _resources_ready(fixture_dir, manifest):
        missing = [
            name for name in manifest["required_env"] if not os.environ.get(name)
        ]
        assert not missing, (
            "APB VIP fixture requires environment variables: %s"
            % ", ".join(missing)
        )

        build = command_runner.run(
            ["make", "clean", "run"],
            cwd=fixture_dir,
            timeout_sec=1200,
            metadata={
                "suite": "apb_vip_real",
                "fixture": str(fixture_dir),
                "seed": manifest["seed"],
            },
        )
        if build.returncode != 0 or build.timed_out:
            _require_success(
                build,
                case_name="apb-vip-real-build",
                artifact_root=artifact_root,
                manifest=manifest,
            )

    resources = manifest["resources"]
    fsdb = fixture_dir / resources["fsdb"]
    daidir = fixture_dir / resources["daidir"]
    sim_log = fixture_dir / resources["simulation_log"]
    assert fsdb.is_file() and fsdb.stat().st_size > 0
    assert daidir.is_dir()
    log_text = sim_log.read_text(encoding="utf-8", errors="replace")
    assert "UVM_ERROR :    0" in log_text
    assert "UVM_FATAL :    0" in log_text
    assert "APB VIP fixture completed: writes=5 reads=5 errors=1" in log_text

    open_response = _query(
        cli_runner,
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": {"fsdb": str(fsdb)},
            "args": {"name": "apb_vip_real"},
        },
        case_name="apb-vip-session-open",
        artifact_root=artifact_root,
        manifest=manifest,
    )
    session = open_response.get("session") or open_response["data"]["session"]
    session_id = session["id"]
    target = {"session_id": session_id}
    prefix = manifest["interface"]
    config = {
        "paddr": prefix + ".paddr",
        "pwdata": prefix + ".pwdata",
        "prdata": prefix + ".prdata[0]",
        "pwrite": prefix + ".pwrite",
        "penable": prefix + ".penable",
        "psel": prefix + ".psel[0]",
        "pready": prefix + ".pready[0]",
        "pslverr": prefix + ".pslverr[0]",
        "clock": manifest["top"] + ".clk",
        "rst_n": manifest["top"] + ".rst_n",
        "edge": "posedge",
    }

    try:
        loaded = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "apb.config.load",
                "target": target,
                "args": {"name": "apb0", "config": config},
            },
            case_name="apb-vip-config-load",
            artifact_root=artifact_root,
            manifest=manifest,
        )
        assert loaded["data"]["config"]["pready"] == config["pready"]
        assert loaded["data"]["config"]["pslverr"] == config["pslverr"]

        listed = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "apb.config.list",
                "target": target,
                "args": {"name": "apb0"},
            },
            case_name="apb-vip-config-list",
            artifact_root=artifact_root,
            manifest=manifest,
        )
        assert listed["data"]["pready"] == config["pready"]
        assert listed["data"]["pslverr"] == config["pslverr"]

        for direction, expected_count in (("wr", 5), ("rd", 5)):
            queried = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "apb.query",
                    "target": target,
                    "args": {"name": "apb0", "direction": direction},
                },
                case_name="apb-vip-query-" + direction,
                artifact_root=artifact_root,
                manifest=manifest,
                extra={"apb_config": config, "simulation_log": log_text},
            )
            assert queried["summary"]["count"] == expected_count

        error_txn = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "apb.query",
                "target": target,
                "args": {
                    "name": "apb0",
                    "direction": "read",
                    "address": "'hf0",
                },
            },
            case_name="apb-vip-error-response",
            artifact_root=artifact_root,
            manifest=manifest,
            extra={"apb_config": config},
        )
        assert error_txn["data"]["transaction"]["has_error"] is True

        window = _query(
            cli_runner,
            {
                "api_version": "xdebug.v1",
                "action": "apb.transfer_window",
                "target": target,
                "args": {
                    "name": "apb0",
                    "time_range": {"begin": "0ns", "end": "1us"},
                    "line_limit": 20,
                },
            },
            case_name="apb-vip-transfer-window",
            artifact_root=artifact_root,
            manifest=manifest,
            extra={"apb_config": config},
        )
        assert window["summary"]["transaction_count"] == 10
        assert sum(
            1
            for transaction in window["data"]["transactions"]
            if transaction["has_error"]
        ) == 1

        for op in ("begin", "next", "last"):
            cursor = _query(
                cli_runner,
                {
                    "api_version": "xdebug.v1",
                    "action": "apb.cursor",
                    "target": target,
                    "args": {
                        "name": "apb0",
                        "op": op,
                        "direction": "all",
                    },
                },
                case_name="apb-vip-cursor-" + op,
                artifact_root=artifact_root,
                manifest=manifest,
            )
            assert cursor["summary"]["found"] is True
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "target": {"session_id": session_id},
            },
            timeout_sec=60,
        )
