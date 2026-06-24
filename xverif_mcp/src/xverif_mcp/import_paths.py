"""Import path bootstrap for in-process xverif tool adapters."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    env_root = os.environ.get("XVERIF_HOME")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[3]


def ensure_tool_import_paths() -> None:
    root = repo_root()
    paths = [
        root / "xbit" / "src",
        root / "xentry" / "src",
        root / "xloc",
        root / "xberif",
        root / "xsva",
    ]
    for path in reversed(paths):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
