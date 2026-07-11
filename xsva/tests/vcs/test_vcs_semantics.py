from pathlib import Path

import pytest


CASES = ("overlap_nonoverlap", "ranged_delay", "rose_fell", "simple_impl")


@pytest.mark.parametrize("case", CASES)
def test_vcs_assertion_run_completed(case: str, xverif_fixture) -> None:
    root = xverif_fixture("xsva.vcs") / "out" / case
    log = (root / "sim.log").read_text(encoding="utf-8", errors="replace")
    assert "$finish" in log
    assert "Fatal:" not in log
    assert "Error-" not in log
    assert (root / "waves.fsdb").stat().st_size > 1024
