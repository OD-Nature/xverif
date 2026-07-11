#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO_ROOT = os.path.abspath(os.path.join(ROOT, ".."))
NONAXI_DIR = os.path.join(ROOT, "testdata", "waveform", "ai_complex_wave")
NONAXI_FSDB = os.path.join(NONAXI_DIR, "out", "waves.fsdb")
AXI_DIR = os.environ.get(
    "XDEBUG_AXI_FIXTURE_DIR",
    os.path.join(ROOT, "testdata", "waveform", "axi_vip_real"),
)
AXI_FSDB = os.path.join(
    AXI_DIR,
    "out",
    "regression",
    "test",
    "axi_multi_id_test",
    "waves.fsdb",
)
AXI_SIM_LOG = os.path.join(
    AXI_DIR,
    "out",
    "regression",
    "test",
    "axi_multi_id_test",
    "sim.log",
)
DEFAULT_AXI_ENV = {
    "AXI_REFERENCE_ROOT": "~/axi_test/test",
    "SVT_VIP_INCDIR": "~/axi_test/test/include/sverilog",
    "SVT_VIP_SRCDIR": "~/axi_test/test/src/sverilog/vcs",
}
DEFAULT_QUERY_TIMEOUT_MS = int(os.environ.get("XDEBUG_QUERY_TIMEOUT_MS", "120000"))
PROGRESS_HEARTBEAT_SEC = int(os.environ.get("XDEBUG_PROGRESS_HEARTBEAT_SEC", "30"))


def log_progress(message):
    print("[xdebug-progress] {}".format(message), flush=True)


def should_print_progress_line(line):
    text = line.strip()
    if not text:
        return False
    if "AXI_EXPECTED_TXN_JSON" in text:
        return False
    important_fragments = [
        "make ",
        "vlogan ",
        "vcs ",
        "simv ",
        "Chronologic VCS",
        "Version V-",
        "Top Level Modules:",
        "CPU time:",
        "Starting test",
        "Starting master",
        "TEST PASSED",
        "Master WRITE transactions",
        "Master READ transactions",
        "UVM_ERROR :",
        "UVM_FATAL :",
        "Error-",
        "Fatal",
        "FAIL:",
    ]
    return any(fragment in text for fragment in important_fragments)


def run_cmd(cmd, cwd=None, env=None, timeout=120, input_text=None, progress_label=None):
    start = time.time()
    if progress_label:
        log_progress("{}: start: {}".format(progress_label, " ".join(cmd)))
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        selector = selectors.DefaultSelector()
        if proc.stdout is not None:
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        if proc.stderr is not None:
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        stdout_chunks = []
        stderr_chunks = []
        last_heartbeat = start
        def emit_heartbeat():
            nonlocal last_heartbeat
            heartbeat_now = time.time()
            if heartbeat_now - last_heartbeat >= PROGRESS_HEARTBEAT_SEC:
                log_progress("{}: still running ({}s)".format(progress_label, int(heartbeat_now - start)))
                last_heartbeat = heartbeat_now

        while selector.get_map():
            now = time.time()
            if timeout is not None and now - start > timeout:
                proc.kill()
                raise subprocess.TimeoutExpired(cmd, timeout)
            events = selector.select(timeout=1.0)
            if not events:
                emit_heartbeat()
                if proc.poll() is not None:
                    for key in list(selector.get_map().values()):
                        line = key.fileobj.readline()
                        while line:
                            if key.data == "stdout":
                                stdout_chunks.append(line)
                            else:
                                stderr_chunks.append(line)
                            if should_print_progress_line(line):
                                print(line, end="", flush=True)
                            line = key.fileobj.readline()
                        selector.unregister(key.fileobj)
                continue
            for key, _ in events:
                line = key.fileobj.readline()
                if line:
                    if key.data == "stdout":
                        stdout_chunks.append(line)
                    else:
                        stderr_chunks.append(line)
                    if should_print_progress_line(line):
                        print(line, end="", flush=True)
                else:
                    selector.unregister(key.fileobj)
            emit_heartbeat()
        rc = proc.wait()
        elapsed_ms = int((time.time() - start) * 1000)
        log_progress("{}: done rc={} elapsed_ms={}".format(progress_label, rc, elapsed_ms))
        return rc, "".join(stdout_chunks), "".join(stderr_chunks), elapsed_ms

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout,
        input=input_text,
    )
    elapsed_ms = int((time.time() - start) * 1000)
    return proc.returncode, proc.stdout, proc.stderr, elapsed_ms


def apply_axi_env_defaults(env):
    for name, value in DEFAULT_AXI_ENV.items():
        env.setdefault(name, value)
    return env


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def duration_fs(value):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(fs|ps|ns|us|ms|s)", value)
    require(match is not None, "invalid duration string: {}".format(value))
    scales = {"fs": 1, "ps": 10**3, "ns": 10**6, "us": 10**9,
              "ms": 10**12, "s": 10**15}
    return float(match.group(1)) * scales[match.group(2)]


def require_clock_summary(resp, edge, sample_point=None, expected_clock="ai_complex_top.clk"):
    summary = resp["summary"]
    require(summary["sampling_mode"] == "clock_edge", "missing clock_edge sampling mode")
    require(summary["clock"] == expected_clock, "unexpected summary clock")
    require(summary["edge"] == edge, "unexpected summary edge: {}".format(summary["edge"]))
    expected_sample_point = sample_point
    if expected_sample_point is None and edge in ("posedge", "dual"):
        expected_sample_point = "before"
    if expected_sample_point is None:
        require("sample_point" not in summary, "negedge summary should not expose sample_point")
    else:
        require(summary["sample_point"] == expected_sample_point, "unexpected summary sample_point")
    require(summary["sample_time_semantics"] == "time is sample_time",
            "missing sample time semantics: {}".format(json.dumps(summary, sort_keys=True)))


def time_ns(value):
    text = str(value).strip().lower()
    require(text.endswith("ns"), "expected ns time, got {}".format(value))
    return float(text[:-2])


def normalize_sv_hex(value):
    text = str(value).strip().lower().replace("_", "")
    if text.startswith("'h"):
        text = text[2:]
    elif text.startswith("0x"):
        text = text[2:]
    if text == "":
        text = "0"
    text = text.lstrip("0") or "0"
    return "'h" + text


def parse_axi_expected_log(path):
    records = {"WR": [], "RD": []}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            marker = "AXI_EXPECTED_TXN_JSON "
            if marker not in line:
                continue
            payload = line.split(marker, 1)[1].strip()
            rec = json.loads(payload)
            rec["dir"] = rec["dir"].upper()
            records[rec["dir"]].append(rec)
    return records


def read_axi_export_table(path):
    delimiter = "," if path.endswith(".csv") else "\t"
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        rows = list(reader)
        require(reader.fieldnames is not None, "missing export header: {}".format(path))
        require("data" not in reader.fieldnames, "export unexpectedly contains data column: {}".format(path))
        return rows


def axi_compare_key(row):
    return (
        normalize_sv_hex(row["id"]),
        normalize_sv_hex(row["addr"]),
        normalize_sv_hex(row["len"]),
        normalize_sv_hex(row["size"]),
        normalize_sv_hex(row["burst"]),
        normalize_sv_hex(row["resp"]),
        int(row["beat_count"]),
        int(row["expected_beat_count"]),
    )


def expected_compare_key(row):
    return (
        normalize_sv_hex(row["id"]),
        normalize_sv_hex(row["addr"]),
        normalize_sv_hex(row["len"]),
        normalize_sv_hex(row["size"]),
        normalize_sv_hex(row["burst"]),
        normalize_sv_hex(row["resp"]),
        int(row["beat_count"]),
        int(row["expected_beat_count"]),
    )


def require_completion_sorted(rows, label):
    def completion_time_ps(row):
        if "completion_time_ps" in row:
            return int(row["completion_time_ps"])
        text = row["completion_time"]
        if text.endswith("ps"):
            return int(text[:-2])
        if text.endswith("ns"):
            return int(text[:-2]) * 1000
        if text.endswith("us"):
            return int(text[:-2]) * 1000 * 1000
        if text.endswith("ms"):
            return int(text[:-2]) * 1000 * 1000 * 1000
        return int(text)

    times = [completion_time_ps(row) for row in rows]
    require(times == sorted(times), "{} export is not sorted by completion time".format(label))


def compare_axi_export_to_log(export_data, expected_log):
    write_file = export_data["summary"]["output"]["write_path"]
    read_file = export_data["summary"]["output"]["read_path"]
    meta_file = export_data["summary"]["output"]["meta_path"]
    writes = read_axi_export_table(write_file)
    reads = read_axi_export_table(read_file)

    require_completion_sorted(writes, "write")
    require_completion_sorted(reads, "read")

    require(os.path.exists(meta_file), "missing AXI export meta: {}".format(meta_file))
    with open(meta_file, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    require(len(writes) == 3200, "unexpected exported write count: {}".format(len(writes)))
    require(len(reads) == 3200, "unexpected exported read count: {}".format(len(reads)))
    require(len(expected_log["WR"]) == 3200, "unexpected expected write log count: {}".format(len(expected_log["WR"])))
    require(len(expected_log["RD"]) == 3200, "unexpected expected read log count: {}".format(len(expected_log["RD"])))

    from collections import Counter

    write_export = Counter(axi_compare_key(row) for row in writes)
    read_export = Counter(axi_compare_key(row) for row in reads)
    write_expected = Counter(expected_compare_key(row) for row in expected_log["WR"])
    read_expected = Counter(expected_compare_key(row) for row in expected_log["RD"])
    require(write_export == write_expected, "write export does not match VIP monitor log")
    require(read_export == read_expected, "read export does not match VIP monitor log")

    expected_ids = ["'h{:x}".format(i) for i in range(16)]
    write_ids = {normalize_sv_hex(v) for v in meta["unique_write_ids"]}
    read_ids = {normalize_sv_hex(v) for v in meta["unique_read_ids"]}
    write_count_by_id = {normalize_sv_hex(k): v for k, v in meta["write_count_by_id"].items()}
    read_count_by_id = {normalize_sv_hex(k): v for k, v in meta["read_count_by_id"].items()}
    require(write_ids == set(expected_ids), "unexpected write id set: {}".format(meta["unique_write_ids"]))
    require(read_ids == set(expected_ids), "unexpected read id set: {}".format(meta["unique_read_ids"]))
    for axi_id in expected_ids:
        require(write_count_by_id.get(axi_id) == 200, "write count mismatch for {}".format(axi_id))
        require(read_count_by_id.get(axi_id) == 200, "read count mismatch for {}".format(axi_id))
    require(meta["max_total_write_outstanding"] >= 16, "write outstanding pressure was not observed")
    require(meta["max_total_read_outstanding"] >= 16, "read outstanding pressure was not observed")
    require(meta["beat_count_mismatch_count"] == 0, "beat count mismatch in export meta")
    require(meta["incomplete_write_count"] == 0, "incomplete writes in export meta")
    require(meta["incomplete_read_count"] == 0, "incomplete reads in export meta")


def make_axi_config(prefix, top="axi_vip_fixture_top", edge="posedge", sample_point=None):
    config = {
        "awaddr": prefix + ".awaddr",
        "awid": prefix + ".awid",
        "awlen": prefix + ".awlen",
        "awsize": prefix + ".awsize",
        "awburst": prefix + ".awburst",
        "awvalid": prefix + ".awvalid",
        "awready": prefix + ".awready",
        "wdata": prefix + ".wdata",
        "wstrb": prefix + ".wstrb",
        "wlast": prefix + ".wlast",
        "wvalid": prefix + ".wvalid",
        "wready": prefix + ".wready",
        "bid": prefix + ".bid",
        "bresp": prefix + ".bresp",
        "bvalid": prefix + ".bvalid",
        "bready": prefix + ".bready",
        "araddr": prefix + ".araddr",
        "arid": prefix + ".arid",
        "arlen": prefix + ".arlen",
        "arsize": prefix + ".arsize",
        "arburst": prefix + ".arburst",
        "arvalid": prefix + ".arvalid",
        "arready": prefix + ".arready",
        "rid": prefix + ".rid",
        "rdata": prefix + ".rdata",
        "rresp": prefix + ".rresp",
        "rlast": prefix + ".rlast",
        "rvalid": prefix + ".rvalid",
        "rready": prefix + ".rready",
        "clock": top + ".clk",
        "rst_n": top + ".rst_n",
    }
    if edge is not None:
        config["edge"] = edge
    if sample_point is not None:
        config["sample_point"] = sample_point
    return config


def make_apb_config(edge=None, sample_point=None):
    config = {
        "paddr": "ai_complex_top.paddr",
        "pwdata": "ai_complex_top.pwdata",
        "prdata": "ai_complex_top.prdata",
        "pwrite": "ai_complex_top.pwrite",
        "penable": "ai_complex_top.penable",
        "psel": "ai_complex_top.psel",
        "clock": "ai_complex_top.clk",
        "rst_n": "ai_complex_top.rst_n",
    }
    if edge is not None:
        config["edge"] = edge
    if sample_point is not None:
        config["sample_point"] = sample_point
    return config


class AiRunner(object):
    def __init__(self, xdebug, fsdb, name):
        self.xdebug = xdebug
        self.fsdb = fsdb
        self.name = name
        self.home = tempfile.mkdtemp(prefix="xdebug_ai_")
        self.env = os.environ.copy()
        self.env["HOME"] = self.home
        self.sid = None
        self.rows = []
        self.duplicate_contract_violations = []

    def cleanup(self):
        if self.sid:
            self.query("session.kill", target={"session_id": self.sid}, expect_ok=True, allow_no_sid=True)
        shutil.rmtree(self.home, ignore_errors=True)
        require(not self.duplicate_contract_violations,
                "summary/data duplicate facts remain: {}".format(self.duplicate_contract_violations))

    def query(self, action, args=None, target=None, limits=None, expect_ok=True, allow_no_sid=False, timeout=60):
        req = {
            "api_version": "xdebug.v1",
            "action": action,
            "args": args or {},
        }
        if target is not None:
            req["target"] = target
        elif self.sid is not None:
            req["target"] = {"session_id": self.sid}
        elif not allow_no_sid:
            raise AssertionError("session must be opened before stateful query")
        request_limits = dict(limits or {})
        request_limits.setdefault("timeout_ms", DEFAULT_QUERY_TIMEOUT_MS)
        req["limits"] = request_limits

        start = time.time()
        log_progress("{}: query {} start timeout_ms={}".format(self.name, action, request_limits["timeout_ms"]))
        process_timeout = max(timeout, int(request_limits["timeout_ms"] / 1000) + 30)
        rc, out, err, _ = run_cmd([self.xdebug, "--json", "-"], cwd=REPO_ROOT, env=self.env,
                                  timeout=process_timeout, input_text=json.dumps(req) + "\n")
        elapsed_ms = int((time.time() - start) * 1000)
        try:
            data = json.loads(out)
        except Exception:
            raise AssertionError("non-json response for {} rc={} stdout={} stderr={}".format(action, rc, out, err))
        ok = bool(data.get("ok"))
        self.rows.append((self.name, action, rc, ok, elapsed_ms, data.get("meta", {}).get("elapsed_ms")))
        log_progress("{}: query {} done rc={} ok={} elapsed_ms={}".format(self.name, action, rc, ok, elapsed_ms))
        if expect_ok:
            require(rc == 0 and ok, "{} failed rc={} data={} stderr={}".format(action, rc, json.dumps(data, indent=2), err))
            if not action.startswith("session."):
                summary = data.get("summary", {})
                payload = data.get("data", {})
                duplicate_keys = sorted(
                    key for key, value in summary.items()
                    if key in payload and payload[key] == value
                )
                if duplicate_keys:
                    self.duplicate_contract_violations.append({"action": action, "keys": duplicate_keys})
        else:
            require(rc != 0 or not ok, "{} expected failure but passed".format(action))
        return data

    def open(self):
        self.query("session.open", target={"fsdb": self.fsdb}, expect_ok=False, allow_no_sid=True)
        data = self.query("session.open", target={"fsdb": self.fsdb}, args={"name": self.name}, expect_ok=True, allow_no_sid=True)
        session = data.get("session") or data.get("data", {}).get("session", {})
        self.sid = session["id"]
        self.query("session.open", target={"fsdb": self.fsdb}, args={"name": self.name}, expect_ok=False, allow_no_sid=True)
        return data


def run_nonaxi(xdebug, fsdb):
    r = AiRunner(xdebug, fsdb, "nonaxi")
    try:
        r.open()
        r.query("session.list", expect_ok=True, allow_no_sid=True)
        r.query("session.doctor", target={"session_id": r.sid})
        r.query("session.gc", expect_ok=True, allow_no_sid=True)

        scope = r.query("scope.list", args={"path": "ai_complex_top", "recursive": True}, limits={"max_rows": 8})
        require(scope["meta"]["truncated"] is True, "scope.list did not truncate")
        require("signals_preview" not in scope["data"], "scope.list generated redundant data.signals_preview")
        require("examples" not in scope["data"], "scope.list generated placeholder data.examples")

        v = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "clock": "ai_complex_top.clk", "time": "75ns", "format": "hex"})
        require(v["data"]["value"]["value"] == "'h22" and v["data"]["value"]["known"] is True, "unexpected sig_a value")
        xz = r.query("value.at", args={"signal": "ai_complex_top.xz_bus", "clock": "ai_complex_top.clk", "time": "95ns", "format": "binary"})
        require(xz["data"]["value"]["known"] is False, "xz_bus should be unknown")
        require("bits" in xz["data"]["value"] and "has_x" in xz["data"]["value"], "xz_bus lacks logic diagnostics")
        batch = r.query(
            "value.batch_at",
            args={"time": "95ns", "clock": "ai_complex_top.clk", "signals": ["ai_complex_top.sig_a", "ai_complex_top.xz_bus", "ai_complex_top.no_such"], "format": "hex"},
            expect_ok=True,
        )
        require(batch["summary"]["missing_count"] == 1 and batch["summary"]["unknown_count"] == 1, "batch missing/unknown mismatch")
        require(batch["summary"]["missing_by_reason"]["signal_not_found"] == 1, "batch missing reason mismatch")
        missing_rows = [row for row in batch["data"]["values"] if row["status"] != "ok"]
        require(missing_rows and missing_rows[0]["reason"], "batch missing row lacks reason")
        hint = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "clock": "ai_complex_top.clk", "time": "75ns", "format": "hex", "slice_hint": {"chunk_width": 4, "count": 2}})
        require(hint["data"]["xbit_hints"]["status"] == "ready", "xbit hints not generated")
        batch_hint = r.query(
            "value.batch_at",
            args={
                "signals": ["ai_complex_top.sig_a", "ai_complex_top.sig_b"],
                "clock": "ai_complex_top.clk",
                "time": "75ns",
                "format": "hex",
                "slice_hint": {"chunk_width": 4, "count": 2},
            },
        )
        hinted_rows = [
            row for row in batch_hint["data"]["values"]
            if row["signal"] == "ai_complex_top.sig_a"
        ]
        require(hinted_rows and hinted_rows[0]["xbit_hints"]["status"] == "ready", "batch xbit hints not generated")
        require(v["data"]["clock_context"] == batch_hint["data"]["clock_context"],
                "value.at and value.batch_at must share one clock bracket contract")
        unsupported = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "clock": "ai_complex_top.clk", "time": "75ns", "format": "array_indexed"})
        require(unsupported["summary"]["status"] == "unsupported_format", "array_indexed unsupported diagnostic missing")
        r.query("value.at", args={"signal": "ai_complex_top.no_such", "clock": "ai_complex_top.clk", "time": "10ns"}, expect_ok=False)

        created = r.query("list.create", args={"name": "basic"})
        require("summary" not in created["data"], "list.create generated nested data.summary")
        added_a = r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.sig_a"})
        require("summary" not in added_a["data"], "list.add generated nested data.summary")
        r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.sig_b"})
        r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.no_such"}, expect_ok=False)
        show = r.query("list.show", args={"name": "basic"})
        require(show["summary"]["signal_count"] == 2, "list.show count mismatch")
        require("count" not in show["data"], "list.show generated redundant data.count")
        values = r.query("list.value_at", args={"name": "basic", "clock": "ai_complex_top.clk", "time": "75ns", "format": "hex"})
        require("summary" not in values["data"], "list.value_at generated nested data.summary")
        validated = r.query("list.validate", args={"name": "basic"})
        require("all_found" in validated["summary"], "list.validate did not expose all_found at source")
        require("summary" not in validated["data"], "list.validate generated nested data.summary")
        diff = r.query("list.diff", args={"name": "basic", "time_range": {"begin": "0ns", "end": "120ns"}})
        require("ns" in diff["summary"]["diff_time"] or "ps" in diff["summary"]["diff_time"], "list.diff did not return time")
        require("time" not in diff["data"], "list.diff generated redundant data.time")
        list_export_dir = tempfile.mkdtemp(prefix="xdebug_list_export_")
        list_export = r.query("list.export", args={
            "name": "basic",
            "time_range": {"begin": "0ns", "end": "400ns"},
            "output": {"path": list_export_dir, "file_format": "u64bin"},
        })
        require("summary" not in list_export["data"], "list.export generated nested data.summary")
        manifest_file = list_export["summary"]["output"]["manifest_path"]
        require(os.path.exists(manifest_file), "missing list.export manifest")
        with open(manifest_file, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        require(manifest["format"] == "u64bin.v1", "unexpected list.export format")
        require(manifest["signal_count"] == 2, "unexpected exported signal count")
        require(manifest["row_count"] >= 2, "list.export did not write rows")
        for item in manifest["signals"]:
            require(os.path.exists(os.path.join(list_export_dir, item["file"])), "missing list.export signal file")
        image_file = os.path.join(list_export_dir, "wave.jpg")
        rc, out, err, _ = run_cmd([
            os.path.join(REPO_ROOT, "tools", "xwaveform"),
            "render",
            "--manifest", manifest_file,
            "--output", image_file,
            "--width", "4096",
            "--cursor-count", "32",
            "--json",
        ], cwd=REPO_ROOT, env=r.env, timeout=60)
        require(rc == 0, "xwaveform render failed\n{}\n{}".format(out, err))
        rendered = json.loads(out)
        require(rendered["width"] == 4096, "xwaveform did not render 4096px width")
        require(os.path.exists(rendered["image_file"]), "missing xwaveform JPG")
        require(os.path.exists(rendered["stats_file"]), "missing xwaveform stats")
        r.query("list.delete", args={"name": "basic", "index": 2})
        r.query("list.show", args={"name": "basic"})

        apb_cfg = os.path.join(NONAXI_DIR, "config", "apb0.json")
        r.query("apb.config.load", args={"name": "apb0", "config_path": apb_cfg})
        r.query("apb.config.list", args={"name": "apb0"})
        r.query("apb.query", args={"name": "apb0", "direction": "write"})
        r.query("apb.query", args={"name": "apb0", "direction": "read", "query": {"index": 1}})
        r.query("apb.cursor", args={"name": "apb0", "op": "begin", "direction": "all"})
        apb_window = r.query("apb.transfer_window", args={"name": "apb0", "time_range": {"begin": "200ns", "end": "400ns"}, "line_limit": 2})
        require(apb_window["summary"]["transaction_count"] >= 1, "APB window empty")

        apb_modes = [
            ("apb_default_negedge", make_apb_config(), "negedge", None),
            ("apb_dual", make_apb_config(edge="dual"), "dual", "before"),
            ("apb_pos_before", make_apb_config(edge="posedge", sample_point="before"), "posedge", "before"),
            ("apb_pos_after", make_apb_config(edge="posedge", sample_point="after"), "posedge", "after"),
        ]
        for name, config, expected_edge, expected_sample_point in apb_modes:
            loaded = r.query("apb.config.load", args={"name": name, "config": config})
            require(loaded["data"]["config"]["edge"] == expected_edge, "APB config edge mismatch for {}".format(name))
            if expected_sample_point is None:
                require("sample_point" not in loaded["data"]["config"],
                        "APB negedge config should not expose sample_point for {}".format(name))
            else:
                require(loaded["data"]["config"]["sample_point"] == expected_sample_point,
                        "APB config sample_point mismatch for {}".format(name))
            wr_count = r.query("apb.query", args={"name": name, "direction": "write"})
            rd_count = r.query("apb.query", args={"name": name, "direction": "read"})
            require(wr_count["summary"]["count"] >= 1, "APB write count empty for {}".format(name))
            require(rd_count["summary"]["count"] >= 1, "APB read count empty for {}".format(name))
        apb_before_first = r.query("apb.query", args={"name": "apb_pos_before", "direction": "write", "query": {"index": 1}})
        apb_after_first = r.query("apb.query", args={"name": "apb_pos_after", "direction": "write", "query": {"index": 1}})
        require(apb_before_first["data"]["transaction"]["time"] > apb_after_first["data"]["transaction"]["time"],
                "APB posedge before should observe the completion one edge later than after")

        event_cfg = os.path.join(NONAXI_DIR, "config", "event0.json")
        r.query("event.config.load", args={"name": "evt0", "config_path": event_cfg})
        r.query("event.config.list", args={"name": "evt0"})
        found = r.query("event.find", args={"name": "evt0", "expr": "vld && !rdy && payload_lo != 0", "time_range": {"begin": "0ns", "end": "200ns"}})
        require(len(found["data"]["events"]) == 1, "event.find did not return one event")
        require_clock_summary(found, "posedge")
        require("examples" not in found["data"], "event.find generated redundant data.examples")
        ge_threshold = r.query("event.find", args={"name": "evt0", "expr": "vld && !rdy && payload_lo >= 10", "time_range": {"begin": "0ns", "end": "200ns"}})
        require(len(ge_threshold["data"]["events"]) == 1, "event.find >= threshold failed")
        gt_literal = r.query("event.find", args={"name": "evt0", "expr": "vld && !rdy && payload_lo > 4'h9", "time_range": {"begin": "0ns", "end": "200ns"}})
        require(len(gt_literal["data"]["events"]) == 1, "event.find > SV literal failed")
        lt_threshold = r.query("event.find", args={"name": "evt0", "expr": "vld && !rdy && payload_lo < 10", "time_range": {"begin": "0ns", "end": "200ns"}})
        require(len(lt_threshold["data"]["events"]) == 0, "event.find < threshold matched unexpectedly")
        inline = r.query("event.find", args={
            "expr": "vld && !rdy",
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "rst_n": "ai_complex_top.rst_n",
            "signals": {
                "vld": "ai_complex_top.event_vld",
                "rdy": "ai_complex_top.event_rdy"
            },
            "time_range": {"begin": "0ns", "end": "200ns"},
            "mode": "last"
        })
        require(inline["summary"]["inline"] is True and len(inline["data"]["events"]) == 1, "inline event.find failed")
        require_clock_summary(inline, "posedge")
        require("examples" not in inline["data"], "inline event.find generated redundant data.examples")
        race_before = r.query("event.find", args={
            "expr": "!vld && !race",
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "sample_point": "before",
            "rst_n": "ai_complex_top.rst_n",
            "signals": {
                "vld": "ai_complex_top.event_vld",
                "race": "ai_complex_top.event_race"
            },
            "time_range": {"begin": "100ns", "end": "110ns"},
            "mode": "first"
        })
        require(len(race_before["data"]["events"]) == 1, "event.find posedge before did not observe old values")
        require_clock_summary(race_before, "posedge", "before")
        race_after = r.query("event.find", args={
            "expr": "vld && race",
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "sample_point": "after",
            "rst_n": "ai_complex_top.rst_n",
            "signals": {
                "vld": "ai_complex_top.event_vld",
                "race": "ai_complex_top.event_race"
            },
            "time_range": {"begin": "100ns", "end": "110ns"},
            "mode": "first"
        })
        require(len(race_after["data"]["events"]) == 1, "event.find posedge after did not observe new values")
        require_clock_summary(race_after, "posedge", "after")
        r.query("stream.config.load", args={"streams": [
            {
                "name": "race_before_stream",
                "signals": {
                    "clk": "ai_complex_top.clk",
                    "rst_n": "ai_complex_top.rst_n",
                    "vld": "ai_complex_top.event_vld",
                    "rdy": "ai_complex_top.event_race",
                    "payload": "ai_complex_top.event_payload",
                },
                "clock": "clk",
                "edge": "posedge",
                "sample_point": "before",
                "reset": "!rst_n",
                "vld": "vld",
                "rdy": "rdy",
                "data": "payload",
            },
            {
                "name": "race_after_stream",
                "signals": {
                    "clk": "ai_complex_top.clk",
                    "rst_n": "ai_complex_top.rst_n",
                    "vld": "ai_complex_top.event_vld",
                    "rdy": "ai_complex_top.event_race",
                    "payload": "ai_complex_top.event_payload",
                },
                "clock": "clk",
                "edge": "posedge",
                "sample_point": "after",
                "reset": "!rst_n",
                "vld": "vld",
                "rdy": "rdy",
                "data": "payload",
            },
        ]})
        stream_before = r.query("stream.query", args={
            "stream": "race_before_stream",
            "query": "summary",
            "time_range": {"begin": "100ns", "end": "110ns"},
        })
        stream_after = r.query("stream.query", args={
            "stream": "race_after_stream",
            "query": "summary",
            "time_range": {"begin": "100ns", "end": "110ns"},
        })
        require_clock_summary(stream_before, "posedge", "before", expected_clock="clk")
        require_clock_summary(stream_after, "posedge", "after", expected_clock="clk")
        require(stream_before["summary"]["transfer_count"] == 0,
                "stream posedge before should not observe same-edge event_vld/event_race transfer")
        require(stream_after["summary"]["transfer_count"] == 1,
                "stream posedge after should observe same-edge event_vld/event_race transfer")
        exported = r.query("event.export", args={"name": "evt0", "expr": "vld && !rdy", "time_range": {"begin": "0ns", "end": "200ns"}, "line_limit": 1})
        require(len(exported["data"]["events"]) == 1, "event.export limit failed")
        require_clock_summary(exported, "posedge")
        require("examples" not in exported["data"], "event.export generated redundant data.examples")
        event_vld = exported["data"]["events"][0]["signals"]["vld"]
        require("'h" in event_vld["value"] and event_vld["known"] is True, "event signal value is not normalized")
        agg = r.query("event.export", args={"name": "evt0", "expr": "vld && !rdy", "time_range": {"begin": "0ns", "end": "200ns"}, "aggregate": {"count": True, "group_by": ["payload_lo"], "events": False}})
        require("events" not in agg["data"] and agg["data"]["aggregate"]["count"] >= 1, "event aggregate count failed")
        require(agg["data"]["aggregate"]["group_count"] >= 1, "event aggregate group failed")
        no_xz = r.query("event.export", args={"name": "evt0", "expr": "xz != 0", "time_range": {"begin": "0ns", "end": "200ns"}, "line_limit": 5})
        require(len(no_xz["data"]["events"]) == 0, "x/z event comparison matched unexpectedly")
        no_xz_order = r.query("event.export", args={"name": "evt0", "expr": "xz >= 1", "time_range": {"begin": "0ns", "end": "200ns"}, "line_limit": 5})
        require(len(no_xz_order["data"]["events"]) == 0, "x/z event ordering comparison matched unexpectedly")
        r.query("event.find", args={"name": "evt0", "expr": "bad_alias", "time_range": {"begin": "0ns", "end": "200ns"}}, expect_ok=False)
        bad_clock_field = r.query("event.find", args={
            "expr": "vld",
            "clk": "ai_complex_top.clk",
            "signals": {"vld": "ai_complex_top.event_vld"},
            "time_range": {"begin": "0ns", "end": "200ns"},
        }, expect_ok=False)
        require(bad_clock_field["error"]["code"] == "INVALID_REQUEST", "legacy clk should be INVALID_REQUEST")
        require(bad_clock_field["error"]["invalid_arg"] == "args.clk", "legacy clk should identify args.clk")
        require("clock" in bad_clock_field["error"]["expected"], "legacy clk expected guidance should mention clock")

        checks = r.query("verify.conditions", args={
            "clock": "ai_complex_top.clk",
            "time": "95ns",
            "signals": {
                "a": "ai_complex_top.sig_a",
                "b": "ai_complex_top.sig_b",
                "xz": "ai_complex_top.xz_bus",
            },
            "conditions": [
                {"expr": "a == 'h22"},
                {"expr": "b == 'h22"},
                {"expr": "xz == 0"},
            ],
        })
        require(checks["summary"]["passed"] == 1 and checks["summary"]["failed"] == 1 and checks["summary"]["unknown"] == 1, "verify.conditions mismatch")
        require("results" not in checks["data"], "verify.conditions generated redundant data.results")
        require("checks" in checks["data"], "verify.conditions did not expose data.checks")

        expr = r.query("expr.eval_at", args={
            "clock": "ai_complex_top.clk",
            "time": "145ns",
            "expr": "valid && !ready",
            "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"},
        })
        require(expr["data"]["expr_value"] is True, "expr.eval_at expected true")
        expr_u = r.query("expr.eval_at", args={
            "clock": "ai_complex_top.clk",
            "time": "95ns",
            "expr": "xz != 0",
            "signals": {"xz": "ai_complex_top.xz_bus"},
        })
        require(expr_u["summary"]["known"] is False, "expr.eval_at xz should be unknown")

        win = r.query("window.verify", args={
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "sample_point": "after",
            "time_range": {"begin": "140ns", "end": "175ns"},
            "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"},
            "conditions": [{"expr": "valid && !ready", "mode": "always"}],
        })
        require(win["summary"]["all_passed"] is True, "window.verify expected pass")
        require_clock_summary(win, "posedge", "after")
        offset_win = r.query("window.verify", args={
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "sample_point": "before",
            "time_range": {"begin": "140ns", "end": "175ns"},
            "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"},
            "conditions": [{"expr": "valid && !ready", "mode": "eventually"}],
        })
        require(offset_win["summary"]["all_passed"] is True,
                "window.verify positive offset expected eventually pass: {}".format(json.dumps(offset_win, sort_keys=True)))
        require_clock_summary(offset_win, "posedge", "before")
        dual_win = r.query("window.verify", args={
            "clock": "ai_complex_top.clk",
            "edge": "dual",
            "time_range": {"begin": "140ns", "end": "160ns"},
            "signals": {"rst": "ai_complex_top.rst_n"},
            "conditions": [{"expr": "rst", "mode": "always"}],
        })
        require(dual_win["summary"]["sample_count"] >= 4, "dual edge window should sample both edges")
        require_clock_summary(dual_win, "dual")
        bad_window_field = r.query("window.verify", args={
            "clock": "ai_complex_top.clk",
            "posedge": True,
            "time_range": {"begin": "140ns", "end": "175ns"},
            "signals": {"valid": "ai_complex_top.hs_valid"},
            "conditions": [{"expr": "valid"}],
        }, expect_ok=False)
        require(bad_window_field["error"]["code"] == "INVALID_REQUEST", "legacy posedge should be INVALID_REQUEST")
        require(bad_window_field["error"]["invalid_arg"] == "args.posedge", "legacy posedge should identify args.posedge")

        changes = r.query("signal.changes", args={"signal": "ai_complex_top.sig_a", "time_range": {"begin": "0ns", "end": "120ns"}, "line_limit": 2})
        require(changes["meta"]["truncated"] is True, "signal.changes did not truncate")
        stab = r.query("signal.stability", args={"signal": "ai_complex_top.stable_sig", "time_range": {"begin": "0ns", "end": "400ns"}})
        require(stab["summary"]["stable"] is True, "stable_sig should be stable")
        require(stab["summary"]["actual_transition_count"] == 0,
                "stable initial value must not be counted as a transition")
        stats = r.query("signal.statistics", args={"signal": "ai_complex_top.hs_valid", "clock": "ai_complex_top.clk", "time_range": {"begin": "120ns", "end": "210ns"}, "line_limit": 1000})
        require_clock_summary(stats, "negedge")
        require(stats["summary"]["sample_count"] > 0 and stats["summary"]["known_count"] > 0, "signal.statistics did not sample")
        require("high_cycles" in stats["data"] and "low_cycles" in stats["data"], "signal.statistics missing cycle counts")
        offset_stats = r.query("signal.statistics", args={
            "signal": "ai_complex_top.hs_valid",
            "clock": "ai_complex_top.clk",
            "edge": "posedge",
            "sample_point": "before",
            "time_range": {"begin": "140ns", "end": "175ns"},
            "line_limit": 1000,
        })
        require_clock_summary(offset_stats, "posedge", "before")
        require(offset_stats["summary"]["sample_count"] > 0, "signal.statistics negative offset did not sample")
        anomaly = r.query("detect_abnormal", args={
            "signals": ["ai_complex_top.glitch_sig", "ai_complex_top.stuck_sig", "ai_complex_top.xz_bus"],
            "time_range": {"begin": "0ns", "end": "200ns"},
            "checks": [{"type": "glitch", "min_pulse_width": "1ns"}, {"type": "stuck", "min_duration": "100ns"}, {"type": "unknown_xz"}],
            "line_limit": 10,
        })
        require(anomaly["summary"]["finding_count"] >= 3, "detect_abnormal missing findings")
        require(any(f.get("type") == "glitch" for f in anomaly["data"].get("findings", [])), "glitch not detected")
        require(any(f.get("type") == "unknown_xz" and f.get("value", {}).get("value") == "8'hzz"
                    for f in anomaly["data"].get("findings", [])), "Z finding not preserved in detect_abnormal JSON")
        sampled_pulse = r.query("sampled_pulse.inspect", args={
            "clock": "ai_complex_top.clk",
            "valid": "ai_complex_top.glitch_sig",
            "payload": "ai_complex_top.sig_a",
            "edge": "posedge",
            "time_range": {"begin": "0ns", "end": "140ns"},
            "line_limit": 1,
        })
        require(sampled_pulse["summary"]["analysis_complete"] is True,
                "sampled_pulse analysis must cover the complete requested window")
        require(sampled_pulse["summary"]["returned_finding_count"] == 1,
                "sampled_pulse line_limit must only limit returned findings")
        require(sampled_pulse["summary"]["risk_count"] >= sampled_pulse["summary"]["returned_finding_count"],
                "sampled_pulse risk_count must count all analyzed findings")
        finding = sampled_pulse["data"]["findings"][0]
        raw_begin = time_ns(finding["raw_begin"])
        raw_end = time_ns(finding["raw_end"])
        require(time_ns(finding["previous_sample_edge"]) <= raw_begin,
                "sampled_pulse previous edge must bracket the raw pulse")
        require(time_ns(finding["next_sample_edge"]) >= raw_end,
                "sampled_pulse next edge must bracket the raw pulse")
        bad_checks = r.query("detect_abnormal", args={
            "signals": ["ai_complex_top.glitch_sig", "ai_complex_top.xz_bus"],
            "time_range": {"begin": "0ns", "end": "200ns"},
            "checks": ["unknown_xz", "glitch"],
        }, expect_ok=False)
        require(bad_checks["error"]["code"] == "INVALID_REQUEST", "string checks should return INVALID_REQUEST")
        require(bad_checks["error"]["invalid_arg"] == "args.checks[0]", "bad checks should expose invalid_arg")
        require(bad_checks["error"]["expected"] == "type \"object\"", "bad checks should explain expected object item")
        require(bad_checks["error"]["received_type"] == "string", "bad checks should expose received_type")
        require("correct_example" in bad_checks["error"], "bad checks should expose correct_example")
        bad_type = r.query("detect_abnormal", args={
            "signals": ["ai_complex_top.glitch_sig", "ai_complex_top.xz_bus"],
            "time_range": {"begin": "0ns", "end": "200ns"},
            "checks": [{"type": "unknown"}],
        }, expect_ok=False)
        require(bad_type["error"]["code"] == "INVALID_REQUEST", "unknown check type should return INVALID_REQUEST")
        require(bad_type["error"]["invalid_arg"] == "args.checks[0].type",
                "unknown check type should expose invalid type path")
        health = r.query("value.at", args={"signal": "ai_complex_top.clk", "clock": "ai_complex_top.clk", "time": "10ns"})
        require(health["ok"] is True, "session should remain healthy after invalid detect_abnormal checks")
        hs = r.query("handshake.inspect", args={
            "clock": "ai_complex_top.clk",
            "valid": "ai_complex_top.hs_valid",
            "ready": "ai_complex_top.hs_ready",
            "data": ["ai_complex_top.hs_data"],
            "time_range": {"begin": "120ns", "end": "210ns"},
            "rules": {"max_wait_cycles": 2, "check_data_stable_when_stalled": True},
        })
        require(hs["summary"]["max_stall_cycles"] >= 3 and hs["summary"]["data_stability_violations"] >= 1, "handshake.inspect mismatch")
        require_clock_summary(hs, "negedge")
        return r.rows
    finally:
        r.cleanup()


def run_axi(xdebug, fsdb):
    r = AiRunner(xdebug, fsdb, "axi")
    try:
        r.open()
        prefix = "axi_vip_fixture_top.axi_vip_if.master_if[0]"
        r.query("axi.config.load", args={"name": "axi0", "config": make_axi_config(prefix)})
        r.query("axi.config.list", args={"name": "axi0"})
        wr = r.query("axi.query", args={"name": "axi0", "direction": "write"})
        rd = r.query("axi.query", args={"name": "axi0", "direction": "read"})
        require(wr["summary"].get("count", 0) > 0 and rd["summary"].get("count", 0) > 0, "AXI query count is empty")
        compact_txn = r.query(
            "axi.query",
            args={"name": "axi0", "direction": "write", "query": {"index": 1}},
        )
        require("data" not in compact_txn["data"]["transaction"],
                "AXI compact transaction must omit beat data")
        verbose_txn = r.query(
            "axi.query",
            args={
                "name": "axi0",
                "direction": "write",
                "query": {"index": 1},
                "output": {"verbose": True},
            },
        )
        require("data" in verbose_txn["data"]["transaction"],
                "AXI verbose transaction must include beat data")

        axi_modes = [
            ("axi_default_negedge", make_axi_config(prefix, edge=None), "negedge", None),
            ("axi_dual", make_axi_config(prefix, edge="dual"), "dual", "before"),
            ("axi_pos_before", make_axi_config(prefix, edge="posedge", sample_point="before"), "posedge", "before"),
        ]
        for name, config, expected_edge, expected_sample_point in axi_modes:
            loaded = r.query("axi.config.load", args={"name": name, "config": config})
            require(loaded["data"]["config"]["edge"] == expected_edge, "AXI config edge mismatch for {}".format(name))
            if expected_sample_point is None:
                require("sample_point" not in loaded["data"]["config"],
                        "AXI negedge config should not expose sample_point for {}".format(name))
            else:
                require(loaded["data"]["config"]["sample_point"] == expected_sample_point,
                        "AXI config sample_point mismatch for {}".format(name))

        r.query("axi.cursor", args={"name": "axi0", "op": "begin", "direction": "all"})
        r.query("axi.cursor", args={"name": "axi0", "op": "next", "direction": "all"})
        tr = {"begin": "0ns", "end": "200ms"}
        pair_cold = r.query(
            "axi.request_response_pair",
            args={"name": "axi0", "time_range": tr, "line_limit": 10000},
        )
        require(pair_cold.get("meta", {}).get("truncated", False) is False and
                pair_cold["data"]["transaction_count"] < 10000,
                "AXI percentile oracle requires the complete transaction set")
        oracle_latencies = sorted(
            duration_fs(txn["latency"])
            for txn in pair_cold["data"]["transactions"]
        )
        require(oracle_latencies, "AXI percentile oracle transaction set is empty")

        latency = r.query("axi.analysis", args={"name": "axi0", "analysis": "latency", "direction": "all"})
        percentile_values = {}
        for percentile, percent in (("p50", 50), ("p95", 95), ("p99", 99)):
            require(percentile in latency["summary"],
                    "AXI latency analysis missing {}".format(percentile))
            percentile_values[percentile] = duration_fs(latency["summary"][percentile])
            rank = (percent * len(oracle_latencies) + 99) // 100
            expected = oracle_latencies[rank - 1]
            require(percentile_values[percentile] == expected,
                    "AXI {} nearest-rank mismatch: expected {}, got {}".format(
                        percentile, expected, percentile_values[percentile]))
        require(latency["summary"]["samples"] == len(oracle_latencies),
                "AXI latency sample count does not match transaction oracle")
        require({"time", "response_time", "addr", "id", "is_write"} <= set(latency["data"]["slowest"]),
                "AXI latency analysis missing slowest transaction anchor")
        slowest = latency["data"]["slowest"]
        slowest_latency = duration_fs(slowest["response_time"]) - duration_fs(slowest["time"])
        require(slowest_latency == duration_fs(latency["summary"]["max"]),
                "AXI slowest transaction latency must equal summary.max")
        require(slowest_latency == oracle_latencies[-1],
                "AXI slowest transaction must match the transaction oracle maximum")
        r.query("axi.analysis", args={"name": "axi0", "analysis": "osd", "direction": "all"})

        require(pair_cold["data"]["transaction_count"] > 0, "AXI request_response_pair empty")
        require(all("data" not in txn and "wstrb" not in txn
                    for txn in pair_cold["data"]["transactions"]),
                "AXI compact request_response_pair must omit beat payload")
        pair_verbose = r.query(
            "axi.request_response_pair",
            args={"name": "axi0", "time_range": tr, "line_limit": 20,
                  "output": {"verbose": True}},
        )
        require(any("data" in txn for txn in pair_verbose["data"]["transactions"]),
                "AXI verbose request_response_pair must include beat payload")
        pair_cache = r.query("axi.request_response_pair", args={"name": "axi0", "time_range": tr, "line_limit": 20})
        require(pair_cache["data"]["transaction_count"] > 0, "AXI cached request_response_pair empty")
        lat = r.query("axi.latency_outlier", args={"name": "axi0", "time_range": tr, "line_limit": 5})
        require(lat["data"]["outlier_count"] > 0, "AXI latency_outlier empty")
        require(all("data" not in txn and "wstrb" not in txn
                    for txn in lat["data"]["outliers"]),
                "AXI compact latency_outlier must omit beat payload")
        lat_verbose = r.query(
            "axi.latency_outlier",
            args={"name": "axi0", "time_range": tr, "line_limit": 5,
                  "output": {"verbose": True}},
        )
        require(any("data" in txn for txn in lat_verbose["data"]["outliers"]),
                "AXI verbose latency_outlier must include beat payload")
        osd = r.query("axi.outstanding_timeline", args={"name": "axi0", "time_range": tr, "line_limit": 20})
        require(osd["summary"]["sample_count"] > 0, "AXI outstanding_timeline empty")
        stall = r.query("axi.channel_stall", args={"name": "axi0", "channel": "r", "time_range": tr, "rules": {"max_wait_cycles": 2}, "line_limit": 1000000})
        require(stall["summary"]["sample_count"] > 0, "AXI channel_stall did not sample")

        expected_log = parse_axi_expected_log(AXI_SIM_LOG)
        export_dir = tempfile.mkdtemp(prefix="xdebug_axi_export_")
        export_prefix = os.path.join(export_dir, "axi0_full")
        exported = r.query(
            "axi.export",
            args={
                "name": "axi0",
                "time_range": tr,
                "output": {"path": export_prefix, "file_format": "tsv"},
            },
            timeout=240,
        )
        compare_axi_export_to_log(exported, expected_log)

        windowed = r.query(
            "axi.export",
            args={
                "name": "axi0",
                "time_range": {"begin": "1us", "end": "200ms"},
                "output": {"path": os.path.join(export_dir, "axi0_windowed"), "file_format": "tsv"},
            },
            timeout=240,
        )
        require(windowed["summary"]["write_count"] <= exported["summary"]["write_count"], "windowed write count exceeds full export")
        require(windowed["summary"]["read_count"] <= exported["summary"]["read_count"], "windowed read count exceeds full export")
        return r.rows
    finally:
        r.cleanup()


def print_rows(rows):
    print("\n=== xdebug waveform performance ===")
    print("{:<8} {:<32} {:>4} {:>5} {:>10} {:>10}".format("wave", "action", "rc", "ok", "wall_ms", "tool_ms"))
    for wave, action, rc, ok, wall_ms, tool_ms in rows:
        print("{:<8} {:<32} {:>4} {:>5} {:>10} {:>10}".format(wave, action, rc, str(ok), wall_ms, str(tool_ms)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xdebug", default=os.path.join(REPO_ROOT, "tools", "xdebug"))
    parser.add_argument("--fsdb", default=NONAXI_FSDB)
    parser.add_argument("--axi-fsdb", default=AXI_FSDB)
    parser.add_argument("--mode", choices=["all", "nonaxi", "axi"], default="all")
    args = parser.parse_args()

    rows = []
    if args.mode in ("all", "nonaxi"):
        rows.extend(run_nonaxi(os.path.abspath(args.xdebug), os.path.abspath(args.fsdb)))
    if args.mode in ("all", "axi"):
        rows.extend(run_axi(os.path.abspath(args.xdebug), os.path.abspath(args.axi_fsdb)))
    print_rows(rows)
    print("\nPASS: xdebug complex waveform validation completed")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAIL: {}".format(e), file=sys.stderr)
        sys.exit(1)
