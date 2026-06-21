#!/usr/bin/env python3
import argparse
import json
import os
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


def run_cmd(cmd, cwd=None, env=None, timeout=120, input_text=None):
    start = time.time()
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


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def make_axi_config(prefix, top="axi_vip_fixture_top"):
    return {
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
        "clk": top + ".clk",
        "rst_n": top + ".rst_n",
        "edge": "posedge",
    }


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

    def cleanup(self):
        try:
            self.query("session.kill", args={"id": "all"}, expect_ok=True, allow_no_sid=True)
        except Exception:
            pass
        shutil.rmtree(self.home, ignore_errors=True)

    def query(self, action, args=None, target=None, limits=None, expect_ok=True, allow_no_sid=False, timeout=60):
        req = {
            "api_version": "xdebug.v1",
            "action": action,
            "args": args or {},
            "output": {"verbosity": "full"},
        }
        if target is not None:
            req["target"] = target
        elif self.sid is not None:
            req["target"] = {"session_id": self.sid}
        elif not allow_no_sid:
            raise AssertionError("session must be opened before stateful query")
        if limits is not None:
            req["limits"] = limits

        start = time.time()
        rc, out, err, _ = run_cmd([self.xdebug, "--json", "-"], cwd=REPO_ROOT, env=self.env,
                                  timeout=timeout, input_text=json.dumps(req) + "\n")
        elapsed_ms = int((time.time() - start) * 1000)
        try:
            data = json.loads(out)
        except Exception:
            raise AssertionError("non-json response for {} rc={} stdout={} stderr={}".format(action, rc, out, err))
        ok = bool(data.get("ok"))
        self.rows.append((self.name, action, rc, ok, elapsed_ms, data.get("meta", {}).get("elapsed_ms")))
        if expect_ok:
            require(rc == 0 and ok, "{} failed rc={} data={} stderr={}".format(action, rc, json.dumps(data, indent=2), err))
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


def build_nonaxi():
    rc, out, err, _ = run_cmd(["make", "clean"], cwd=NONAXI_DIR, timeout=60)
    require(rc == 0, "non-AXI clean failed\n{}\n{}".format(out, err))
    rc, out, err, _ = run_cmd(["make"], cwd=NONAXI_DIR, timeout=120)
    require(rc == 0, "non-AXI wave build failed\n{}\n{}".format(out, err))
    require(os.path.exists(NONAXI_FSDB), "missing non-AXI fsdb: {}".format(NONAXI_FSDB))


def build_axi():
    env = os.environ.copy()
    env["PWD"] = AXI_DIR
    required = ["AXI_REFERENCE_ROOT", "SVT_VIP_INCDIR", "SVT_VIP_SRCDIR"]
    missing = [name for name in required if not env.get(name)]
    require(
        not missing,
        "AXI fixture requires environment variables: {}".format(", ".join(missing)),
    )
    rc, out, err, _ = run_cmd(
        [
            "make", "run",
            "SEED=7",
        ],
        cwd=AXI_DIR,
        env=env,
        timeout=600,
    )
    require(rc == 0, "AXI wave build failed\n{}\n{}".format(out[-4000:], err[-4000:]))
    require(os.path.exists(AXI_FSDB), "missing AXI fsdb: {}".format(AXI_FSDB))


def run_nonaxi(xdebug, fsdb):
    r = AiRunner(xdebug, fsdb, "nonaxi")
    try:
        r.open()
        r.query("session.list", expect_ok=True, allow_no_sid=True)
        r.query("session.doctor", args={"session_id": r.sid}, target={"session_id": r.sid})
        r.query("session.gc", expect_ok=True, allow_no_sid=True)

        scope = r.query("scope.list", args={"path": "ai_complex_top", "recursive": True}, limits={"max_rows": 8})
        require(scope["meta"]["truncated"] is True, "scope.list did not truncate")

        v = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "time": "75ns", "format": "hex"})
        require(v["data"]["value"]["value"] == "'h22" and v["data"]["value"]["known"] is True, "unexpected sig_a value")
        xz = r.query("value.at", args={"signal": "ai_complex_top.xz_bus", "time": "95ns", "format": "binary"})
        require(xz["data"]["value"]["known"] is False, "xz_bus should be unknown")
        require("bits" in xz["data"]["value"] and "has_x" in xz["data"]["value"], "xz_bus lacks logic diagnostics")
        batch = r.query(
            "value.batch_at",
            args={"time": "95ns", "signals": ["ai_complex_top.sig_a", "ai_complex_top.xz_bus", "ai_complex_top.no_such"], "format": "hex"},
            expect_ok=True,
        )
        require(batch["summary"]["missing_count"] == 1 and batch["summary"]["unknown_count"] == 1, "batch missing/unknown mismatch")
        require(batch["summary"]["missing_by_reason"]["signal_not_found"] == 1, "batch missing reason mismatch")
        missing_rows = [row for row in batch["data"]["values"] if row["status"] != "ok"]
        require(missing_rows and missing_rows[0]["reason"], "batch missing row lacks reason")
        hint = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "time": "75ns", "format": "hex", "slice_hint": {"chunk_width": 4, "count": 2}})
        require(hint["data"]["xbit_hints"]["status"] == "ready", "xbit hints not generated")
        unsupported = r.query("value.at", args={"signal": "ai_complex_top.sig_a", "time": "75ns", "format": "array_indexed"})
        require(unsupported["data"]["status"] == "unsupported_format", "array_indexed unsupported diagnostic missing")
        r.query("value.at", args={"signal": "ai_complex_top.no_such", "time": "10ns"}, expect_ok=False)

        r.query("list.create", args={"name": "basic"})
        r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.sig_a"})
        r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.sig_b"})
        r.query("list.add", args={"name": "basic", "signal": "ai_complex_top.no_such"}, expect_ok=False)
        show = r.query("list.show", args={"name": "basic"})
        require(show["summary"]["signal_count"] == 2, "list.show count mismatch")
        r.query("list.value_at", args={"name": "basic", "time": "75ns", "format": "hex"})
        r.query("list.validate", args={"name": "basic"})
        diff = r.query("list.diff", args={"name": "basic", "begin": "0ns", "end": "120ns"})
        require("ns" in diff["summary"]["diff_time"] or "ps" in diff["summary"]["diff_time"], "list.diff did not return time")
        r.query("list.delete", args={"name": "basic", "index": "2"})
        r.query("list.show", args={"name": "basic"})

        apb_cfg = os.path.join(NONAXI_DIR, "config", "apb0.json")
        r.query("apb.config.load", args={"name": "apb0", "config_path": apb_cfg})
        r.query("apb.config.list", args={"name": "apb0"})
        r.query("apb.query", args={"name": "apb0", "direction": "wr"})
        r.query("apb.query", args={"name": "apb0", "direction": "rd", "num": 1})
        r.query("apb.cursor", args={"name": "apb0", "op": "begin", "direction": "all"})
        apb_window = r.query("apb.transfer_window", args={"name": "apb0", "time_range": {"begin": "200ns", "end": "400ns"}, "limit": 2})
        require(apb_window["data"]["transaction_count"] >= 1, "APB window empty")

        event_cfg = os.path.join(NONAXI_DIR, "config", "event0.json")
        r.query("event.config.load", args={"name": "evt0", "config_path": event_cfg})
        r.query("event.config.list", args={"name": "evt0"})
        found = r.query("event.find", args={"name": "evt0", "expr": "vld && !rdy && payload_lo != 0", "time_range": {"begin": "0ns", "end": "200ns"}})
        require(len(found["data"]["events"]) == 1, "event.find did not return one event")
        inline = r.query("event.find", args={
            "expr": "vld && !rdy",
            "clk": "ai_complex_top.clk",
            "rst_n": "ai_complex_top.rst_n",
            "signals": {
                "vld": "ai_complex_top.event_vld",
                "rdy": "ai_complex_top.event_rdy"
            },
            "time_range": {"begin": "0ns", "end": "200ns"},
            "mode": "last"
        })
        require(inline["summary"]["inline"] is True and len(inline["data"]["events"]) == 1, "inline event.find failed")
        exported = r.query("event.export", args={"name": "evt0", "expr": "vld && !rdy", "time_range": {"begin": "0ns", "end": "200ns"}, "limit": 1})
        require(len(exported["data"]["events"]) == 1, "event.export limit failed")
        event_vld = exported["data"]["events"][0]["signals"]["vld"]
        require("'h" in event_vld["value"] and event_vld["known"] is True, "event signal value is not normalized")
        agg = r.query("event.export", args={"name": "evt0", "expr": "vld && !rdy", "time_range": {"begin": "0ns", "end": "200ns"}, "aggregate": {"count": True, "group_by": ["payload_lo"], "events": False}})
        require("events" not in agg["data"] and agg["data"]["aggregate"]["count"] >= 1, "event aggregate count failed")
        require(agg["data"]["aggregate"]["group_count"] >= 1, "event aggregate group failed")
        no_xz = r.query("event.export", args={"name": "evt0", "expr": "xz != 0", "time_range": {"begin": "0ns", "end": "200ns"}, "limit": 5})
        require(len(no_xz["data"]["events"]) == 0, "x/z event comparison matched unexpectedly")
        r.query("event.find", args={"name": "evt0", "expr": "bad_alias", "time_range": {"begin": "0ns", "end": "200ns"}}, expect_ok=False)

        checks = r.query("verify.conditions", args={
            "time": "95ns",
            "conditions": [
                {"signal": "ai_complex_top.sig_a", "op": "==", "value": "'h22"},
                {"signal": "ai_complex_top.sig_b", "op": "==", "value": "'h22"},
                {"signal": "ai_complex_top.xz_bus", "op": "==", "value": "0"},
            ],
        })
        require(checks["summary"]["passed"] == 1 and checks["summary"]["failed"] == 1 and checks["summary"]["unknown"] == 1, "verify.conditions mismatch")

        expr = r.query("expr.eval_at", args={
            "time": "145ns",
            "expr": "valid && !ready",
            "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"},
        })
        require(expr["data"]["expr_value"] is True, "expr.eval_at expected true")
        expr_u = r.query("expr.eval_at", args={
            "time": "95ns",
            "expr": "xz != 0",
            "signals": {"xz": "ai_complex_top.xz_bus"},
        })
        require(expr_u["summary"]["known"] is False, "expr.eval_at xz should be unknown")

        win = r.query("window.verify", args={
            "clock": "ai_complex_top.clk",
            "sampling": "posedge",
            "time_range": {"begin": "140ns", "end": "175ns"},
            "conditions": [{"expr": "valid && !ready", "signals": {"valid": "ai_complex_top.hs_valid", "ready": "ai_complex_top.hs_ready"}, "mode": "always"}],
        })
        require(win["summary"]["all_passed"] is True, "window.verify expected pass")

        changes = r.query("signal.changes", args={"signal": "ai_complex_top.sig_a", "time_range": {"begin": "0ns", "end": "120ns"}, "limit": 2})
        require(changes["data"]["truncated"] is True, "signal.changes did not truncate")
        stab = r.query("signal.stability", args={"signal": "ai_complex_top.stable_sig", "time_range": {"begin": "0ns", "end": "400ns"}})
        require(stab["data"]["stable"] is True, "stable_sig should be stable")
        trend = r.query("signal.trend", args={"signal": "ai_complex_top.counter_nonmono", "clock": "ai_complex_top.clk", "time_range": {"begin": "40ns", "end": "110ns"}})
        require(trend["data"]["monotonic"] == "none", "counter_nonmono should be non-monotonic")
        stats = r.query("signal.statistics", args={"signal": "ai_complex_top.hs_valid", "clock": "ai_complex_top.clk", "time_range": {"begin": "120ns", "end": "210ns"}, "max_samples": 1000})
        require(stats["data"]["sample_count"] > 0 and stats["data"]["known_count"] > 0, "signal.statistics did not sample")
        require("high_cycles" in stats["data"] and "low_cycles" in stats["data"], "signal.statistics missing cycle counts")
        inspect = r.query("inspect_signal", args={"signal": "ai_complex_top.glitch_sig", "time_range": {"begin": "80ns", "end": "120ns"}, "glitch_threshold": "1ns"})
        require(inspect["data"]["glitch"]["count"] >= 1, "glitch not detected")
        anomaly = r.query("detect_anomaly", args={
            "signals": ["ai_complex_top.glitch_sig", "ai_complex_top.stuck_sig", "ai_complex_top.xz_bus"],
            "time_range": {"begin": "0ns", "end": "200ns"},
            "checks": [{"type": "glitch", "min_pulse_width": "1ns"}, {"type": "stuck", "min_duration": "100ns"}, {"type": "unknown_xz"}],
            "max_findings": 10,
        })
        require(anomaly["summary"]["finding_count"] >= 3, "detect_anomaly missing findings")
        hs = r.query("handshake.inspect", args={
            "clock": "ai_complex_top.clk",
            "valid": "ai_complex_top.hs_valid",
            "ready": "ai_complex_top.hs_ready",
            "data": ["ai_complex_top.hs_data"],
            "time_range": {"begin": "120ns", "end": "210ns"},
            "rules": {"max_wait_cycles": 2, "check_data_stable_when_stalled": True},
        })
        require(hs["summary"]["max_stall_cycles"] >= 3 and hs["data"]["data_stability_violations"] >= 1, "handshake.inspect mismatch")
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
        wr = r.query("axi.query", args={"name": "axi0", "direction": "wr"})
        rd = r.query("axi.query", args={"name": "axi0", "direction": "rd"})
        require(wr["data"].get("count", 0) > 0 and rd["data"].get("count", 0) > 0, "AXI query count is empty")
        r.query("axi.query", args={"name": "axi0", "direction": "wr", "num": 1})
        r.query("axi.cursor", args={"name": "axi0", "op": "begin", "direction": "all"})
        r.query("axi.cursor", args={"name": "axi0", "op": "next", "direction": "all"})
        r.query("axi.analysis", args={"name": "axi0", "analysis": "latency", "direction": "all"})
        r.query("axi.analysis", args={"name": "axi0", "analysis": "osd", "direction": "all"})

        tr = {"begin": "0ns", "end": "20000us"}
        pair_cold = r.query("axi.request_response_pair", args={"name": "axi0", "time_range": tr, "limit": 20})
        require(pair_cold["data"]["transaction_count"] > 0, "AXI request_response_pair empty")
        pair_cache = r.query("axi.request_response_pair", args={"name": "axi0", "time_range": tr, "limit": 20})
        require(pair_cache["data"]["transaction_count"] > 0, "AXI cached request_response_pair empty")
        lat = r.query("axi.latency_outlier", args={"name": "axi0", "time_range": tr, "top_n": 5, "limit": 200})
        require(lat["data"]["outlier_count"] > 0, "AXI latency_outlier empty")
        osd = r.query("axi.outstanding_timeline", args={"name": "axi0", "time_range": tr, "limit": 20})
        require(osd["data"]["sample_count"] > 0, "AXI outstanding_timeline empty")
        stall = r.query("axi.channel_stall", args={"name": "axi0", "channel": "r", "time_range": tr, "rules": {"max_wait_cycles": 2}, "max_samples": 1000000})
        require(stall["data"]["sample_count"] > 0, "AXI channel_stall did not sample")
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
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    if not args.skip_build:
        if args.mode in ("all", "nonaxi"):
            build_nonaxi()
        if args.mode in ("all", "axi"):
            build_axi()

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
