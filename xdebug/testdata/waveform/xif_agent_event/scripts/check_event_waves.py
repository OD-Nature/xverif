#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[3]


def query(binary, home, action, args=None, target=None, expect_ok=True):
    request = {"api_version": "xdebug.v1", "action": action, "args": args or {},
               "output": {"verbosity": "full"}}
    if target is not None:
        request["target"] = target
    env = os.environ.copy()
    env["HOME"] = str(home)
    proc = subprocess.run(
        [binary, "--json", "-"],
        input=json.dumps(request) + "\n",
        universal_newlines=True,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "{} returned non-JSON stdout: {!r}; stderr: {!r}".format(
                action, proc.stdout[:500], proc.stderr[:500]
            )
        ) from exc
    if expect_ok and (proc.returncode != 0 or not result.get("ok")):
        raise AssertionError("{} failed: {} {}".format(action, result, proc.stderr))
    if not expect_ok and result.get("ok"):
        raise AssertionError("{} unexpectedly passed".format(action))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xdebug", default=str(REPO_ROOT / "tools" / "xdebug"))
    parser.add_argument("--fsdb", default=str(ROOT / "out" / "waves" / "xif_event_multi_if_test.fsdb"))
    args = parser.parse_args()
    fsdb = Path(args.fsdb).resolve()
    if not fsdb.exists():
        raise RuntimeError("missing FSDB: {}".format(fsdb))

    home = Path(tempfile.mkdtemp(prefix="xdebug-event-check-"))
    session = "xif_event_check"
    try:
        query(args.xdebug, home, "session.open",
              {"name": session}, {"fsdb": str(fsdb)})
        configs = {
            "rdy": "event_rdy.json",
            "bp": "event_bp.json",
            "none": "event_none.json",
            "pair_master": "event_pair_master.json",
            "pair_slave": "event_pair_slave.json",
            "xz": "event_xz.json",
        }
        for name, config in configs.items():
            query(args.xdebug, home, "event.config.load",
                  {"name": name, "config_path": str(ROOT / config)},
                  {"session_id": session})

        def export(name, expr):
            return query(args.xdebug, home, "event.export",
                         {"name": name, "expr": expr},
                         {"session_id": session})["data"]["events"]

        rdy = export("rdy", "vld && rdy")
        bp = export("bp", "vld && !bp")
        none = export("none", "vld")
        pair_master = export("pair_master", "vld && rdy")
        pair_slave = export("pair_slave", "vld && rdy")
        assert rdy and bp and none and pair_master and pair_slave
        assert not export("xz", "vld && data != 0")
        query(args.xdebug, home, "event.find",
              {"name": "rdy", "expr": "vld && missing_alias"},
              {"session_id": session}, expect_ok=False)
        print("PASS: xdebug event checks rdy={} bp={} none={} pair_master={} pair_slave={}".format(
            len(rdy), len(bp), len(none), len(pair_master), len(pair_slave)))
    finally:
        try:
            query(args.xdebug, home, "session.kill", {"id": "all"})
        except Exception:
            pass
        shutil.rmtree(str(home), ignore_errors=True)


if __name__ == "__main__":
    main()
