import json
from pathlib import Path

import jsonschema
import pytest

from testinfra.xverif_test.dependencies import DependencyError
from testinfra.xverif_test.environment import probe_capabilities, write_snapshot


ROOT = Path(__file__).resolve().parents[2]


def test_environment_snapshot_is_schema_valid(tmp_path: Path) -> None:
    statuses = probe_capabilities(["child_process", "uds"], ROOT)
    path = tmp_path / "environment.json"
    write_snapshot(path, statuses)
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "testinfra/schemas/environment-snapshot.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(payload)
    with pytest.raises(DependencyError, match="unknown dependencies"):
        probe_capabilities(["unknown-test-capability"], ROOT)


def test_environment_snapshot_uses_only_explicit_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setenv("XVERIF_TEST_EXECUTION_ENV", "host")
    path = tmp_path / "environment.json"
    write_snapshot(path, {})
    assert json.loads(path.read_text(encoding="utf-8"))["execution_environment"] == "host"

    monkeypatch.setenv("XVERIF_TEST_EXECUTION_ENV", "invalid")
    try:
        write_snapshot(path, {})
    except ValueError as exc:
        assert "must be 'host' or 'sandbox'" in str(exc)
    else:
        raise AssertionError("invalid execution environment was accepted")
