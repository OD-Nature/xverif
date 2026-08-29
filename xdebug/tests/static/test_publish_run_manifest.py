from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


XDEBUG = Path(__file__).resolve().parents[2]


def _module():
    path = XDEBUG / "tools" / "publish_run_manifest.py"
    spec = importlib.util.spec_from_file_location("publish_run_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_manifest_has_relative_resource_and_file_digest(tmp_path, monkeypatch) -> None:
    tool = _module()
    fsdb = tmp_path / "waves.fsdb"
    output = tmp_path / "out" / "run-manifest.json"
    fsdb.write_bytes(b"fsdb-fixture")
    monkeypatch.setattr("sys.argv", ["publish_run_manifest.py", "--fsdb", str(fsdb),
                                      "--output", str(output)])

    assert tool.main() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "xdebug.run-manifest.v1"
    assert payload["state"] == "published"
    assert payload["resources"]["fsdb"]["path"] == "../waves.fsdb"
    assert payload["resources"]["fsdb"]["sha256"] == tool.digest(fsdb)


def test_publish_manifest_rejects_missing_resource(tmp_path, monkeypatch) -> None:
    tool = _module()
    output = tmp_path / "run-manifest.json"
    monkeypatch.setattr("sys.argv", ["publish_run_manifest.py", "--fsdb", str(tmp_path / "missing.fsdb"),
                                      "--output", str(output)])

    with pytest.raises(SystemExit) as raised:
        tool.main()
    assert raised.value.code == 2
    assert not output.exists()
