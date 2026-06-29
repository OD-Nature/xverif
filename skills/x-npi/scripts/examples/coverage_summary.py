#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from x_npi.coverage import close_covdb, coverage_items, coverage_summary, merged_test_handle, open_covdb, test_names
from x_npi.jsonio import error, ok, print_json, split_limited
from x_npi.runtime import pynpi_lifecycle


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize VCS/Verdi coverage database with pynpi.cov.")
    ap.add_argument("--vdb", required=True, help="Path to simv.vdb or merged.vdb")
    ap.add_argument("--metric", action="append",
                    choices=["line", "toggle", "branch", "condition", "fsm", "assert", "functional"],
                    help="Metric to include. Defaults to all supported metrics.")
    ap.add_argument("--scope", help="Optional scope/full_name prefix filter")
    ap.add_argument("--holes-only", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    try:
        with pynpi_lifecycle([sys.argv[0]]):
            db = open_covdb(args.vdb)
            try:
                test = merged_test_handle(db)
                rows = coverage_items(db, test=test, metrics=args.metric, scope=args.scope,
                                      holes_only=args.holes_only)
                shown, truncated = split_limited(rows, args.limit)
                summary = coverage_summary(rows)
                summary.update({
                    "tests": test_names(db),
                    "row_count": len(rows),
                    "returned": len(shown),
                    "truncated": truncated,
                    "holes_only": args.holes_only,
                })
            finally:
                close_covdb(db)
        print_json(ok("coverage_summary", {"items": shown}, summary))
        return 0
    except Exception as exc:
        print_json(error("coverage_summary", "FAILED", str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
