import pytest

from catalog_cases import cases, run_case


@pytest.mark.parametrize("case", cases("timing"), ids=lambda item: str(item["case"]))
def test_timing(case, xverif_fixture, tmp_path) -> None:
    runner = xverif_fixture("xdebug.active_trace_runner") / "build/chain_test"
    result = run_case(runner, xverif_fixture("xdebug.active_trace_timing"), case, tmp_path)
    assert result["total_hops"] == 1
    assert result["temporal_boundaries"] == 1
