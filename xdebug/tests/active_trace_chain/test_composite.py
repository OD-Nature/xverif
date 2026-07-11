import pytest

from catalog_cases import cases, run_case


@pytest.mark.parametrize("case", cases("composite"), ids=lambda item: str(item["case"]))
def test_composite(case, xverif_fixture, tmp_path) -> None:
    runner = xverif_fixture("xdebug.active_trace_runner") / "build/chain_test"
    run_case(runner, xverif_fixture("xdebug.active_trace_composite"), case, tmp_path)
