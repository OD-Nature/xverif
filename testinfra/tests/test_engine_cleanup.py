from __future__ import annotations

import os
import shutil
import subprocess

from testinfra.xverif_test.engine_cleanup import EngineProcessGuard


def test_engine_process_guard_terminates_owned_process(tmp_path) -> None:
    sleep_bin = shutil.which("sleep")
    assert sleep_bin is not None
    guard = EngineProcessGuard(tmp_path / "unused")
    guard.engine_bin = guard.engine_bin.with_name("sleep")
    guard.marker = sleep_bin
    guard.start()
    env = os.environ.copy()
    proc = subprocess.Popen([sleep_bin, "30"], env=env)
    try:
        assert proc.pid in guard.owned_pids()
        assert guard.cleanup() == set()
        proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
