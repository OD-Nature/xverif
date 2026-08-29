from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    artifact_root: Path,
    manifest: dict,
) -> None:
    if result.returncode == 0 and not result.timed_out:
        return
    artifact_dir = ArtifactWriter(artifact_root).write(
        "axi-vip-real",
        result,
        manifest=manifest,
    )
    pytest.fail(
        "AXI VIP regression failed rc=%s timeout=%s; artifacts=%s\n"
        "stdout tail:\n%s\nstderr tail:\n%s"
        % (
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


def _resources_ready(fixture_dir: Path, manifest: dict) -> bool:
    resources = manifest["resources"]
    fsdb = fixture_dir / resources["fsdb"]
    daidir = fixture_dir / resources["daidir"]
    sim_log = fixture_dir / resources["simulation_log"]
    handshake_oracle = fixture_dir / resources["handshake_oracle"]
    return (
        fsdb.is_file()
        and fsdb.stat().st_size > 0
        and daidir.is_dir()
        and sim_log.is_file()
        and handshake_oracle.is_file()
        and handshake_oracle.stat().st_size > 0
    )


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.axi
@pytest.mark.vip
@pytest.mark.regression
@pytest.mark.slow
def test_axi_vip_real_waveform_actions(
    command_runner: CommandRunner,
    repo_root: Path,
    xdebug_root: Path,
    xdebug_bin: Path,
    artifact_root: Path,
    xverif_fixture: Any,
) -> None:
    fixture_dir = xdebug_root / "testdata" / "waveform" / "axi_vip_real"
    resources_root = xverif_fixture("xdebug.axi_vip")
    manifest = json.loads(
        (fixture_dir / "manifest.json").read_text(encoding="utf-8")
    )
    results = []
    for run in manifest["runs"]:
        expected_count = run["num_ids"] * run["transactions_per_id"]
        command = [
            sys.executable,
            str(xdebug_root / "tests" / "waveform" / "run_complex_wave.py"),
            "--mode", "axi",
            "--xdebug", str(xdebug_bin),
            "--axi-fsdb", str(resources_root / run["fsdb"]),
            "--axi-sim-log", str(resources_root / run["simulation_log"]),
            "--axi-handshake-oracle", str(resources_root / run["handshake_oracle"]),
            "--axi-expected-count", str(expected_count),
            "--axi-num-ids", str(run["num_ids"]),
            "--axi-transactions-per-id", str(run["transactions_per_id"]),
            "--axi-min-random-delay", str(run["min_random_delay"]),
            "--axi-max-random-delay", str(run["max_random_delay"]),
        ]
        result = command_runner.run(
            command,
            cwd=repo_root,
            env={"XDEBUG_AXI_FIXTURE_DIR": str(resources_root)},
            timeout_sec=2400,
            metadata={
                "suite": "axi-vip-real",
                "run": run["name"],
                "fixture": str(fixture_dir),
                "seed": run["seed"],
            },
        )
        _require_success(result, artifact_root=artifact_root, manifest=manifest)
        results.append(result)

    resources = manifest["resources"]
    fsdb = resources_root / resources["fsdb"]
    daidir = resources_root / resources["daidir"]
    sim_log = resources_root / resources["simulation_log"]
    handshake_oracle = resources_root / resources["handshake_oracle"]
    assert fsdb.is_file() and fsdb.stat().st_size > 0
    assert daidir.is_dir()
    assert sim_log.is_file()
    assert handshake_oracle.is_file() and handshake_oracle.stat().st_size > 0

    log_text = sim_log.read_text(encoding="utf-8", errors="replace")
    assert "UVM_ERROR :    0" in log_text
    assert "UVM_FATAL :    0" in log_text
    assert "Master WRITE transactions: 3200" in log_text
    assert "Master READ transactions:  3200" in log_text
    assert "AXI_EXPECTED_TXN_JSON" in log_text
    assert "AXI_DELAY_PROFILE_JSON" in log_text
    assert "AXI_RESPONSE_DELAY_JSON" in log_text
    assert log_text.count("AXI_DELAY_PROFILE_JSON ") == 3200
    assert "TEST PASSED - All data comparisons OK" in log_text
    assert all("PASS: xdebug complex waveform validation completed" in item.stdout_raw
               for item in results)
