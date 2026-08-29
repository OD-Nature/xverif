#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "x-npi" / "scripts"))

from x_npi.jsonio import print_json  # noqa: E402
from x_npi.runtime import json_stdout_quarantine, pynpi_lifecycle  # noqa: E402
from x_npi.wave import close_fsdb, iter_edge_samples, iter_signal_changes, open_fsdb  # noqa: E402


def _legacy_rows(fp, clock: str, signals: list[str], edge: str) -> int:
    from pynpi import waveform  # type: ignore

    changes = list(iter_signal_changes(fp, clock))
    edges: list[int] = []
    previous = None
    for item in changes:
        current = str(item["value"])
        if edge == "negedge" and previous == "1" and current == "0":
            edges.append(int(item["time"]))
        if edge == "posedge" and previous == "0" and current == "1":
            edges.append(int(item["time"]))
        previous = current
    rows = []
    for edge_time in edges:
        values = waveform.sig_vec_value_at(
            fp, signals, edge_time, waveform.VctFormat_e.BinStrVal
        )
        if values is None or len(values) != len(signals):
            raise RuntimeError("legacy sig_vec_value_at failed")
        rows.append((edge_time, values))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fsdb", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--mode", choices=("legacy", "stream"), required=True)
    parser.add_argument("--edge", choices=("negedge", "posedge"), required=True)
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    signals = [value for key, value in cfg.items() if key not in {"clk", "edge", "sample_point"}
               and isinstance(value, str)]

    with json_stdout_quarantine() as json_stream:
        with pynpi_lifecycle([sys.argv[0]]):
            fp = open_fsdb(args.fsdb)
            try:
                started = time.perf_counter()
                cpu_started = time.process_time()
                if args.mode == "legacy":
                    sample_count = _legacy_rows(fp, cfg["clk"], signals, args.edge)
                else:
                    sample_point = "after" if args.edge == "posedge" else None
                    sample_count = sum(
                        1 for _ in iter_edge_samples(
                            fp, cfg["clk"], signals, edge=args.edge,
                            sample_point=sample_point,
                        )
                    )
                elapsed = time.perf_counter() - started
                cpu_elapsed = time.process_time() - cpu_started
            finally:
                close_fsdb(fp)
        print_json(
            {
                "ok": True,
                "mode": args.mode,
                "edge": args.edge,
                "sample_count": sample_count,
                "elapsed_sec": elapsed,
                "cpu_sec": cpu_elapsed,
                "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            json_stream,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
