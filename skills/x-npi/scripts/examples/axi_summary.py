#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from x_npi.cli import emit_result, error_document, require_output, sampling_contract
from x_npi.jsonio import print_json
from x_npi.protocol import axi_summary
from x_npi.runtime import json_stdout_quarantine, pynpi_lifecycle
from x_npi.wave import close_fsdb, iter_edge_samples, open_fsdb, time_in

SIGNAL_KEYS = (
    "rst_n", "awid", "awaddr", "awlen", "awsize", "awburst", "awvalid", "awready",
    "wdata", "wstrb", "wlast", "wvalid", "wready", "bid", "bresp", "bvalid", "bready",
    "arid", "araddr", "arlen", "arsize", "arburst", "arvalid", "arready",
    "rid", "rdata", "rresp", "rlast", "rvalid", "rready",
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract an AXI4/AXI4-Lite report from FSDB.")
    ap.add_argument("--fsdb", required=True)
    ap.add_argument("--config", required=True, help="JSON with clk plus AXI4 channel signal paths")
    ap.add_argument("--begin")
    ap.add_argument("--end")
    ap.add_argument("--max-edges", type=int, default=300000)
    ap.add_argument("--detail", choices=("summary", "transactions", "timeline", "full"), default="summary")
    ap.add_argument("--output")
    args = ap.parse_args()
    scan = None
    with json_stdout_quarantine() as json_stream:
        try:
            require_output(args.detail, args.output)
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
            edge, sample_point = sampling_contract(cfg)
            with pynpi_lifecycle([sys.argv[0]]):
                fp = open_fsdb(args.fsdb)
                try:
                    begin = time_in(fp, args.begin) if args.begin else None
                    end = time_in(fp, args.end) if args.end else None
                    signals = [cfg[key] for key in SIGNAL_KEYS if cfg.get(key)]
                    scan = iter_edge_samples(fp, cfg["clk"], signals, begin, end,
                                             edge=edge, sample_point=sample_point,
                                             max_edges=args.max_edges)
                    result = axi_summary(scan, cfg, detail=args.detail)
                    result["meta"].update({"time_base": "fsdb_tick", "scale_unit": fp.scale_unit()})
                finally:
                    close_fsdb(fp)
            emit_result("axi_summary", result, args.detail, args.output, json_stream)
            return 0
        except Exception as exc:
            scan_meta = scan.context.as_dict() if scan is not None else None
            print_json(error_document("axi_summary", exc, scan_meta=scan_meta), json_stream)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
