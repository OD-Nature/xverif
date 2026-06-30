#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from x_npi.jsonio import error, ok, print_json
from x_npi.protocol import stream_summary
from x_npi.runtime import pynpi_lifecycle
from x_npi.wave import close_fsdb, edge_samples, open_fsdb, time_in


def _normalize_config(cfg: dict) -> dict:
    normalized = dict(cfg)
    aliases = {
        "clock": ("clk",),
        "valid": ("vld",),
        "ready": ("rdy",),
    }
    for canonical, alternatives in aliases.items():
        if normalized.get(canonical):
            continue
        for alternative in alternatives:
            if normalized.get(alternative):
                normalized[canonical] = normalized[alternative]
                break
    return normalized


def _is_posedge(cfg: dict) -> bool:
    edge = str(cfg.get("edge", cfg.get("clock_edge", ""))).lower()
    if edge in {"posedge", "pos", "rising"}:
        return True
    if edge in {"negedge", "neg", "falling"}:
        return False
    return bool(cfg.get("posedge", False))


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract valid/ready stream summary from FSDB.")
    ap.add_argument("--fsdb", required=True)
    ap.add_argument("--config", required=True, help="JSON with clock/valid/ready/data/fields")
    ap.add_argument("--begin")
    ap.add_argument("--end")
    ap.add_argument("--max-edges", type=int, default=300000)
    args = ap.parse_args()
    cfg = _normalize_config(json.loads(Path(args.config).read_text()))
    try:
        with pynpi_lifecycle([sys.argv[0]]):
            fp = open_fsdb(args.fsdb)
            try:
                begin = time_in(fp, args.begin) if args.begin else None
                end = time_in(fp, args.end) if args.end else None
                signals = [cfg[k] for k in ("valid", "ready", "data", "sop", "eop") if cfg.get(k)]
                signals.extend(cfg.get("fields", {}).values())
                rows = edge_samples(fp, cfg["clock"], signals, begin, end, _is_posedge(cfg), args.max_edges)
                result = stream_summary(rows, cfg)
            finally:
                close_fsdb(fp)
        print_json(ok("stream_summary", result, result["summary"]))
        return 0
    except Exception as exc:
        print_json(error("stream_summary", "FAILED", str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
