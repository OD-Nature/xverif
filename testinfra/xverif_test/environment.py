from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    available: bool
    reason: str


def probe_capabilities(names: Iterable[str], repo_root: Path) -> dict[str, CapabilityStatus]:
    return {name: _probe(name, repo_root) for name in sorted(set(names))}


def write_snapshot(path: Path, statuses: dict[str, CapabilityStatus]) -> None:
    execution_environment = os.environ.get("XVERIF_TEST_EXECUTION_ENV", "sandbox")
    if execution_environment not in {"host", "sandbox"}:
        raise ValueError(
            "XVERIF_TEST_EXECUTION_ENV must be 'host' or 'sandbox', got: "
            + execution_environment
        )
    payload = {
        "schema_version": "xverif-environment-snapshot.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "execution_environment": execution_environment,
        "capabilities": [asdict(statuses[name]) for name in sorted(statuses)],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _probe(name: str, repo_root: Path) -> CapabilityStatus:
    if name in {"fsdb", "daidir"}:
        return CapabilityStatus(name, True, "validated by the declared fixture")
    if name == "child_process":
        return _which(name, "python3")
    if name == "vim":
        return _which(name, "vim")
    if name == "uds":
        return CapabilityStatus(name, hasattr(socket, "AF_UNIX"), "AF_UNIX support")
    if name == "mcp_process":
        available = importlib.util.find_spec("mcp") is not None
        return CapabilityStatus(name, available, "Python mcp package import")
    if name == "fake_lsf":
        return CapabilityStatus(name, True, "repository fake LSF backend")
    if name == "real_lsf":
        enabled = os.environ.get("XDEBUG_ENABLE_REAL_LSF") == "1"
        commands = all(shutil.which(command) for command in ("bsub", "bjobs", "bkill"))
        return CapabilityStatus(
            name,
            enabled and commands,
            "XDEBUG_ENABLE_REAL_LSF=1 and bsub/bjobs/bkill available",
        )
    if name == "npi":
        home = Path(os.path.expanduser(os.environ.get("VERDI_HOME", "")))
        candidates = (
            home / "share/NPI/lib/LINUX64",
            home / "share/NPI/lib/linux64",
        )
        available = bool(str(home)) and any(path.is_dir() for path in candidates)
        return CapabilityStatus(name, available, "VERDI_HOME NPI runtime directory")
    if name == "external_realdata":
        manifests = repo_root / "xdebug/tests/realdata/manifests"
        available = False
        for path in sorted(manifests.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            resources = [raw.get(key) for key in ("fsdb", "daidir") if raw.get(key)]
            if resources and all(Path(os.path.expanduser(str(value))).exists() for value in resources):
                available = True
                break
        return CapabilityStatus(name, available, "at least one complete realdata manifest")
    return CapabilityStatus(name, False, "capability has no registered probe")


def _which(name: str, command: str) -> CapabilityStatus:
    return CapabilityStatus(name, shutil.which(command) is not None, f"{command} executable")
