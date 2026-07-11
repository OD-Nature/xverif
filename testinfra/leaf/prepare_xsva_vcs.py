#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.resources.resolve() / "out"
    for case_dir in sorted((source / "cases").iterdir()):
        if not case_dir.is_dir():
            continue
        common = ["make", "-C", str(source), f"CASE={case_dir.name}", f"OUTPUT_ROOT={output}"]
        subprocess.run([*common, "cmp"], check=True)
        subprocess.run([*common, "run"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
