#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from x_npi.jsonio import error, ok, print_json
from x_npi.protocol import apb_summary
from x_npi.runtime import pynpi_lifecycle
from x_npi.wave import close_fsdb, edge_samples, open_fsdb, time_in

SIGNAL_KEYS = (
    "rst_n",
    "psel",
    "penable",
    "pwrite",
    "paddr",
    "pwdata",
    "prdata",
    "pready",
    "pslverr",
)


def _is_posedge(cfg: dict) -> bool:
    edge = str(cfg.get("edge", cfg.get("clock_edge", ""))).lower()
    if edge in {"posedge", "pos", "rising"}:
        return True
    if edge in {"negedge", "neg", "falling"}:
        return False
    return bool(cfg.get("posedge", False))


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract APB transaction summary from FSDB.")
    ap.add_argument("--fsdb", required=True)
    ap.add_argument("--config", required=True, help="JSON with clk/rst_n/psel/penable/pwrite/paddr/pwdata/prdata")
    ap.add_argument("--begin")
    ap.add_argument("--end")
    ap.add_argument("--max-edges", type=int, default=200000)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    try:
        with pynpi_lifecycle([sys.argv[0]]):
            fp = open_fsdb(args.fsdb)
            try:
                begin = time_in(fp, args.begin) if args.begin else None
                end = time_in(fp, args.end) if args.end else None
                signals = [cfg[k] for k in SIGNAL_KEYS if cfg.get(k)]
                rows = edge_samples(fp, cfg["clk"], signals, begin, end, _is_posedge(cfg), args.max_edges)
                result = apb_summary(rows, cfg)
            finally:
                close_fsdb(fp)
        print_json(ok("apb_summary", result, result["summary"]))
        return 0
    except Exception as exc:
        print_json(error("apb_summary", "FAILED", str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
