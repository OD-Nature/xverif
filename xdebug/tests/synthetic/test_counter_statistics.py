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
def test_counter_statistics_targeted_waveform(
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
            str(xdebug_root / "tests" / "waveform" / "run_counter_statistics.py"),
            "--xdebug",
            str(xdebug_bin),
            "--fsdb",
            str(resources / "out" / "waves.fsdb"),
        ],
        cwd=repo_root,
        timeout_sec=1200,
        metadata={"suite": "counter-statistics"},
    )
    _require_success(
        result,
        case_name="counter-statistics-targeted",
        artifact_root=artifact_root,
    )
    assert "PASS: xdebug counter.statistics validation completed" in result.stdout_raw
