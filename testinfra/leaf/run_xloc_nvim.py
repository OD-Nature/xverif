#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "xloc"
    with tempfile.TemporaryDirectory(prefix="xloc-nvim-") as temporary:
        env = os.environ.copy()
        env["XLOC_NVIM_PLUGIN"] = str(root / "nvim")
        env["XLOC_NVIM_TMP"] = temporary
        return subprocess.run(
            ["nvim", "--headless", "-u", "NONE", "-n", "-l", "nvim/checks/xloc_smoke.lua"],
            cwd=root,
            env=env,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
