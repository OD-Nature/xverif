import pytest

from catalog_cases import cases, run_case


@pytest.mark.parametrize(
    "case", cases("phase5"), ids=lambda item: f"{item['signal']}@{item['time']}"
)
def test_phase5(case, xverif_fixture, tmp_path) -> None:
    runner = xverif_fixture("xdebug.active_trace_runner") / "build/chain_test"
    run_case(runner, xverif_fixture("xdebug.active_trace_phase5"), case, tmp_path)
