"""Waveform-oriented pynpi helpers."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence


Json = Dict[str, Any]


class SignalPreflightError(RuntimeError):
    def __init__(self, missing: List[Json]):
        super().__init__("required waveform signals were not found")
        self.missing = missing


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


def _candidate_paths(file_handle: Any, requested: str, limit: int = 5) -> List[str]:
    parent_name, _, basename = requested.rpartition(".")
    candidates: List[str] = []

    def add_signal(signal: Any) -> None:
        if len(candidates) >= limit:
            return
        name = str(signal.name())
        if name == basename or basename.lower() in name.lower() or name.lower() in basename.lower():
            full_name = str(signal.full_name())
            if full_name not in candidates:
                candidates.append(full_name)

    if parent_name:
        parent = file_handle.scope_by_name(parent_name)
        if parent is not None:
            for signal in parent.sig_list():
                add_signal(signal)
                if len(candidates) >= limit:
                    return candidates

    scopes = deque(file_handle.top_scope_list())
    for signal in file_handle.top_sig_list():
        add_signal(signal)
    while scopes and len(candidates) < limit:
        scope = scopes.popleft()
        for signal in scope.sig_list():
            add_signal(signal)
            if len(candidates) >= limit:
                break
        if len(candidates) < limit:
            scopes.extend(scope.child_scope_list())
    return candidates


def preflight_signals(file_handle: Any, signals: Sequence[str]) -> Json:
    found: List[str] = []
    missing: List[Json] = []
    seen = set()
    for path in signals:
        if path in seen:
            continue
        seen.add(path)
        if file_handle.sig_by_name(path) is not None:
            found.append(path)
        else:
            missing.append({"requested": path, "candidates": _candidate_paths(file_handle, path)})
    result = {"found": found, "missing": missing}
    if missing:
        raise SignalPreflightError(missing)
    return result


def sample_values(file_handle: Any, signals: Sequence[str], time: int, fmt: Any | None = None) -> Dict[str, Any]:
    waveform = _waveform()
    preflight_signals(file_handle, signals)
    fmt = fmt or waveform.VctFormat_e.BinStrVal
    values = waveform.sig_vec_value_at(file_handle, list(signals), time, fmt)
    if values is None or len(values) != len(signals):
        raise RuntimeError(f"sig_vec_value_at failed for {len(signals)} preflighted signals at {time}")
    return {signal: values[i] for i, signal in enumerate(signals)}


def iter_signal_changes(file_handle: Any, signal: str, begin: int | None = None,
                        end: int | None = None, fmt: Any | None = None,
                        max_changes: int | None = None) -> Iterator[Json]:
    waveform = _waveform()
    fmt = fmt or waveform.VctFormat_e.BinStrVal
    begin = file_handle.min_time() if begin is None else begin
    end = file_handle.max_time() if end is None else end
    sig = file_handle.sig_by_name(signal)
    if sig is None:
        raise SignalPreflightError([{"requested": signal, "candidates": _candidate_paths(file_handle, signal)}])
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
                yield {"time": int(t), "value": vct.value(fmt)}
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


@dataclass
class EdgeSampleContext:
    edge: str
    sample_point: str | None
    requested_begin: int
    requested_end: int
    sample_count: int = 0
    analysis_complete: bool = True
    stop_reason: str | None = None
    first_sample_time: int | None = None
    last_sample_time: int | None = None

    def as_dict(self) -> Json:
        return {
            "edge": self.edge,
            "sample_point": self.sample_point,
            "requested_begin": self.requested_begin,
            "requested_end": self.requested_end,
            "sample_count": self.sample_count,
            "analysis_complete": self.analysis_complete,
            "stop_reason": self.stop_reason,
            "first_sample_time": self.first_sample_time,
            "last_sample_time": self.last_sample_time,
        }


class EdgeSampleScan(Iterable[Json]):
    """Single-use streaming clock sample scan with post-consumption metadata."""

    def __init__(self, file_handle: Any, clock: str, signals: Sequence[str],
                 begin: int | None = None, end: int | None = None, *,
                 edge: str = "negedge", sample_point: str | None = None,
                 max_edges: int | None = None):
        edge = str(edge).lower()
        if edge not in {"negedge", "posedge"}:
            raise ValueError("edge must be negedge or posedge")
        if edge == "posedge" and sample_point not in {"before", "after"}:
            raise ValueError("posedge requires sample_point=before or after")
        if edge == "negedge" and sample_point is not None:
            raise ValueError("sample_point is only valid with edge=posedge")
        if max_edges is not None and max_edges <= 0:
            raise ValueError("max_edges must be positive")
        self.file_handle = file_handle
        self.clock = clock
        self.signals = list(dict.fromkeys(signals))
        self.begin = int(file_handle.min_time() if begin is None else begin)
        self.end = int(file_handle.max_time() if end is None else end)
        if self.begin > self.end:
            raise ValueError("begin must not be greater than end")
        self.edge = edge
        self.sample_point = sample_point
        self.max_edges = max_edges
        self.context = EdgeSampleContext(edge, sample_point, self.begin, self.end)
        self._started = False
        preflight_signals(file_handle, [clock, *self.signals])

    def __iter__(self) -> Iterator[Json]:
        if self._started:
            raise RuntimeError("EdgeSampleScan is single-use")
        self._started = True
        if self.edge == "negedge":
            yield from self._iter_negedge_bulk()
        else:
            yield from self._iter_posedge_grouped()

    def _record(self, time: int) -> bool:
        if self.max_edges is not None and self.context.sample_count >= self.max_edges:
            self.context.analysis_complete = False
            self.context.stop_reason = "max_edges"
            return False
        self.context.sample_count += 1
        if self.context.first_sample_time is None:
            self.context.first_sample_time = time
        self.context.last_sample_time = time
        return True

    def _iter_negedge_bulk(self) -> Iterator[Json]:
        waveform = _waveform()
        fmt = waveform.VctFormat_e.BinStrVal
        prev: str | None = None
        for item in iter_signal_changes(self.file_handle, self.clock, self.begin, self.end, fmt):
            cur = str(item["value"])
            if prev == "1" and cur == "0":
                time = int(item["time"])
                if not self._record(time):
                    return
                values = [] if not self.signals else waveform.sig_vec_value_at(self.file_handle, self.signals, time, fmt)
                if values is None or len(values) != len(self.signals):
                    raise RuntimeError(f"sig_vec_value_at failed for preflighted signals at {time}")
                yield {"time": time, "values": dict(zip(self.signals, values))}
            prev = cur

    def _iter_posedge_grouped(self) -> Iterator[Json]:
        waveform = _waveform()
        fmt = waveform.VctFormat_e.BinStrVal
        all_paths = [self.clock, *self.signals]
        initial_time = self.begin - 1 if self.begin > int(self.file_handle.min_time()) else self.begin
        initial = waveform.sig_vec_value_at(self.file_handle, all_paths, initial_time, fmt)
        if initial is None or len(initial) != len(all_paths):
            raise RuntimeError("failed to read initial values for grouped edge sampling")
        current = dict(zip(all_paths, initial))
        iterator = waveform.TimeBasedHandle()
        ids: Dict[int, str] = {}
        for path in all_paths:
            signal = self.file_handle.sig_by_name(path)
            signal_id = int(iterator.add(signal))
            if signal_id <= 0:
                raise RuntimeError(f"failed to add signal to TimeBasedHandle: {path}")
            ids[signal_id] = path
        iterator.set_max_session_load(6)
        iterator.iter_start(self.begin, self.end)
        try:
            pending: tuple[int, int, Any] | None = None
            while True:
                if pending is None:
                    signal_id, time = iterator.iter_next()
                    if int(signal_id) == 0:
                        return
                    pending = (int(signal_id), int(time), iterator.get_value(fmt))
                group_time = pending[1]
                before = dict(current)
                clock_changed = False
                posedge_hit = False
                while pending is not None and pending[1] == group_time:
                    signal_id, _, value = pending
                    path = ids.get(signal_id)
                    if path is None:
                        raise RuntimeError(f"TimeBasedHandle returned unknown signal id: {signal_id}")
                    previous = str(current.get(path, ""))
                    current[path] = value
                    if path == self.clock:
                        clock_changed = True
                        if previous == "0" and str(value) == "1":
                            posedge_hit = True
                    next_id, next_time = iterator.iter_next()
                    if int(next_id) == 0:
                        pending = None
                    else:
                        pending = (int(next_id), int(next_time), iterator.get_value(fmt))
                if clock_changed and posedge_hit:
                    if not self._record(group_time):
                        return
                    source = before if self.sample_point == "before" else current
                    yield {"time": group_time,
                           "values": {path: source.get(path) for path in self.signals}}
                if pending is None:
                    return
        finally:
            iterator.iter_stop()


def iter_edge_samples(file_handle: Any, clock: str, signals: Sequence[str],
                      begin: int | None = None, end: int | None = None, *,
                      edge: str = "negedge", sample_point: str | None = None,
                      max_edges: int | None = None) -> EdgeSampleScan:
    return EdgeSampleScan(file_handle, clock, signals, begin, end, edge=edge,
                          sample_point=sample_point, max_edges=max_edges)


def clock_edges(file_handle: Any, clock: str, begin: int | None = None,
                end: int | None = None, *, edge: str = "negedge",
                sample_point: str | None = None,
                max_edges: int | None = None) -> List[int]:
    scan = iter_edge_samples(file_handle, clock, [], begin, end, edge=edge,
                             sample_point=sample_point, max_edges=max_edges)
    return [int(row["time"]) for row in scan]


def edge_samples(file_handle: Any, clock: str, signals: Sequence[str],
                 begin: int | None = None, end: int | None = None, *,
                 edge: str = "negedge", sample_point: str | None = None,
                 max_edges: int | None = None) -> List[Json]:
    return list(iter_edge_samples(file_handle, clock, signals, begin, end,
                                  edge=edge, sample_point=sample_point,
                                  max_edges=max_edges))


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
