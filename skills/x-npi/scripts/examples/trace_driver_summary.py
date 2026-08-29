#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from x_npi.design import trace_driver, trace_load
from x_npi.jsonio import error, ok, print_json
from x_npi.runtime import json_stdout_quarantine, pynpi_lifecycle


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize pynpi static driver/load trace.")
    ap.add_argument("--dbdir", required=True)
    ap.add_argument("--signal", required=True)
    ap.add_argument("--mode", choices=["driver", "load"], default="driver")
    args = ap.parse_args()
    with json_stdout_quarantine() as json_stream:
        try:
            with pynpi_lifecycle([sys.argv[0], "-dbdir", args.dbdir], load_design=True):
                rows = trace_driver(args.signal) if args.mode == "driver" else trace_load(args.signal)
            print_json(ok("trace_driver_summary", {"rows": rows}, {"count": len(rows), "mode": args.mode}), json_stream)
            return 0
        except Exception as exc:
            print_json(
                error(
                    "trace_driver_summary", "FAILED", str(exc),
                    stage="runtime", dbdir=args.dbdir, signal=args.signal,
                    mode=args.mode,
                ),
                json_stream,
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
