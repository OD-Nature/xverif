#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the repository-local xverif Miniconda environment")
    parser.add_argument("--prefix", type=Path, default=ROOT / ".conda-xverif")
    args = parser.parse_args()
    conda = shutil.which("conda")
    if conda is None:
        parser.error("conda is not available in PATH; install/activate Miniconda first")
    prefix = args.prefix.resolve()
    python = prefix / "bin/python"
    ready = False
    if python.is_file():
        probe = subprocess.run(
            [str(python), "-c", "import pip,sys; raise SystemExit(sys.version_info < (3,11))"],
            cwd=ROOT,
            check=False,
        )
        ready = probe.returncode == 0
    if not ready:
        operation = "install" if (prefix / "conda-meta").is_dir() else "create"
        subprocess.run([conda, operation, "--yes", "--prefix", str(prefix), "python>=3.11", "pip"], cwd=ROOT, check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-test.txt")], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / "tools/check_test_environment.py"), "--python-only"], cwd=ROOT, check=True)
    print(f"xverif Python environment is ready: {prefix}")
    print(f"activate with: conda activate {prefix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
