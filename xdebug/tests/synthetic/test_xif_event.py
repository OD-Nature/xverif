from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_xif_event_queries_published_fsdb(xverif_fixture) -> None:
    resources = xverif_fixture("xdebug.xif_event")
    script = ROOT / "testdata/waveform/xif_agent_event/scripts/check_event_waves.py"
    fsdb = resources / "out/waves/xif_event_multi_if_test.fsdb"
    result = subprocess.run(
        ["python3", str(script), "--xdebug", str(ROOT / "xdebug"), "--fsdb", str(fsdb)],
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: xdebug event direct struct checks" in result.stdout
