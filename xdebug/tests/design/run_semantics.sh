#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
XDEBUG="$ROOT_DIR/../tools/xdebug"
UART_DB="${UART_DB:-$ROOT_DIR/testdata/design/uart/simv.daidir}"
IFACE_DB="${IFACE_DB:-/home/yian/worken/mod_port_trace/test/testcases/interface_port/simv.daidir}"
P3_DB="${P3_DB:-$ROOT_DIR/testdata/design/p3_semantics/out/simv.daidir}"
TMP_HOME="$(mktemp -d)"

cleanup() {
  printf '%s\n' '{"api_version":"xdebug.v1","action":"session.kill","args":{"id":"all"}}' |
    HOME="$TMP_HOME" "$XDEBUG" --json - >/dev/null 2>&1 || true
  rm -rf "$TMP_HOME"
}
trap cleanup EXIT

require_db() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo "missing regression database: $path" >&2
    exit 1
  fi
}

build_p3_db() {
  if [[ -d "$P3_DB" ]]; then
    return
  fi
  if ! command -v vcs >/dev/null 2>&1; then
    echo "missing regression database and vcs is unavailable: $P3_DB" >&2
    exit 1
  fi
  local out_dir
  out_dir="$(dirname "$P3_DB")"
  rm -rf "$out_dir"
  mkdir -p "$out_dir"
  (
    cd "$out_dir"
    vcs -full64 -sverilog -kdb -debug_access+all \
      "$ROOT_DIR/testdata/design/p3_semantics/p3_semantics.sv" \
      -top p3_sem_top -o simv >/tmp/xdebug_p3_vcs.log 2>&1
  ) || {
    cat /tmp/xdebug_p3_vcs.log >&2
    exit 1
  }
}

query() {
  printf '%s\n' "$1" | HOME="$TMP_HOME" "$XDEBUG" --json -
}

query_any() {
  set +e
  printf '%s\n' "$1" | HOME="$TMP_HOME" "$XDEBUG" --json -
  local rc=$?
  set -e
  return 0
}

check_json() {
  python3 -c '
import json
import sys

payload = json.load(sys.stdin)
expr = sys.argv[1]
ns = {"d": payload}
if not eval(expr, {}, ns):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit(f"check failed: {expr}")
' "$@"
}

require_db "$UART_DB"
build_p3_db
require_db "$P3_DB"

printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | "$XDEBUG" --json - | python3 -c '
import json,sys
d=json.load(sys.stdin)["data"]
assert "trace.driver" in d["implemented"]
assert "fsm.explain" in d["implemented"]
'

printf '%s\n' '{"api_version":"xdebug.v1","action":"schema"}' | "$XDEBUG" --json - | python3 -c 'import json,sys; assert json.load(sys.stdin)["ok"]'

query "{\"api_version\":\"xdebug.v1\",\"action\":\"session.open\",\"target\":{\"daidir\":\"$UART_DB\"},\"args\":{\"name\":\"uart_ai\"}}" \
  | check_json 'd["ok"] and d["summary"]["session_id"] == "uart_ai"'

query '{"api_version":"xdebug.v1","action":"trace.driver","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin"},"limits":{"max_results":10},"output":{"verbosity":"full"}}' \
  | check_json 'd["ok"] and d["data"]["assignment"]["rhs"]["op"] == "ternary" and len(d["data"]["dependency_edges"]) >= 2 and d["summary"]["confidence"] in ("high","medium")'

query '{"api_version":"xdebug.v1","action":"trace.driver","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin","include_statement_only":false},"limits":{"max_results":10},"output":{"verbosity":"full"}}' \
  | check_json 'd["ok"] and not any(e.get("type") == "statement_only" or e.get("resolution") == "statement_only" for e in d["data"]["dependency_edges"])'

query '{"api_version":"xdebug.v1","action":"trace.expand","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin","direction":"driver"},"limits":{"max_depth":2,"max_nodes":20,"max_edges":50},"output":{"verbosity":"full"}}' \
  | check_json 'd["ok"] and d["summary"]["node_count"] >= 2 and d["summary"]["edge_count"] >= 1 and d["meta"]["truncated"] is False and "traces" not in d["data"] and "expanded_queries" in d["data"] and len(d["data"]["graph"]["edges"]) == len(d["data"]["trace"]["dependency_edges"]) and len({(e.get("from_signal"), e.get("to_signal"), e.get("type"), e.get("assignment_type")) for e in d["data"]["graph"]["edges"]}) == len(d["data"]["graph"]["edges"]) and all(e.get("evidence_count", 1) >= 1 and 0 <= len(e.get("evidence", [])) <= 3 and (e.get("evidence_count", 1) == 1 or len(e.get("evidence", [])) >= 1) for e in d["data"]["graph"]["edges"]) and d["summary"]["raw_edge_count"] >= d["summary"]["deduped_edge_count"] and d["summary"]["duplicate_edge_count"] == d["summary"]["raw_edge_count"] - d["summary"]["deduped_edge_count"] and d["summary"]["relation_group_count"] == d["summary"]["edge_count"] and d["summary"]["aggregated_edge_count"] == d["summary"]["deduped_edge_count"] - d["summary"]["relation_group_count"]'

query '{"api_version":"xdebug.v1","action":"trace.expand","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin","direction":"driver"},"limits":{"max_depth":2,"max_nodes":20,"max_edges":50,"max_evidence_per_edge":1},"output":{"verbosity":"full"}}' \
  | check_json 'd["ok"] and d["summary"]["edge_count"] >= 1 and all(len(e.get("evidence", [])) <= 1 for e in d["data"]["graph"]["edges"])'

query '{"api_version":"xdebug.v1","action":"trace.expand","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin","direction":"driver"},"limits":{"max_depth":2,"max_nodes":20,"max_results":1},"output":{"verbosity":"full"}}' \
  | check_json 'd["ok"] and d["summary"]["edge_count"] == 1 and d["summary"]["deduped_edge_count"] == 1 and d["summary"]["truncated"] is True'

query_any '{"api_version":"xdebug.v1","action":"trace.expand","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.DOES_NOT_EXIST","direction":"driver"},"limits":{"max_depth":2,"max_nodes":20,"max_edges":50}}' \
  | check_json 'not d["ok"] and d["summary"]["failed_query_count"] == 1 and d["summary"]["edge_count"] == 0 and d["warnings"] and d["error"]["code"] == "SIGNAL_NOT_FOUND"'

query '{"api_version":"xdebug.v1","action":"trace.path","target":{"session_id":"uart_ai"},"args":{"from_signal":"uart_16550.loopback","to_signal":"uart_16550.RXDin","direction":"driver"},"limits":{"max_depth":2}}' \
  | check_json 'd["ok"] and d["summary"]["found"] is True and d["summary"]["path_count"] >= 1'

query '{"api_version":"xdebug.v1","action":"signal.canonicalize","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin"}}' \
  | check_json 'd["ok"] and d["data"]["canonical"].endswith("RXDin")'

query '{"api_version":"xdebug.v1","action":"source.context","args":{"file":"'"$ROOT_DIR"'/testdata/design/uart/uart_16550.sv","line":164,"context_lines":2,"include_source":true}}' \
  | check_json 'd["ok"] and len(d["data"]["context"]) == 5 and any(x["hit"] for x in d["data"]["context"]) and d["data"]["enclosing"]["type"] != "unknown"'

query '{"api_version":"xdebug.v1","action":"expr.normalize","args":{"expr":"valid && !ready"}}' \
  | check_json 'd["ok"] and d["summary"]["source"] == "string_fallback" and d["summary"]["confidence"] == "low"'

query "{\"api_version\":\"xdebug.v1\",\"action\":\"session.open\",\"target\":{\"daidir\":\"$P3_DB\"},\"args\":{\"name\":\"p3_ai\"}}" \
  | check_json 'd["ok"] and d["summary"]["session_id"] == "p3_ai"'

query '{"api_version":"xdebug.v1","action":"fsm.explain","target":{"session_id":"p3_ai"},"args":{"signal":"p3_sem_top.u_mid.u_leaf.state_q"},"limits":{"max_results":30}}' \
  | check_json 'd["ok"] and d["summary"]["transition_count"] >= 1 and d["data"]["fsm"]["transitions"]'

query '{"api_version":"xdebug.v1","action":"batch","args":{"mode":"continue_on_error","requests":[{"api_version":"xdebug.v1","action":"trace.driver","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.TXD"}},{"api_version":"xdebug.v1","action":"signal.resolve","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin"}}]}}' \
  | check_json 'd["ok"] and d["summary"]["count"] == 2'

query '{"api_version":"xdebug.v1","action":"signal.resolve","target":{"session_id":"uart_ai"},"args":{"signal":"uart_16550.RXDin"}}' \
  | check_json 'd["ok"]'

echo "xdebug design semantics regression passed"
