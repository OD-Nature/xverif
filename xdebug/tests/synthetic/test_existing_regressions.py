from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from runner import ArtifactWriter, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    case_name: str,
    artifact_root: Path,
) -> None:
    if result.returncode == 0 and not result.timed_out:
        return
    artifact_dir = ArtifactWriter(artifact_root).write(case_name, result)
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout tail:\n%s\nstderr tail:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-4000:],
            result.stderr_raw[-4000:],
        )
    )


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.slow
def test_existing_nonaxi_waveform_regression(
    command_runner: CommandRunner,
    repo_root: Path,
    xdebug_root: Path,
    xdebug_bin: Path,
    artifact_root: Path,
    xverif_fixture: Any,
) -> None:
    resources = xverif_fixture("xdebug.ai_complex_wave")
    result = command_runner.run(
        [
            sys.executable,
            str(xdebug_root / "tests" / "waveform" / "run_complex_wave.py"),
            "--mode",
            "nonaxi",
            "--fsdb",
            str(resources / "out" / "waves.fsdb"),
            "--xdebug",
            str(xdebug_bin),
        ],
        cwd=repo_root,
        timeout_sec=1200,
        metadata={"suite": "waveform-nonaxi"},
    )
    _require_success(
        result,
        case_name="existing-waveform-nonaxi",
        artifact_root=artifact_root,
    )
    assert "PASS: xdebug complex waveform validation completed" in result.stdout_raw


@pytest.mark.synthetic
@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.slow
def test_existing_combined_active_driver_regression(
    command_runner: CommandRunner,
    repo_root: Path,
    xdebug_root: Path,
    xdebug_bin: Path,
    artifact_root: Path,
    xverif_fixture: Any,
) -> None:
    active_driver = xverif_fixture("xdebug.active_driver")
    interface_root = xverif_fixture("xdebug.interface_port_root")
    result = command_runner.run(
        [
            sys.executable,
            str(
                xdebug_root
                / "tests"
                / "combined"
                / "run_active_driver_fixture.py"
            ),
        ],
        cwd=repo_root,
        timeout_sec=1200,
        env={
            "XDEBUG": str(xdebug_bin),
            "XDEBUG_ACTIVE_DRIVER_FIXTURE_DIR": str(active_driver),
            "XDEBUG_INTERFACE_PORT_ROOT_FIXTURE_DIR": str(interface_root),
        },
        metadata={"suite": "combined-active-driver"},
    )
    _require_success(
        result,
        case_name="existing-combined-active-driver",
        artifact_root=artifact_root,
    )
    assert "failed, 0 skipped" in result.stdout_raw
