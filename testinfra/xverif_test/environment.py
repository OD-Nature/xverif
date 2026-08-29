from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .dependencies import DependencyStatus, probe_dependencies


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    available: bool
    reason: str


def probe_capabilities(names: Iterable[str], repo_root: Path) -> dict[str, CapabilityStatus]:
    return {
        name: CapabilityStatus(status.name, status.available, status.reason)
        for name, status in probe_dependencies(names, repo_root).items()
    }


def write_snapshot(path: Path, statuses: dict[str, CapabilityStatus | DependencyStatus]) -> None:
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
        "capabilities": [
            {
                "name": statuses[name].name,
                "available": statuses[name].available,
                "reason": statuses[name].reason,
            }
            for name in sorted(statuses)
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
