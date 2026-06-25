#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XDEBUG="$ROOT/tools/xdebug"
DBDIR="$ROOT/xdebug/testdata/combined/active_driver/out/simv.daidir"
FSDB="$ROOT/xdebug/testdata/combined/active_driver/out/waves.fsdb"
NPI_LIB="$VERDI_HOME/share/NPI/lib/LINUX64"
if [[ ! -d "$NPI_LIB" ]]; then
    NPI_LIB="$VERDI_HOME/share/NPI/lib/linux64"
fi
TMP_HOME="$(mktemp -d /tmp/xdebug-regression-home.XXXXXX)"

query() {
    printf '%s\n' "$2" | HOME="$TMP_HOME" "$XDEBUG" --json - > "$TMP_HOME/$1.json"
}

query_from_root() {
    (cd "$ROOT" && printf '%s\n' "$2" | HOME="$TMP_HOME" "$XDEBUG" --json -) > "$TMP_HOME/$1.json"
}

expect_ok() {
    python3 - "$TMP_HOME/$1.json" "$1" <<'PY'
import json
import sys

path, name = sys.argv[1:]
with open(path) as f:
    data = json.load(f)
assert data.get("api_version") == "xdebug.v1", (name, data)
assert data.get("ok") is True, (name, data)
PY
}

cleanup() {
    printf '%s\n' '{"api_version":"xdebug.v1","action":"session.kill","args":{"id":"all"}}' |
        HOME="$TMP_HOME" "$XDEBUG" --json - >/dev/null 2>&1 || true
    rm -rf "$TMP_HOME"
}
trap cleanup EXIT

query actions '{"api_version":"xdebug.v1","action":"actions"}'
expect_ok actions
python3 - "$TMP_HOME/actions.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    data = json.load(f)["data"]
assert "trace.active_driver" in data["implemented"]
assert "signal.search" in data["removed"]
PY

printf '%s\n' '{"api_version":"unsupported.v0","action":"actions"}' |
    HOME="$TMP_HOME" "$XDEBUG" --json - > "$TMP_HOME/unsupported_api.json" || true
printf '%s\n' '{"api_version":"xdebug.v1","action":"signal.search"}' |
    HOME="$TMP_HOME" "$XDEBUG" --json - > "$TMP_HOME/removed_action.json" || true
HOME="$TMP_HOME" "$XDEBUG" open waves.fsdb > "$TMP_HOME/text_cli.xout" || true
HOME="$TMP_HOME" "$XDEBUG" --json open waves.fsdb > "$TMP_HOME/text_cli.json" || true
grep -q '^@xdebug.error.v1' "$TMP_HOME/text_cli.xout"
python3 - "$TMP_HOME/unsupported_api.json" "$TMP_HOME/removed_action.json" "$TMP_HOME/text_cli.json" <<'PY'
import json
import sys

unsupported_api = json.load(open(sys.argv[1]))
removed = json.load(open(sys.argv[2]))
text_cli = json.load(open(sys.argv[3]))
assert unsupported_api["ok"] is False and unsupported_api["error"]["code"] == "UNSUPPORTED_API_VERSION"
assert removed["ok"] is False and removed["error"]["code"] == "UNKNOWN_ACTION"
assert text_cli["ok"] is False and text_cli["error"]["code"] == "JSON_ONLY"
PY

if LD_LIBRARY_PATH="$NPI_LIB:${LD_LIBRARY_PATH:-}" "$ROOT/xdebug/libexec/xdebug-engine" open -dbdir nowhere \
    >"$TMP_HOME/private_engine.out" 2>&1; then
    printf 'FAIL: internal engine accepted a text CLI request\n' >&2
    exit 1
fi
grep -q 'accepts JSON requests only' "$TMP_HOME/private_engine.out"

if [[ ! -d "$DBDIR" || ! -f "$FSDB" ]]; then
    printf 'SKIP: fixture resources absent: %s %s\n' "$DBDIR" "$FSDB"
    exit 0
fi

query wave_open "{\"api_version\":\"xdebug.v1\",\"action\":\"session.open\",\"target\":{\"fsdb\":\"$FSDB\"},\"args\":{\"name\":\"wave_case\"}}"
expect_ok wave_open
query wave_only "{\"api_version\":\"xdebug.v1\",\"action\":\"value.at\",\"target\":{\"session_id\":\"wave_case\"},\"args\":{\"signal\":\"active_driver_tb.u_dut.q\",\"time\":\"26ns\",\"format\":\"bin\"}}"
expect_ok wave_only

query design_open "{\"api_version\":\"xdebug.v1\",\"action\":\"session.open\",\"target\":{\"daidir\":\"$DBDIR\"},\"args\":{\"name\":\"design_case\"}}"
expect_ok design_open
query design_only "{\"api_version\":\"xdebug.v1\",\"action\":\"trace.driver\",\"target\":{\"session_id\":\"design_case\"},\"args\":{\"signal\":\"active_driver_tb.u_dut.q\"},\"limits\":{\"max_results\":4}}"
expect_ok design_only

query compact_expand '{"api_version":"xdebug.v1","action":"trace.expand","target":{"session_id":"design_case"},"args":{"signal":"active_driver_tb.u_dut.q","direction":"driver"},"limits":{"max_depth":1,"max_edges":8}}'
query compact_verify '{"api_version":"xdebug.v1","action":"verify.conditions","target":{"session_id":"wave_case"},"args":{"signal":"active_driver_tb.u_dut.q","time":"26ns","conditions":[{"signal":"active_driver_tb.u_dut.q","op":"==","value":"'\''hb2"},{"signal":"active_driver_tb.u_dut.q","op":"==","value":"'\''h00"}]}}'
python3 - "$TMP_HOME/wave_only.json" "$TMP_HOME/design_only.json" "$TMP_HOME/compact_expand.json" "$TMP_HOME/compact_verify.json" <<'PY'
import json
import sys

wave, design, expand, verify = (json.load(open(path)) for path in sys.argv[1:])
assert isinstance(wave["data"]["value"], dict), wave
assert wave["data"]["value"]["value"] == "8'hb2", wave
assert "resolved_time" not in wave["data"], wave
assert "assignments" in design["data"], design
assert design["data"]["assignments"], design
assert "graph" in expand["data"], expand
assert verify["summary"]["verdict"] == "fail", verify
assert any(item["status"] == "pass" for item in verify["data"]["checks"]), verify
assert any(item["status"] == "fail" for item in verify["data"]["checks"]), verify
PY

query combined_open "{\"api_version\":\"xdebug.v1\",\"action\":\"session.open\",\"target\":{\"daidir\":\"$DBDIR\",\"fsdb\":\"$FSDB\"},\"args\":{\"name\":\"combined_case\"}}"
expect_ok combined_open
query_from_root combined_relative_open '{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"xdebug/testdata/combined/active_driver/out/simv.daidir","fsdb":"xdebug/testdata/combined/active_driver/out/waves.fsdb"},"args":{"name":"combined_relative"}}'
expect_ok combined_relative_open
query active_assignment '{"api_version":"xdebug.v1","action":"trace.active_driver","target":{"session_id":"combined_case"},"args":{"signal":"active_driver_tb.u_dut.q","requested_time":"26ns","include_control":true,"include_parity":true}}'
query active_force '{"api_version":"xdebug.v1","action":"trace.active_driver","target":{"session_id":"combined_case"},"args":{"signal":"active_driver_tb.u_dut.q","requested_time":"40ns","include_control":true}}'
query active_default '{"api_version":"xdebug.v1","action":"trace.active_driver","target":{"session_id":"combined_case"},"args":{"signal":"active_driver_tb.u_dut.comb_q","requested_time":"51ns","include_control":true}}'
query active_relative '{"api_version":"xdebug.v1","action":"trace.active_driver","target":{"session_id":"combined_relative"},"args":{"signal":"active_driver_tb.u_dut.q","requested_time":"26ns","include_control":true}}'
python3 - "$TMP_HOME/active_assignment.json" "$TMP_HOME/active_force.json" "$TMP_HOME/active_default.json" "$TMP_HOME/active_relative.json" <<'PY'
import json
import sys

assignment, force, default, relative = (json.load(open(path)) for path in sys.argv[1:])
for result in (assignment, force, default, relative):
    assert result["ok"] is True, result
assert assignment["data"]["active_time"] == "25ns"
assert assignment["data"]["driver_status"] == "resolved"
assert assignment["data"]["driver"]["kind"] == "assignment"
assert assignment["data"]["driver"]["line"] == 20
assert force["data"]["active_time"] == "37ns"
assert force["data"]["driver"]["kind"] == "force"
assert force["data"]["driver"]["line"] == 82
assert default["data"]["active_time"] == "50ns"
assert default["data"]["driver_status"] == "control_only"
assert default["data"]["driver"] is None
assert relative["data"]["driver"]["line"] == 20
PY

query session_active '{"api_version":"xdebug.v1","action":"trace.active_driver","target":{"session_id":"combined_case"},"args":{"signal":"active_driver_tb.u_dut.q","requested_time":"26ns","include_control":true}}'
expect_ok session_active
python3 - "$TMP_HOME/session_active.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    result = json.load(f)
assert result["data"]["driver_status"] == "resolved"
assert result["data"]["driver"]["line"] == 20
PY

printf 'PASS: xdebug JSON API, fallback modes, and active trace fixture\n'
