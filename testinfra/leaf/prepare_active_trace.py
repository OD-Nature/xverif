#!/usr/bin/env python3
"""Build one active-trace fixture group into a staging resource directory."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


GROUP_PATTERNS = {
    "p0": "p0_composability/p0_*",
    "composite": "composite/case_*",
    "timing": "timing/case_*",
    "phase4": "phase4/case_*",
    "phase5": "phase5",
}


def source_files(root: Path, group: str, case: Path) -> list[Path]:
    if group == "composite":
        return [case / "tb.sv", root / "composite/chain_dut.sv"]
    if group == "timing":
        return [case / "tb.sv", root / "timing/timing_boundary_dut.sv"]
    if group == "phase4":
        return [
            case / "tb.sv",
            root / "phase4/phase4_dut.sv",
            root / "composite/chain_dut.sv",
        ]
    if group == "phase5":
        return [case / "dut.sv", case / "tb.sv"]
    return [case / "tb.sv"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=sorted(GROUP_PATTERNS), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    args = parser.parse_args()

    root = args.source.resolve()
    resources = args.resources.resolve()
    pattern = GROUP_PATTERNS[args.group]
    cases = sorted(path for path in root.glob(pattern) if (path / "tb.sv").is_file())
    if not cases:
        raise SystemExit(f"no active-trace cases for group {args.group}")

    for case in cases:
        output = resources / "cases" / case.name / "out"
        output.mkdir(parents=True, exist_ok=True)
        compile_log = output / "compile.log"
        run_log = output / "run.log"
        argv = [
            "vcs",
            "-full64",
            "-sverilog",
            "-timescale=1ns/1ps",
            "-debug_access+all",
            "-kdb",
            "-lca",
            *(str(path.resolve()) for path in source_files(root, args.group, case)),
            "-top",
            "top",
            "-o",
            str(output / "simv"),
            "-l",
            str(compile_log),
        ]
        subprocess.run(argv, cwd=output, check=True, env=os.environ.copy())
        subprocess.run(
            [
                str(output / "simv"),
                "+fsdb+force",
                "+fsdb+autoflush",
                "+fsdbfile+waves.fsdb",
                "-ucli",
                "-ucli2Proc",
                "-do",
                str((case / "wave.tcl").resolve()),
                "-l",
                str(run_log),
            ],
            cwd=output,
            check=True,
            env=os.environ.copy(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
