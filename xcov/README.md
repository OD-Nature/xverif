# xcov

`xcov` is an AI/MCP-oriented query engine for VCS/Verdi coverage databases.
It accepts `xcov.v1` JSON requests and returns compact `xout` by default.
Set `output.response_format:"json"` or use `tools/xcov --json -` for machine
JSON responses.

xcov follows the same stateful split as xdebug: `tools/xcov --stdio-loop`
hosts the real coverage database session and owns VDB handles, cached summary,
scope traversal, and query execution. `xverif_mcp` only starts/stops the loop
process, keeps alias/default mappings, forwards JSON requests, and handles
direct/LSF launcher cleanup.

## Quick Start

One-shot:

```bash
printf '%s\n' '{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"fake"},"args":{"name":"cov0","fake":true}}' \
  | tools/xcov --json -
```

Loop mode for MCP:

```bash
tools/xcov --stdio-loop
```

The loop emits a JSON ready line with `protocol:"xcov-stdio-loop"` and then
JSONL envelopes containing `xout` and `json` payloads. NPI diagnostic output is
routed to stderr so stdout remains machine-readable.

## Real NPI Smoke

The verified runtime shape is:

```text
Python 3.11
```

Verified database shape:

```text
<project>/sim/merged.vdb
```

Observed smoke results:

```text
session.open: ok, test_count=1, top_scope_count=null (lazy; scope actions scan hierarchy)
tests.list: ok, matched_count=1
metrics.list: ok, matched_count=4
scope.summary: ok, matched_count=1 for uart_tb
scope.children: ok, direct children returned with limits
export.scope_tree: ok, writes .xverif/xcov_exports/<name>
cov.holes: ok with metric/limit filtering
```

Real NPI commands need access to the local Synopsys license server. In sandboxed
execution, run them outside the sandbox.

## MCP Tools

`xverif_mcp` exposes xcov as a stateful backend:

```text
xverif_cov_session_open
xverif_cov_session_list
xverif_cov_session_use
xverif_cov_session_close
xverif_cov_query
xverif_cov_raw_request
xverif_cov_list_actions
xverif_cov_get_schema
```

Use `XVERIF_MCP_ENABLE_COV=0` to hide coverage tools. `XVERIF_XCOV_BIN` and
`XVERIF_XCOV_PYTHON` override the xcov executable and Python runtime.

MCP `xverif_cov_query` accepts `limits` and `output` as top-level tool
arguments. xcov merges those into action args unless `args.limits` or
`args.output` is already set; action-local args win.

`xverif_cov_get_schema` returns action-specific request/response schemas for
all current P0 actions. The schema is meant for agent/tool guidance; runtime
validation still uses xcov's explicit checks.

## Logs

xcov writes diagnostic logs without touching stdout protocol output:

```text
~/.xverif/xcov/sessions/<session_id>/session.json
~/.xverif/xcov/sessions/<session_id>/logs/actions.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/lifecycle.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/transport.ndjson
```

Use `XVERIF_XCOV_LOG_DIR` to override the log root. Use
`XVERIF_XCOV_LOG=0` to disable logging. Log events follow the xdebug-style
fields `ts/event_id/pid/layer/component/session_id/action/phase/ok/context`
and omit large coverage payloads such as full `items` arrays.

## Scope Semantics

- `scope.summary(scope="top.u_dut")` returns one aggregate row for that scope.
- `scope.summary` without `scope` returns aggregate rows for top scopes.
- `scope.children(scope="top.u_dut")` returns direct children only.
- `scope.children(..., recursive=true)` returns descendants.
- `scope.search` only searches scope names/paths and does not attach coverage
  aggregation fields.
- `export.scope_tree` exports scope rows enriched with coverage totals and
  per-metric summaries.

Session open/status/close are lightweight: they do not recursively scan the
whole VDB. Recursive scope/item traversal is triggered by coverage actions such
as `scope.children`, `scope.summary`, `export.scope_tree`, and `cov.holes`.

## Export Safety

For MCP safety, relative `output.path` values are written under
`.xverif/xcov_exports/`. Paths containing `..` are rejected. Absolute paths are
rejected unless `output.allow_absolute_path=true` is set explicitly.

## Current Limits

- `test="each"` is not implemented; use `test="merged"` or a concrete test name.
- `cov.object.get` is an exact lookup with optional `include_children` and
  `max_children`; it is not a general object index yet.
- `functional.summary` and `functional.holes` support
  `levels=["covergroup","coverpoint","cross","bin"]`.
