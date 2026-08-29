from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from testinfra.xverif_test.catalog import Catalog
from testinfra.xverif_test.dependencies import (
    DependencyError,
    load_default_dependency_registry,
    probe_dependencies,
    validate_suite_dependencies,
)
from testinfra.xverif_test.fixtures import load_default_registry


ROOT = Path(__file__).resolve().parents[2]


def test_dependency_registry_is_schema_valid_and_unique() -> None:
    payload = json.loads((ROOT / "testinfra/dependencies.v1.json").read_text())
    schema = json.loads(
        (ROOT / "testinfra/schemas/dependencies.v1.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(payload)
    registry = load_default_dependency_registry(ROOT)
    assert len(registry.definitions) == len(payload["dependencies"])


def test_catalog_and_fixture_dependencies_are_registered() -> None:
    registry = load_default_dependency_registry(ROOT)
    catalog = Catalog.load(
        ROOT / "testinfra/catalog.v1.yaml",
        ROOT / "testinfra/schemas/catalog.v1.schema.json",
    )
    validate_suite_dependencies(catalog, registry)
    fixtures = load_default_registry(ROOT)
    registry.require_known(
        name for fixture in fixtures.fixtures for name in fixture.build_capabilities
    )


def test_unknown_dependency_is_a_contract_error() -> None:
    with pytest.raises(DependencyError, match="unknown dependencies"):
        probe_dependencies(["not_registered"], ROOT)


def test_neovim_dependency_uses_path_and_gives_local_hint(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    status = probe_dependencies(["neovim"], ROOT)["neovim"]
    assert status.available is False
    assert "nvim" in status.reason


def test_npi_requires_license_configuration(tmp_path: Path, monkeypatch) -> None:
    verdi = tmp_path / "verdi/share/NPI/lib/LINUX64"
    verdi.mkdir(parents=True)
    monkeypatch.setenv("VERDI_HOME", str(tmp_path / "verdi"))
    monkeypatch.delenv("SNPSLMD_LICENSE_FILE", raising=False)
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)
    missing = probe_dependencies(["npi"], ROOT)["npi"]
    assert missing.available is False
    assert "unset" in missing.reason
    monkeypatch.setenv("SNPSLMD_LICENSE_FILE", "27000@license-host")
    available = probe_dependencies(["npi"], ROOT)["npi"]
    assert available.available is True
    assert "redacted" in available.reason
