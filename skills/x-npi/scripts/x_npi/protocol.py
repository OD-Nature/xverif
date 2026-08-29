"""Pure Python protocol analyzers built from sampled clock-edge rows."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Mapping

from .wave import active, known


Json = Dict[str, Any]
DETAILS = {"summary", "transactions", "timeline", "full"}


class ProtocolAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, *, stage: str, channel: str | None = None,
                 time: int | None = None, transaction_seq: int | None = None,
                 evidence: Json | None = None):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.channel = channel
        self.time = time
        self.transaction_seq = transaction_seq
        self.evidence = evidence or {}

    def as_dict(self) -> Json:
        return {key: value for key, value in {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "channel": self.channel,
            "time": self.time,
            "transaction_seq": self.transaction_seq,
            "evidence": self.evidence or None,
        }.items() if value is not None}


def _v(row: Json, name: str | None) -> Any:
    if not name:
        return None
    return row.get("values", {}).get(name)


def _require(cfg: Mapping[str, Any], keys: Iterable[str], owner: str) -> None:
    for key in keys:
        if not isinstance(cfg.get(key), str) or not str(cfg[key]).strip():
            raise ValueError(f"{owner} config requires non-empty {key}")


def _detail(detail: str) -> str:
    if detail not in DETAILS:
        raise ValueError("detail must be summary, transactions, timeline, or full")
    return detail


def _int_value(value: Any, default: int = 0) -> int:
    text = "" if value is None else str(value).strip().replace("_", "")
    if not text or not known(text):
        return default
    try:
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        if text.startswith(("0b", "0B")):
            return int(text, 2)
        if all(ch in "01" for ch in text):
            return int(text, 2)
        return int(text, 10)
    except ValueError:
        return default


def _percentile(values: List[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(pct * len(ordered)) - 1))
    return int(ordered[index])


def _distribution(values: List[int], start: str, end: str) -> Json:
    return {
        "start": start,
        "end": end,
        "count": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "avg": (sum(values) / len(values)) if values else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
    }


def _scan_meta(rows: Any) -> Json:
    context = getattr(rows, "context", None)
    if context is None:
        return {"analysis_complete": True, "sample_count": None}
    return context.as_dict()


@dataclass
class ChannelTracker:
    name: str
    valid_key: str
    ready_key: str
    valid_active: bool = False
    valid_begin_time: int | None = None
    transfers: int = 0
    stall_cycles: int = 0
    stall_windows: List[Json] = field(default_factory=list)
    current_stall: Json | None = None
    valid_unknown: int = 0
    ready_unknown: int = 0
    unknown_while_valid: int = 0
    first_unknown_time: int | None = None

    def reset(self) -> None:
        self.valid_active = False
        self.valid_begin_time = None
        self.current_stall = None

    def sample(self, row: Json) -> tuple[bool, int | None, bool]:
        time = int(row["time"])
        valid_value = _v(row, self.valid_key)
        ready_value = _v(row, self.ready_key)
        valid_known = known(valid_value)
        ready_known = known(ready_value)
        valid = valid_known and active(valid_value)
        ready = ready_known and active(ready_value)
        ambiguous = False
        if not valid_known:
            self.valid_unknown += 1
            ambiguous = True
            if self.first_unknown_time is None:
                self.first_unknown_time = time
        if not ready_known:
            self.ready_unknown += 1
            if valid:
                self.unknown_while_valid += 1
                ambiguous = True
                if self.first_unknown_time is None:
                    self.first_unknown_time = time
        if valid and not self.valid_active:
            self.valid_active = True
            self.valid_begin_time = time
        if not valid_known or not valid:
            self.valid_active = False
            self.valid_begin_time = None
        handshake = valid and ready
        begin = self.valid_begin_time
        if valid and ready_known and not ready:
            self.stall_cycles += 1
            if self.current_stall is None:
                self.current_stall = {"channel": self.name, "begin_time": time, "cycles": 0}
            self.current_stall["cycles"] += 1
        elif self.current_stall is not None:
            self.current_stall["end_time"] = time
            self.stall_windows.append(self.current_stall)
            self.current_stall = None
        if handshake:
            self.transfers += 1
            self.valid_active = False
            self.valid_begin_time = None
        return handshake, begin, ambiguous

    def finish(self) -> None:
        if self.current_stall is not None:
            self.stall_windows.append(self.current_stall)
            self.current_stall = None

    def summary(self) -> Json:
        return {
            "transfers": self.transfers,
            "stall_cycles": self.stall_cycles,
            "stall_windows": len(self.stall_windows),
            "max_stall_cycles": max((item["cycles"] for item in self.stall_windows), default=0),
            "valid_unknown": self.valid_unknown,
            "ready_unknown": self.ready_unknown,
            "unknown_while_valid": self.unknown_while_valid,
            "first_unknown_time": self.first_unknown_time,
        }


def _transaction_view(txn: Json, include_payload: bool) -> Json:
    hidden = {"_expected_beats", "_data_complete"}
    payload = {"data", "strb", "data_resp", "data_handshake_times", "data_last"}
    return {key: value for key, value in txn.items()
            if key not in hidden and (include_payload or key not in payload)}


def axi_summary(rows: Iterable[Json], cfg: Json, detail: str = "summary") -> Json:
    detail = _detail(detail)
    if "wid" in cfg:
        raise ValueError("AXI4/AXI4-Lite helper does not support wid; WID is AXI3-only")
    _require(cfg, (
        "awvalid", "awready", "awaddr", "wvalid", "wready", "wdata",
        "bvalid", "bready", "arvalid", "arready", "araddr",
        "rvalid", "rready", "rdata",
    ), "AXI")

    trackers = {
        name: ChannelTracker(name, cfg[f"{name.lower()}valid"], cfg[f"{name.lower()}ready"])
        for name in ("AW", "W", "B", "AR", "R")
    }
    writes: List[Json] = []
    reads: List[Json] = []
    pending_writes: Deque[Json] = deque()
    pending_reads: Dict[str, Deque[Json]] = defaultdict(deque)
    wbeats: Deque[Json] = deque()
    osd_read: Dict[str, int] = defaultdict(int)
    osd_write: Dict[str, int] = defaultdict(int)
    change_points: List[Json] = []
    previous_osd = (-1, -1)
    reset_active = False
    reset_cleared = {"writes": 0, "reads": 0, "w_beats": 0}
    quality = "complete"
    next_seq = 0

    def signal(row: Json, key: str) -> Any:
        return _v(row, cfg.get(key))

    def update_osd(time: int) -> None:
        nonlocal previous_osd
        current = (sum(osd_read.values()), sum(osd_write.values()))
        if current != previous_osd:
            change_points.append({
                "time": time,
                "read": current[0],
                "write": current[1],
                "read_by_id": dict(osd_read),
                "write_by_id": dict(osd_write),
            })
            previous_osd = current

    for row in rows:
        time = int(row["time"])
        if cfg.get("rst_n") and (not known(signal(row, "rst_n")) or not active(signal(row, "rst_n"))):
            if not reset_active:
                reset_cleared["writes"] += len(pending_writes)
                reset_cleared["reads"] += sum(len(queue) for queue in pending_reads.values())
                reset_cleared["w_beats"] += len(wbeats)
                pending_writes.clear()
                pending_reads.clear()
                wbeats.clear()
                osd_read.clear()
                osd_write.clear()
                for tracker in trackers.values():
                    tracker.reset()
                update_osd(time)
            reset_active = True
            continue
        reset_active = False

        events: Dict[str, tuple[bool, int | None]] = {}
        for name, tracker in trackers.items():
            handshake, valid_begin, ambiguous = tracker.sample(row)
            events[name] = (handshake, valid_begin)
            if ambiguous:
                quality = "ambiguous"

        w_handshake, w_valid_begin = events["W"]
        aw_handshake, aw_valid_begin = events["AW"]
        b_handshake, _ = events["B"]
        ar_handshake, ar_valid_begin = events["AR"]
        r_handshake, r_valid_begin = events["R"]

        if w_handshake:
            wbeats.append({
                "time": time,
                "valid_begin_time": w_valid_begin,
                "data": signal(row, "wdata"),
                "strb": signal(row, "wstrb"),
                "last": active(signal(row, "wlast")) if cfg.get("wlast") else True,
            })

        if aw_handshake:
            txn_id = str(signal(row, "awid") or "0")
            expected = _int_value(signal(row, "awlen"), 0) + 1
            txn = {
                "seq": next_seq,
                "kind": "write",
                "id": txn_id,
                "addr": signal(row, "awaddr"),
                "addr_valid_begin_time": aw_valid_begin,
                "addr_time": time,
                "expected_beats": expected,
                "data": [],
                "strb": [],
                "data_handshake_times": [],
                "data_last": [],
                "_expected_beats": expected,
                "_data_complete": False,
            }
            next_seq += 1
            pending_writes.append(txn)
            osd_write[txn_id] += 1

        while wbeats:
            target = next((txn for txn in pending_writes if not txn["_data_complete"]), None)
            if target is None:
                break
            beat = wbeats.popleft()
            if not target["data"]:
                target["first_data_valid_begin_time"] = beat["valid_begin_time"]
                target["first_data_time"] = beat["time"]
            target["data"].append(beat["data"])
            target["strb"].append(beat["strb"])
            target["data_handshake_times"].append(beat["time"])
            target["data_last"].append(bool(beat["last"]))
            target["last_data_time"] = beat["time"]
            count = len(target["data"])
            expected = int(target["_expected_beats"])
            if beat["last"]:
                if count != expected:
                    raise ProtocolAnalysisError(
                        "AXI_BEAT_COUNT_MISMATCH",
                        f"write transaction expected {expected} beats but WLAST arrived on beat {count}",
                        stage="pairing", channel="W", time=beat["time"],
                        transaction_seq=target["seq"], evidence={"expected": expected, "actual": count})
                target["_data_complete"] = True
                first_time = int(target["first_data_time"])
                addr_time = int(target["addr_time"])
                target["phase_order"] = (
                    "w_before_aw" if first_time < addr_time else
                    "same_cycle" if first_time == addr_time else "aw_before_w"
                )
            elif count >= expected:
                raise ProtocolAnalysisError(
                    "AXI_BEAT_COUNT_MISMATCH",
                    f"write transaction reached expected beat count {expected} without WLAST",
                    stage="pairing", channel="W", time=beat["time"],
                    transaction_seq=target["seq"], evidence={"expected": expected, "actual": count})

        if b_handshake:
            bid = str(signal(row, "bid") or "0")
            same_id = [txn for txn in pending_writes if txn["id"] == bid]
            target = next((txn for txn in same_id if txn["_data_complete"]), None)
            if target is None:
                if same_id:
                    raise ProtocolAnalysisError(
                        "AXI_RESPONSE_DEPENDENCY_VIOLATION",
                        "B handshake occurred before matching write data completed",
                        stage="pairing", channel="B", time=time,
                        transaction_seq=same_id[0]["seq"], evidence={"bid": bid})
                raise ProtocolAnalysisError(
                    "AXI_ORPHAN_B", "B handshake has no matching AW transaction",
                    stage="pairing", channel="B", time=time, evidence={"bid": bid})
            if time <= int(target["addr_time"]) or time <= int(target["last_data_time"]):
                raise ProtocolAnalysisError(
                    "AXI_RESPONSE_DEPENDENCY_VIOLATION",
                    "B handshake did not follow both AW and WLAST handshakes",
                    stage="pairing", channel="B", time=time,
                    transaction_seq=target["seq"], evidence={"bid": bid})
            target["resp_time"] = time
            target["resp"] = signal(row, "bresp")
            writes.append(target)
            pending_writes.remove(target)
            osd_write[bid] -= 1
            if osd_write[bid] == 0:
                del osd_write[bid]

        if ar_handshake:
            txn_id = str(signal(row, "arid") or "0")
            expected = _int_value(signal(row, "arlen"), 0) + 1
            txn = {
                "seq": next_seq,
                "kind": "read",
                "id": txn_id,
                "addr": signal(row, "araddr"),
                "addr_valid_begin_time": ar_valid_begin,
                "addr_time": time,
                "expected_beats": expected,
                "data": [],
                "data_resp": [],
                "data_handshake_times": [],
                "data_last": [],
                "_expected_beats": expected,
            }
            next_seq += 1
            pending_reads[txn_id].append(txn)
            osd_read[txn_id] += 1

        if r_handshake:
            rid = str(signal(row, "rid") or "0")
            queue = pending_reads.get(rid)
            if not queue:
                raise ProtocolAnalysisError(
                    "AXI_ORPHAN_R", "R handshake has no pending AR with the same ID",
                    stage="pairing", channel="R", time=time, evidence={"rid": rid})
            target = queue[0]
            if time <= int(target["addr_time"]):
                raise ProtocolAnalysisError(
                    "AXI_READ_DEPENDENCY_VIOLATION", "R handshake did not follow AR handshake",
                    stage="pairing", channel="R", time=time,
                    transaction_seq=target["seq"], evidence={"rid": rid})
            if not target["data"]:
                target["first_data_valid_begin_time"] = r_valid_begin
                target["first_data_time"] = time
            target["data"].append(signal(row, "rdata"))
            target["data_resp"].append(signal(row, "rresp"))
            target["data_handshake_times"].append(time)
            last = active(signal(row, "rlast")) if cfg.get("rlast") else True
            target["data_last"].append(last)
            target["last_data_time"] = time
            count = len(target["data"])
            expected = int(target["_expected_beats"])
            if last:
                if count != expected:
                    raise ProtocolAnalysisError(
                        "AXI_BEAT_COUNT_MISMATCH",
                        f"read transaction expected {expected} beats but RLAST arrived on beat {count}",
                        stage="pairing", channel="R", time=time,
                        transaction_seq=target["seq"], evidence={"expected": expected, "actual": count})
                target["resp_time"] = time
                target["resp"] = signal(row, "rresp")
                reads.append(target)
                queue.popleft()
                if not queue:
                    del pending_reads[rid]
                osd_read[rid] -= 1
                if osd_read[rid] == 0:
                    del osd_read[rid]
            elif count >= expected:
                raise ProtocolAnalysisError(
                    "AXI_BEAT_COUNT_MISMATCH",
                    f"read transaction reached expected beat count {expected} without RLAST",
                    stage="pairing", channel="R", time=time,
                    transaction_seq=target["seq"], evidence={"expected": expected, "actual": count})
        update_osd(time)

    for tracker in trackers.values():
        tracker.finish()
    meta = _scan_meta(rows)
    meta["analysis_quality"] = quality

    phases = {
        "arvalid_to_ar": _distribution(
            [int(t["addr_time"] - t["addr_valid_begin_time"]) for t in reads
             if t.get("addr_valid_begin_time") is not None], "ARVALID begin", "AR handshake"),
        "ar_to_first_r": _distribution(
            [int(t["first_data_time"] - t["addr_time"]) for t in reads], "AR handshake", "first R handshake"),
        "ar_to_rlast": _distribution(
            [int(t["last_data_time"] - t["addr_time"]) for t in reads], "AR handshake", "RLAST handshake"),
        "awvalid_to_aw": _distribution(
            [int(t["addr_time"] - t["addr_valid_begin_time"]) for t in writes
             if t.get("addr_valid_begin_time") is not None], "AWVALID begin", "AW handshake"),
        "aw_to_first_w": _distribution(
            [int(t["first_data_time"] - t["addr_time"]) for t in writes], "AW handshake", "first W handshake"),
        "aw_to_wlast": _distribution(
            [int(t["last_data_time"] - t["addr_time"]) for t in writes], "AW handshake", "WLAST handshake"),
        "aw_to_b": _distribution(
            [int(t["resp_time"] - t["addr_time"]) for t in writes], "AW handshake", "B handshake"),
    }
    pending_read_count = sum(len(queue) for queue in pending_reads.values())
    summary = {
        "writes": len(writes),
        "reads": len(reads),
        "total": len(writes) + len(reads),
        "channels": {name: tracker.summary() for name, tracker in trackers.items()},
        "phases": phases,
        "max_read_outstanding": max((item["read"] for item in change_points), default=0),
        "max_write_outstanding": max((item["write"] for item in change_points), default=0),
        "final_read_outstanding": sum(osd_read.values()),
        "final_write_outstanding": sum(osd_write.values()),
        "pending_transactions": {"writes": len(pending_writes), "reads": pending_read_count,
                                 "buffered_w_beats": len(wbeats)},
        "reset_cleared": reset_cleared,
    }
    data: Json = {}
    include_payload = detail == "full"
    if detail in {"transactions", "full"}:
        data["transactions"] = {
            "writes": [_transaction_view(t, include_payload) for t in writes],
            "reads": [_transaction_view(t, include_payload) for t in reads],
            "pending_writes": [_transaction_view(t, include_payload) for t in pending_writes],
            "pending_reads": [_transaction_view(t, include_payload)
                              for queue in pending_reads.values() for t in queue],
            "buffered_w_beats": list(wbeats) if include_payload else len(wbeats),
        }
    if detail in {"timeline", "full"}:
        data["timeline"] = {
            "outstanding_change_points": change_points,
            "stall_windows": [window for tracker in trackers.values()
                              for window in tracker.stall_windows],
        }
    return {"summary": summary, "meta": meta, "data": data}


def axi_transactions(rows: Iterable[Json], cfg: Json) -> Json:
    return axi_summary(rows, cfg, detail="full")["data"]["transactions"]


def apb_summary(rows: Iterable[Json], cfg: Json, detail: str = "summary") -> Json:
    detail = _detail(detail)
    _require(cfg, ("psel", "penable", "pready", "pslverr", "pwrite", "paddr", "pwdata", "prdata"), "APB")
    transactions: List[Json] = []
    current: Json | None = None
    incomplete: List[Json] = []
    reset_cleared = 0
    unknown = {key: 0 for key in ("psel", "penable", "pready", "pwrite", "pslverr")}
    first_unknown_time: int | None = None
    quality = "complete"
    next_seq = 0
    reset_active = False
    completion_seen = False

    def new_transaction(row: Json, time: int, setup_time: int | None) -> Json:
        nonlocal next_seq
        pwrite_value = _v(row, cfg["pwrite"])
        is_write = known(pwrite_value) and active(pwrite_value)
        txn = {
            "seq": next_seq,
            "kind": "write" if is_write else "read",
            "setup_begin_time": setup_time,
            "access_begin_time": None,
            "completion_time": None,
            "wait_cycles": 0,
            "addr": _v(row, cfg["paddr"]),
            "data": _v(row, cfg["pwdata"] if is_write else cfg["prdata"]),
            "error": False,
        }
        next_seq += 1
        return txn

    for row in rows:
        time = int(row["time"])
        if cfg.get("rst_n") and (not known(_v(row, cfg["rst_n"])) or not active(_v(row, cfg["rst_n"]))):
            if not reset_active and current is not None:
                reset_cleared += 1
                current = None
            completion_seen = False
            reset_active = True
            continue
        reset_active = False
        values = {key: _v(row, cfg[key]) for key in unknown}
        for key, value in values.items():
            if not known(value):
                unknown[key] += 1
                if key in {"psel", "penable", "pready", "pwrite"}:
                    quality = "ambiguous"
                if first_unknown_time is None:
                    first_unknown_time = time
        psel = known(values["psel"]) and active(values["psel"])
        penable = known(values["penable"]) and active(values["penable"])
        pready = known(values["pready"]) and active(values["pready"])
        if not psel or not penable:
            completion_seen = False
        if psel and not penable and current is None:
            current = new_transaction(row, time, time)
        if psel and penable and current is None and not completion_seen:
            current = new_transaction(row, time, None)
        if current is not None and psel and penable:
            if current["access_begin_time"] is None:
                current["access_begin_time"] = time
            if not pready:
                current["wait_cycles"] += 1
            else:
                current["completion_time"] = time
                current["data"] = _v(row, cfg["pwdata"] if current["kind"] == "write" else cfg["prdata"])
                current["error"] = known(values["pslverr"]) and active(values["pslverr"])
                transactions.append(current)
                current = None
                completion_seen = True
        elif current is not None and not psel:
            current["end_time"] = time
            incomplete.append(current)
            current = None
    if current is not None:
        incomplete.append(current)

    meta = _scan_meta(rows)
    meta["analysis_quality"] = quality
    summary = {
        "total": len(transactions),
        "writes": sum(1 for t in transactions if t["kind"] == "write"),
        "reads": sum(1 for t in transactions if t["kind"] == "read"),
        "errors": sum(1 for t in transactions if t["error"]),
        "wait_cycles": sum(int(t["wait_cycles"]) for t in transactions),
        "max_wait_cycles": max((int(t["wait_cycles"]) for t in transactions), default=0),
        "incomplete": len(incomplete),
        "reset_cleared": reset_cleared,
        "unknown": {**unknown, "first_time": first_unknown_time},
    }
    data: Json = {}
    if detail in {"transactions", "full"}:
        if detail == "transactions":
            data["transactions"] = [{key: value for key, value in txn.items() if key != "data"}
                                    for txn in transactions]
        else:
            data["transactions"] = transactions
        data["incomplete_transactions"] = incomplete
    if detail in {"timeline", "full"}:
        data["timeline"] = [
            {"seq": t["seq"], "setup_begin_time": t["setup_begin_time"],
             "access_begin_time": t["access_begin_time"], "completion_time": t["completion_time"],
             "wait_cycles": t["wait_cycles"]}
            for t in transactions
        ]
    return {"summary": summary, "meta": meta, "data": data}


def apb_transactions(rows: Iterable[Json], cfg: Json) -> List[Json]:
    return apb_summary(rows, cfg, detail="full")["data"]["transactions"]


def stream_summary(rows: Iterable[Json], cfg: Json, detail: str = "summary") -> Json:
    detail = _detail(detail)
    _require(cfg, ("valid",), "stream")
    ready = bool(cfg.get("ready"))
    bp = bool(cfg.get("bp"))
    if ready == bp:
        raise ValueError("stream config requires exactly one of ready or bp")
    sop = bool(cfg.get("sop"))
    eop = bool(cfg.get("eop"))
    if sop != eop:
        raise ValueError("stream config requires both sop and eop, or neither")
    ready_key = cfg["ready"] if ready else cfg["bp"]
    tracker = ChannelTracker("STREAM", cfg["valid"], ready_key)
    transfers: List[Json] = []
    packets: List[Json] = []
    current_packet: Json | None = None
    next_packet = 0
    quality = "complete"

    for row in rows:
        time = int(row["time"])
        if cfg.get("rst_n") and (not known(_v(row, cfg["rst_n"])) or not active(_v(row, cfg["rst_n"]))):
            tracker.reset()
            current_packet = None
            continue
        if bp:
            original = row.get("values", {}).get(ready_key)
            values = dict(row.get("values", {}))
            values[ready_key] = "1" if known(original) and not active(original) else "0" if known(original) else original
            sample_row = {**row, "values": values}
        else:
            sample_row = row
        handshake, valid_begin, ambiguous = tracker.sample(sample_row)
        if ambiguous:
            quality = "ambiguous"
        if not handshake:
            continue
        fields = {name: _v(row, signal) for name, signal in cfg.get("fields", {}).items()}
        if cfg.get("data"):
            fields["data"] = _v(row, cfg["data"])
        transfer = {
            "beat_index": len(transfers),
            "valid_begin_time": valid_begin,
            "handshake_time": time,
            "fields": fields,
        }
        if sop:
            is_sop = active(_v(row, cfg["sop"]))
            is_eop = active(_v(row, cfg["eop"]))
            if is_sop:
                if current_packet is not None:
                    raise ProtocolAnalysisError(
                        "STREAM_REPEATED_SOP", "SOP arrived before the current packet closed",
                        stage="pairing", channel="STREAM", time=time,
                        transaction_seq=current_packet["seq"])
                current_packet = {"seq": next_packet, "begin_time": time, "beats": []}
                next_packet += 1
            if current_packet is None:
                raise ProtocolAnalysisError(
                    "STREAM_ORPHAN_BEAT", "transfer arrived without an active SOP-delimited packet",
                    stage="pairing", channel="STREAM", time=time)
            current_packet["beats"].append(transfer)
            transfer["packet_seq"] = current_packet["seq"]
            if is_eop:
                current_packet["end_time"] = time
                packets.append(current_packet)
                current_packet = None
        transfers.append(transfer)
    tracker.finish()
    meta = _scan_meta(rows)
    meta["analysis_quality"] = quality
    summary = {
        "transfers": len(transfers),
        "stall_cycles": tracker.stall_cycles,
        "stall_windows": len(tracker.stall_windows),
        "max_stall_cycles": max((item["cycles"] for item in tracker.stall_windows), default=0),
        "packets": len(packets),
        "incomplete_packets": 1 if current_packet is not None else 0,
        "unknown": tracker.summary(),
        "handshake_mode": "ready" if ready else "bp",
    }
    data: Json = {}
    if detail in {"transactions", "full"}:
        if detail == "transactions":
            data["transfers"] = [{key: value for key, value in item.items() if key != "fields"}
                                 for item in transfers]
            data["packets"] = [{key: value for key, value in item.items() if key != "beats"}
                               for item in packets]
        else:
            data["transfers"] = transfers
            data["packets"] = packets
        data["incomplete_packet"] = current_packet
    if detail in {"timeline", "full"}:
        data["timeline"] = {"stall_windows": tracker.stall_windows,
                            "handshakes": [item["handshake_time"] for item in transfers]}
    return {"summary": summary, "meta": meta, "data": data}
