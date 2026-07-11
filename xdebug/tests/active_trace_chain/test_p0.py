import pytest

from catalog_cases import cases, run_case


@pytest.mark.parametrize("case", cases("p0"), ids=lambda item: str(item["case"]))
def test_p0(case, xverif_fixture, tmp_path) -> None:
    runner = xverif_fixture("xdebug.active_trace_runner") / "build/chain_test"
    run_case(runner, xverif_fixture("xdebug.active_trace_p0"), case, tmp_path)
