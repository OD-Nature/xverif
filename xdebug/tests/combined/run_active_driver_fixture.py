#!/usr/bin/env python3
"""Live combined regression tests for trace.active_driver.

Requires NPI license.  Without license, all tests are skipped (exit 0).
Set XDEBUG_REQUIRE_NPI=1 to make license-unavailable a hard failure.

Usage:
  make -C xdebug combined-test
  XDEBUG_REQUIRE_NPI=1 make -C xdebug combined-test
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# When run via "make -C xdebug combined-test", CWD is the xdebug directory
_XDEBUG_CANDIDATES = [
    os.environ.get("XDEBUG", ""),
    str(Path.cwd() / "xdebug"),           # CWD = xdebug/
    str(REPO_ROOT / "tools" / "xdebug"),   # repo root tools/
    str(REPO_ROOT / "xdebug" / "xdebug"),   # xdebug/xdebug binary
]
XDEBUG = next((c for c in _XDEBUG_CANDIDATES if c and Path(c).is_file()), "xdebug")
REQUIRE_NPI = os.environ.get("XDEBUG_REQUIRE_NPI", "") == "1"

ACTIVE_DRIVER_DIR = Path(__file__).resolve().parent.parent.parent / "testdata" / "combined" / "active_driver"
IF_PORT_ROOT_DIR = Path(__file__).resolve().parent.parent.parent / "testdata" / "combined" / "interface_port_root"

ACTIVE_DRIVER_DAIDIR = str(ACTIVE_DRIVER_DIR / "out" / "simv.daidir")
ACTIVE_DRIVER_FSDB = str(ACTIVE_DRIVER_DIR / "out" / "waves.fsdb")
IF_PORT_ROOT_DAIDIR = str(IF_PORT_ROOT_DIR / "out" / "simv.daidir")
IF_PORT_ROOT_FSDB = str(IF_PORT_ROOT_DIR / "out" / "waves.fsdb")

failed = 0
passed = 0
skipped = 0


def _has_license_issue(output: str) -> bool:
    """Check if output contains license-related errors."""
    lower = output.lower()
    return any(phrase in lower for phrase in [
        "npi_init_failed",
        "failed to check out license",
        "license checkout failed",
        "npi initialization failed",
        "cannot check out license",
        "npi_init failed",
    ])


def run_xdebug(request_body: str) -> "tuple[int, str]":
    """Run xdebug --json with the given request, return (rc, stdout)."""
    proc = subprocess.run(
        [XDEBUG, "--json", "-"],
        input=request_body,
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = proc.stdout + proc.stderr
    return proc.returncode, combined


def open_session(name: str, daidir: str, fsdb: str) -> "tuple[str, str]":
    """Open a session, returns (session_id, error_message or "")."""
    req = json.dumps({
        "api_version": "xdebug.v1",
        "action": "session.open",
        "target": {"daidir": daidir, "fsdb": fsdb},
        "args": {"name": name, "reopen": True},
        "output": {"format": "json", "verbosity": "compact"},
    })
    _, out = run_xdebug(req)

    if _has_license_issue(out):
        return name, out

    # Try to extract the last complete JSON object from the output.
    # xdebug --json emits pretty-printed JSON that starts at a top-level '{'.
    # Use bracket matching to find the corresponding '}'.
    resp = None
    stripped = out.strip()
    # Find the first '{' that starts the main JSON response
    start = stripped.find("{")
    if start >= 0:
        # Bracket-match to find the matching closing '}'
        depth = 0
        end = -1
        for i in range(start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end >= 0:
            try:
                candidate = json.loads(stripped[start:end + 1])
                if isinstance(candidate, dict) and "api_version" in candidate:
                    resp = candidate
            except (json.JSONDecodeError, ValueError):
                pass

    # Fallback: try line-by-line for compact single-line JSON
    if resp is None:
        for line in reversed(stripped.split("\n")):
            line = line.strip()
            if not line:
                continue
            try:
                candidate = json.loads(line)
                if isinstance(candidate, dict) and "api_version" in candidate:
                    resp = candidate
                    break
            except (json.JSONDecodeError, ValueError):
                continue

    if resp is None:
        return name, out

    if not resp.get("ok"):
        err = resp.get("error", {})
        return name, err.get("code", "UNKNOWN") + ": " + err.get("message", str(resp))

    # Extract session_id — may be at session.* or data.session.*
    session = resp.get("session", {}) or resp.get("data", {}).get("session", {})
    sid = session.get("session_id") or session.get("id") or name
    return str(sid), ""


def do_active_driver(session_id: str, signal: str, requested_time: str,
                     extra_args: dict = None) -> "tuple[int, str, dict]":
    """Run trace.active_driver, returns (rc, raw_output, json_response)."""
    args = {
        "signal": signal,
        "requested_time": requested_time,
    }
    if extra_args:
        args.update(extra_args)
    req = json.dumps({
        "api_version": "xdebug.v1",
        "action": "trace.active_driver",
        "target": {"session_id": session_id},
        "args": args,
        "output": {"format": "json", "verbosity": "compact"},
    })
    rc, out = run_xdebug(req)
    resp = None
    # Bracket-match to extract the outermost JSON object
    stripped = out.strip()
    start = stripped.find("{")
    if start >= 0:
        depth = 0
        end = -1
        for i in range(start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end >= 0:
            try:
                candidate = json.loads(stripped[start:end + 1])
                if isinstance(candidate, dict) and "api_version" in candidate:
                    resp = candidate
            except (json.JSONDecodeError, ValueError):
                pass
    # Fallback: line-by-line
    if resp is None:
        for line in reversed(stripped.split("\n")):
            line = line.strip()
            if not line:
                continue
            try:
                candidate = json.loads(line)
                if isinstance(candidate, dict) and "api_version" in candidate:
                    resp = candidate
                    break
            except (json.JSONDecodeError, ValueError):
                continue
    if resp is None:
        return rc, out, {}
    return rc, out, resp


def check(name: str, session_id: str, signal: str, requested_time: str,
          checks: list, extra_args: dict = None):
    """Run a check case. Each check is a callable(resp, raw) -> bool."""
    global failed, passed, skipped
    rc, raw, resp = do_active_driver(session_id, signal, requested_time, extra_args)
    if not resp:
        if _has_license_issue(raw):
            print(f"SKIP: {name} — NPI license unavailable")
            if REQUIRE_NPI:
                global _hard_fail
                failed += 1
                print(f"  FAIL (hard): XDEBUG_REQUIRE_NPI=1 but got license error")
            else:
                skipped += 1
            return
        print(f"FAIL: {name} — no JSON response")
        print(f"  raw output (last 500 chars): {raw[-500:]}")
        failed += 1
        return

    if not resp.get("ok", False):
        err = resp.get("error", {})
        if _has_license_issue(err.get("code", "") + err.get("message", "")):
            print(f"SKIP: {name} — NPI license unavailable")
            if REQUIRE_NPI:
                failed += 1
                print(f"  FAIL (hard): XDEBUG_REQUIRE_NPI=1 but got license error")
            else:
                skipped += 1
            return
        print(f"FAIL: {name} — request failed: {err}")
        failed += 1
        return

    all_ok = True
    for check_fn in checks:
        ok, msg = check_fn(resp, raw)
        if not ok:
            print(f"FAIL: {name} — {msg}")
            all_ok = False

    if all_ok:
        print(f"PASS: {name}")
        passed += 1
    else:
        failed += 1


# ─── check helpers ───────────────────────────────────────────────────────────

def has_field(path: str, expected=None):
    """Check that resp has a field at dotted path, optionally matching value."""
    def fn(resp, raw):
        obj = resp
        for key in path.split("."):
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                return False, f"missing field '{path}'"
        if expected is not None:
            if obj != expected:
                return False, f"field '{path}' is {json.dumps(obj)}, expected {json.dumps(expected)}"
        return True, ""
    return fn


def field_equals(path: str, expected):
    return has_field(path, expected)


def field_contains(path: str, substring: str):
    def fn(resp, raw):
        obj = resp
        for key in path.split("."):
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                return False, f"missing field '{path}'"
        if not isinstance(obj, str) or substring not in obj:
            return False, f"field '{path}'='{obj}' does not contain '{substring}'"
        return True, ""
    return fn


def field_not_present(path: str):
    def fn(resp, raw):
        parts = path.split(".")
        obj = resp
        for i, key in enumerate(parts[:-1]):
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                return True, ""  # parent missing, ok
        if isinstance(obj, dict) and parts[-1] in obj:
            return False, f"field '{path}' should not be present"
        return True, ""
    return fn


def summary_has(key: str, expected):
    return has_field(f"summary.{key}", expected)


def data_has(key: str, expected):
    return has_field(f"data.{key}", expected)


def meta_truncated(expected: bool):
    def fn(resp, raw):
        meta = resp.get("meta", {})
        actual = meta.get("truncated", False)
        if actual != expected:
            return False, f"meta.truncated is {actual}, expected {expected}"
        return True, ""
    return fn


def root_driver_line(expected_line: int):
    def fn(resp, raw):
        data = resp.get("data", {})
        root = data.get("root_driver", None)
        if root is None:
            return False, "data.root_driver is missing"
        line = root.get("line", 0)
        if line != expected_line:
            return False, f"root_driver.line is {line}, expected {expected_line}"
        return True, ""
    return fn


def root_driver_kind(expected_kind: str):
    def fn(resp, raw):
        data = resp.get("data", {})
        root = data.get("root_driver", None)
        if root is None:
            return False, "data.root_driver is missing"
        kind = root.get("kind", "")
        if kind != expected_kind:
            return False, f"root_driver.kind is '{kind}', expected '{expected_kind}'"
        return True, ""
    return fn


def trace_has_alias_edge():
    def fn(resp, raw):
        trace = resp.get("data", {}).get("trace", {})
        edges = trace.get("edges", [])
        aliases = [e for e in edges if e.get("relation") == "alias"]
        if not aliases:
            return False, "no alias edge found in data.trace.edges"
        return True, ""
    return fn


def driver_status_is(expected: str):
    def fn(resp, raw):
        summary = resp.get("summary", {})
        status = summary.get("driver_status", "")
        if status != expected:
            return False, f"summary.driver_status is '{status}', expected '{expected}'"
        return True, ""
    return fn


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    global failed, passed, skipped

    # Check xdebug is available
    try:
        subprocess.run([XDEBUG, "-h"], capture_output=True, timeout=5)
    except Exception:
        print(f"SKIP: xdebug binary not available at {XDEBUG}")
        print(f"  Build with: make -C xdebug")
        sys.exit(0)

    # Ensure fixtures are built (optional - may fail if VCS not available)
    for name, fixture_dir in [("active_driver", ACTIVE_DRIVER_DIR),
                               ("interface_port_root", IF_PORT_ROOT_DIR)]:
        daidir = fixture_dir / "out" / "simv.daidir"
        if not daidir.exists():
            print(f"Building fixture: {name} ...")
            try:
                subprocess.run(
                    ["make", "-C", str(fixture_dir), "fixture"],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(REPO_ROOT),
                )
            except Exception as e:
                print(f"Note: fixture build for {name} failed: {e}")

    # Open sessions
    print("Opening sessions...")
    ad_sid, ad_err = open_session(
        f"active_driver_py_{os.getpid()}", ACTIVE_DRIVER_DAIDIR, ACTIVE_DRIVER_FSDB)
    if ad_err:
        print(f"active_driver session open error: {ad_err[:200]}")
        if _has_license_issue(ad_err):
            print("SKIP: all tests — NPI license unavailable")
            if REQUIRE_NPI:
                sys.exit(1)
            sys.exit(0)
        print("FAIL: cannot open active_driver session")
        failed += 1
    else:
        print(f"  active_driver session: {ad_sid}")

    if_sid, if_err = open_session(
        f"if_port_root_py_{os.getpid()}", IF_PORT_ROOT_DAIDIR, IF_PORT_ROOT_FSDB)
    if if_err:
        print(f"interface_port_root session open error: {if_err[:200]}")
        if _has_license_issue(if_err):
            print("SKIP: all tests — NPI license unavailable")
            if REQUIRE_NPI:
                sys.exit(1)
            sys.exit(0)
        print("FAIL: cannot open interface_port_root session")
        failed += 1
    else:
        print(f"  interface_port_root session: {if_sid}")

    if failed > 0:
        sys.exit(1)

    print()
    print("Running test cases...")
    print()

    # ── Test 1: q_20ns ──
    check("q_20ns: basic assignment resolution",
          ad_sid, "active_driver_tb.u_dut.q", "20ns",
          checks=[
              driver_status_is("resolved"),
              root_driver_line(18),
              root_driver_kind("assignment"),
          ])

    # ── Test 2: comb_q_16ns (pass-through: should go comb_q=q -> q<=data_a) ──
    check("comb_q_16ns: pass-through recursion to line 18",
          ad_sid, "active_driver_tb.u_dut.comb_q", "16ns",
          checks=[
              driver_status_is("resolved"),
              root_driver_line(18),
              root_driver_kind("assignment"),
          ])

    # ── Test 3: q_force_40ns ──
    check("q_force_40ns: force detection at line 82",
          ad_sid, "active_driver_tb.u_dut.q", "40ns",
          checks=[
              root_driver_kind("force"),
              root_driver_line(82),
          ])

    # ── Test 4: comb_q_x_50ns (control_only or resolved) ──
    def check_comb_q_x(resp, raw):
        status = resp.get("summary", {}).get("driver_status", "")
        if status in ("control_only", "resolved"):
            return True, ""
        return False, f"driver_status is '{status}', expected 'control_only' or 'resolved'"

    check("comb_q_x_50ns: control_only for default/X branch",
          ad_sid, "active_driver_tb.u_dut.comb_q", "50ns",
          checks=[check_comb_q_x])

    # ── Test 5: if_sink_observed_q_30ns (interface alias join) ──
    check("if_sink_observed_q_30ns: alias resolution to line 23",
          if_sid, "if_root_tb.u_sink.observed_q", "30ns",
          extra_args={"include_trace": True},
          checks=[
              root_driver_line(23),
              root_driver_kind("assignment"),
              trace_has_alias_edge(),
          ])

    # ── Test 6: if_link_data_20ns ──
    check("if_link_data_20ns: modport data trace to line 21",
          if_sid, "if_root_tb.link.data", "20ns",
          checks=[
              root_driver_line(21),
              root_driver_kind("assignment"),
          ])

    # ── Test 7: if_link_data_30ns ──
    check("if_link_data_30ns: modport data trace to line 23",
          if_sid, "if_root_tb.link.data", "30ns",
          checks=[
              root_driver_line(23),
              root_driver_kind("assignment"),
          ])

    # ── Test 8: include_trace_false ──
    check("include_trace_false: no data.trace.nodes",
          ad_sid, "active_driver_tb.u_dut.q", "20ns",
          extra_args={"include_trace": False},
          checks=[
              driver_status_is("resolved"),
              root_driver_line(18),
              field_not_present("data.trace.nodes"),
              has_field("data.root_driver"),
          ])

    # ── Test 9: limits_max_nodes ──
    check("limits_max_nodes: truncation with max_nodes=1",
          ad_sid, "active_driver_tb.u_dut.q", "20ns",
          extra_args={"limits": {"max_nodes": 1}},
          checks=[
              meta_truncated(True),
          ])

    # ── Summary ──
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
