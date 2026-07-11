from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_semantics.sh")


def test_design_semantics_uses_published_databases(xverif_fixture) -> None:
    uart = xverif_fixture("xdebug.design_uart") / "simv.daidir"
    p3 = xverif_fixture("xdebug.design_p3") / "simv.daidir"
    env = os.environ.copy()
    env["UART_DB"] = str(uart)
    env["P3_DB"] = str(p3)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "xdebug design semantics regression passed" in result.stdout
