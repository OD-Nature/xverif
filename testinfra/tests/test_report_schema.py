import json
from types import SimpleNamespace
from pathlib import Path

import jsonschema

from testinfra.xverif_test.reports import ResultManager


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_execution_report_matches_schema() -> None:
    schema = json.loads(
        (ROOT / "testinfra/schemas/execution-report.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    report = {
        "schema_version": "xverif-execution-report.v1",
        "gate": "fast",
        "catalog_version": "xverif-test-catalog.v1",
        "exitstatus": 0,
        "counts": {"passed": 1},
        "items": [
            {
                "nodeid": "testinfra/tests/test_catalog.py::test_catalog_loads",
                "suite_id": "testinfra.unit",
                "phase": "call",
                "outcome": "passed",
                "duration_sec": 0.01,
                "error_layer": None,
            }
        ],
    }
    jsonschema.Draft202012Validator(schema).validate(report)


def test_setup_skip_is_counted_in_json_report(tmp_path: Path) -> None:
    manager = ResultManager(tmp_path, "nightly", "xverif-test-catalog.v1")
    report = SimpleNamespace(
        when="setup",
        user_properties=[("xverif_suite", "optional.demo")],
        skipped=True,
        passed=False,
        failed=False,
        nodeid="::suite::optional.demo",
        outcome="skipped",
        duration=0.01,
        capstdout="",
        capstderr="",
        longrepr=None,
    )
    manager.record_report(report)
    manager.finish(0)
    payload = json.loads((manager.run_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["counts"] == {"skipped": 1}
    assert payload["items"][0]["phase"] == "setup"
