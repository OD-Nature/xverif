from __future__ import annotations

import importlib.util
from pathlib import Path


XDEBUG = Path(__file__).resolve().parents[2]


def _module(name: str):
    path = XDEBUG / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"xdebug_static_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_files() -> None:
    assert _module("validate_schema").main(["validate_schema", str(XDEBUG / "schemas/v1")]) == 0


def test_examples_match_action_schemas() -> None:
    assert _module("validate_examples").main(
        ["validate_examples", str(XDEBUG / "examples"), str(XDEBUG / "schemas/v1")]
    ) == 0


def test_clock_sampling_is_consolidated() -> None:
    assert _module("check_clock_sampling_consolidation").main() == 0


def test_error_contract_is_consolidated() -> None:
    assert _module("check_error_contract_consolidation").main() == 0


def test_response_contract_is_consolidated() -> None:
    assert _module("check_response_contract_consolidation").main() == 0


def test_action_schema_coverage_is_complete() -> None:
    assert _module("audit_action_schema_coverage").main(
        ["audit_action_schema_coverage", str(XDEBUG)]
    ) == 0
