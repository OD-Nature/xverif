"""Waveform-oriented pynpi helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, Iterator, List, Sequence


Json = Dict[str, Any]


def _waveform():
    from pynpi import waveform  # type: ignore

    return waveform


def active(value: Any) -> bool:
    text = "" if value is None else str(value)
    return text not in {"", "0", "X", "Z", "x", "z"}


def known(value: Any) -> bool:
    text = "" if value is None else str(value)
    return bool(text) and not any(ch in text for ch in "xXzZ")


def open_fsdb(path: str):
    waveform = _waveform()
    fp = waveform.open(path)
    if fp is None:
        raise RuntimeError(f"failed to open FSDB: {path}")
    return fp


def close_fsdb(file_handle: Any) -> None:
    _waveform().close(file_handle)


def time_in(file_handle: Any, value: float | int | str, unit: str | None = None) -> int:
    waveform = _waveform()
    if isinstance(value, str):
        stripped = value.strip()
        number = ""
        suffix = ""
        for ch in stripped:
            if ch.isdigit() or ch in ".+-":
                number += ch
            else:
                suffix += ch
        if not number or not suffix:
            raise ValueError(f"time string must include number and unit: {value}")
        value = float(number)
        unit = suffix
    unit = unit or "ps"
    out = waveform.convert_time_in(file_handle, value, unit)
    if out is None:
        raise RuntimeError(f"failed to convert time {value}{unit}")
    return int(out)


def sample_values(file_handle: Any, signals: Sequence[str], time: int, fmt: Any | None = None) -> Dict[str, Any]:
    waveform = _waveform()
    fmt = fmt or waveform.VctFormat_e.BinStrVal
    values = waveform.sig_vec_value_at(file_handle, list(signals), time, fmt)
    if values is None:
        raise RuntimeError("sig_vec_value_at failed")
    return {signal: values[i] if i < len(values) else None for i, signal in enumerate(signals)}


def iter_signal_changes(file_handle: Any, signal: str, begin: int | None = None,
                        end: int | None = None, fmt: Any | None = None,
                        max_changes: int | None = None) -> Iterator[Json]:
    waveform = _waveform()
    fmt = fmt or waveform.VctFormat_e.BinStrVal
    begin = file_handle.min_time() if begin is None else begin
    end = file_handle.max_time() if end is None else end
    sig = file_handle.sig_by_name(signal)
    if sig is None:
        raise RuntimeError(f"signal not found: {signal}")
    file_handle.load_vc_by_range(begin, end)
    vct = sig.create_vct()
    if vct is None:
        raise RuntimeError(f"failed to create VCT: {signal}")
    try:
        if not vct.goto_time(begin):
            return
        count = 0
        while True:
            t = vct.time()
            if t is not None and begin <= t <= end:
                yield {"time": t, "value": vct.value(fmt)}
                count += 1
                if max_changes is not None and count >= max_changes:
                    return
            if not vct.goto_next():
                return
            nxt = vct.time()
            if nxt is not None and nxt > end:
                return
    finally:
        vct.release()
        file_handle.unload_vc()


def clock_edges(file_handle: Any, clock: str, begin: int | None = None, end: int | None = None,
                posedge: bool = False, max_edges: int | None = None) -> List[int]:
    changes = list(iter_signal_changes(file_handle, clock, begin, end, max_changes=None))
    edges: List[int] = []
    prev = None
    for item in changes:
        cur = str(item.get("value"))
        if prev is not None:
            if posedge and prev == "0" and cur == "1":
                edges.append(int(item["time"]))
            if not posedge and prev == "1" and cur == "0":
                edges.append(int(item["time"]))
        prev = cur
        if max_edges is not None and len(edges) >= max_edges:
            break
    return edges


def edge_samples(file_handle: Any, clock: str, signals: Sequence[str], begin: int | None = None,
                 end: int | None = None, posedge: bool = False,
                 max_edges: int | None = None) -> List[Json]:
    edges = clock_edges(file_handle, clock, begin, end, posedge, max_edges)
    rows: List[Json] = []
    for t in edges:
        values = sample_values(file_handle, signals, t)
        rows.append({"time": t, "values": values})
    return rows


def value_statistics(file_handle: Any, signal: str, begin: int | None = None,
                     end: int | None = None, max_changes: int | None = None) -> Json:
    rows = list(iter_signal_changes(file_handle, signal, begin, end, max_changes=max_changes))
    counts = Counter(str(row["value"]) for row in rows)
    return {
        "signal": signal,
        "change_count": len(rows),
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
        "values": dict(sorted(counts.items())),
        "truncated": max_changes is not None and len(rows) >= max_changes,
    }
