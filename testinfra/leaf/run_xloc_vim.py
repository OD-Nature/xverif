#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "xloc"
    with tempfile.TemporaryDirectory(prefix="xloc-vim-") as temporary:
        env = os.environ.copy()
        env["XLOC_VIM_PLUGIN"] = str(root / "vim/plugin/xloc.vim")
        env["XLOC_VIM_TMP"] = temporary
        return subprocess.run(
            ["vim", "-Nu", "NONE", "-n", "-es", "-S", "vim/checks/xloc_smoke.vim"],
            cwd=root,
            env=env,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
