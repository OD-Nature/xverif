# xdebug action review notes

Date: 2026-06-27

## Modify Candidates

### `axi.outstanding_timeline`

Decision: mark as modify candidate.

Required follow-up:

- Add an outstanding waveform export path.
- The future output should be able to produce a visual timeline of AXI outstanding read/write counts, not only a compact sample table.

Reason:

- The action concept is useful for outstanding accumulation and backpressure diagnosis.
- The current action name suggests a timeline, but the next useful agent/user workflow is a waveform-style visualization.

## Delete Candidates

### `control explanation view`

Decision: mark as delete candidate.

Reason:

- Real XOUT on the UART design fixture returned no useful control dependency information for the reviewed signal.
- The action does not currently provide enough actionable explanation to justify keeping it as a public action.

### `counter explanation view`

Decision: mark as delete candidate.

Reason:

- Real XOUT on the UART design fixture did not prove a useful counter explanation for the reviewed signal.
- The waveform-oriented `counter.statistics` action provides concrete sampled counter facts and is more useful for the observed workflow.

## Test Enhancement Candidates

### `detect_anomaly`

Decision: mark as test enhancement candidate.

Required follow-up:

- Strengthen tests so each requested anomaly check type is covered by at least one real finding.
- The reviewed request enabled `glitch`, `stuck`, and `unknown_xz`, but the real XOUT only reported `glitch` and `unknown_xz`.
- Add or adjust fixture coverage so `stuck` is asserted explicitly when the stuck check is requested.

Reason:

- The action is useful, but current fixture/test evidence does not prove all advertised check types in one reviewable output.
- Better test coverage is needed before relying on this as a general anomaly scanner.

## Real XOUT Evidence

These examples were run on real local FSDB fixtures outside the sandbox because waveform/NPI/license-backed actions must run outside the sandbox.

AXI fixture:

```text
xdebug/testdata/waveform/axi_vip_real/out/regression/test/axi_multi_id_test/waves.fsdb
```

APB fixture:

```text
xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb
```

Design fixture:

```text
xdebug/testdata/design/uart/simv.daidir
```

### `axi.channel_stall`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.channel_stall",
  "target": {"session_id": "<opened AXI session>"},
  "args": {
    "name": "axi0",
    "channel": "r",
    "time_range": {"begin": "0ns", "end": "200ms"},
    "rules": {"max_wait_cycles": 2},
    "max_samples": 1000000
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.axi.channel_stall.v1
data:
  sample_count: 1000000
  transfer_count: 33545
  max_stall_cycles: 110
  ready_without_valid_cycles: 932585
  data_stability_violations: 0
  truncated: true

findings:
  type severity begin end cycles
  long_stall warning 15165ns 15465.009ns 31
  long_stall warning 23645ns 23865.009ns 23
  long_stall warning 36535ns 36715.009ns 19
  long_stall warning 38015ns 38205.009ns 20
  long_stall warning 43335ns 43525.009ns 20
  long_stall warning 54725ns 54885.009ns 17
  long_stall warning 71715ns 71975.009ns 27
  long_stall warning 71985ns 72035.009ns 6
  long_stall warning 75025ns 75255.009ns 24
  long_stall warning 75265ns 75305.009ns 5
  long_stall warning 84675ns 84745.009ns 8
  long_stall warning 86655ns 86925.009ns 28
  long_stall warning 96635ns 96915.009ns 29
  long_stall warning 96925ns 97075.009ns 16
  long_stall warning 97645ns 97765.009ns 13
  long_stall warning 107525ns 107545.009ns 3
  long_stall warning 110795ns 111095ns 31
  long_stall warning 120415ns 120435.009ns 3
  long_stall warning 132305ns 132565.009ns 27
  long_stall warning 162165ns 162295.009ns 14
  name: axi0
  channel: r
```

Initial review note:

`axi.channel_stall` has concrete value: it surfaces long-stall windows and max stall cycles directly. The XOUT is useful, though the huge `sample_count` and `truncated:true` mean users may need a smaller time window for focused debugging.

### `axi.request_response_pair`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.request_response_pair",
  "target": {"session_id": "<opened AXI session>"},
  "args": {
    "name": "axi0",
    "time_range": {"begin": "0ns", "end": "200ms"},
    "limit": 5
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.axi.request_response_pair.v1
data:
  name: axi0
  begin: 0ns
  end: 200000000ns
  transaction_count: 5
  truncated: true

transactions:
  addr_time type id addr len size burst beats first_data_time last_data_time resp_time resp match_time latency
  415ns WR 'h00 'h00000000000008c0 'h000 'h3 'h1 1 635ns 635ns 1345ns 'h0 415ns 930ns
  415ns RD 'h00 'h000000000000ef58 'h00c 'h3 'h1 13 1315ns 12115ns 12115ns 'h0 415ns 11700ns
  455ns RD 'h01 'h000000000000b440 'h004 'h3 'h1 5 12125ns 15165ns 15165ns 'h0 455ns 14710ns
  515ns RD 'h02 'h000000000000d4e0 'h00b 'h3 'h1 12 15475ns 23645ns 23645ns 'h0 515ns 23130ns
  565ns WR 'h01 'h000000000000ef28 'h002 'h3 'h1 3 695ns 1055ns 15575ns 'h0 565ns 15010ns
```

Initial review note:

`axi.request_response_pair` is useful. It provides the paired request/response timing and latency in one table. The main weakness is table width, but it answers a real debug question.

Enhancement decision:

Mark `axi.request_response_pair` as a modify candidate.

Required follow-up:

- Add user-configurable transaction filters.
- ID filter: allow membership matching, so users can request one or more AXI IDs.
- Type filter: allow `rd`, `wr`, and `wrandrd`.
- Address filter: allow an array of explicit addresses, so users can request transactions touching selected addresses.
- The JSON response and XOUT should include a concise AI-facing hint: for more advanced searches, prefer exporting AXI transaction data and analyzing it with a script, or directly use the `x-pynpi` skill for custom waveform/protocol analysis.

Intended parameter shape:

```json
{
  "filter": {
    "ids": ["'h00", "'h01"],
    "type": "wrandrd",
    "addrs": ["'h00000000000008c0", "'h000000000000ef58"]
  }
}
```

Output guidance requirement:

- JSON should expose a short machine-readable hint, for example `advanced_search_hint`.
- XOUT should print the same hint briefly after the transaction table or summary.
- The hint should steer AI away from overloading this action with arbitrary query-language features; complex filtering, joins, aggregation, and post-processing should happen after AXI data export or through `x-pynpi`.

### `axi.latency_outlier`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.latency_outlier",
  "target": {"session_id": "<opened AXI session>"},
  "args": {
    "name": "axi0",
    "time_range": {"begin": "0ns", "end": "200ms"},
    "top_n": 5,
    "limit": 200
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.axi.latency_outlier.v1
data:
  name: axi0
  begin: 0ns
  end: 200000000ns
  transaction_count: 200
  truncated: true

outliers:
  addr_time type id addr len size burst beats first_data_time last_data_time resp_time resp match_time latency
  8555ns RD 'h0d 'h0000000000004f90 'h003 'h3 'h1 4 296465ns 298415ns 298415ns 'h0 8555ns 289860ns
  8715ns RD 'h0e 'h000000000000cfd8 'h000 'h3 'h1 1 298555ns 298555ns 298555ns 'h0 8715ns 289840ns
  8985ns RD 'h0f 'h000000000000ff20 'h000 'h3 'h1 1 298635ns 298635ns 298635ns 'h0 8985ns 289650ns
  8505ns RD 'h0c 'h000000000000e868 'h00d 'h3 'h1 14 289565ns 296455ns 296455ns 'h0 8505ns 287950ns
  8335ns RD 'h0b 'h0000000000002678 'h00f 'h3 'h1 16 275835ns 289295ns 289295ns 'h0 8335ns 280960ns
  outlier_count: 5
```

Initial review note:

`axi.latency_outlier` is useful but overlaps with `axi.request_response_pair`. Its value is the top-N ranking; if kept, it should remain clearly positioned as the ranking/filter action, not a replacement for full pairing.

Enhancement decision:

Mark `axi.latency_outlier` as a modify candidate.

Required follow-up:

- Include transactions that start before the requested window and return after the requested window. The intended window semantics should cover transactions active across the window, not only transactions whose request or response endpoint falls inside the window.
- Add a latency waveform export path so users can inspect the latency distribution/timeline visually, not only as a top-N compact table.

Implementation note:

- Current `get_transactions_in_range()` includes transactions whose `addr_time` is in `[begin, end]` and transactions whose `resp_time` is in `[begin, end]`.
- It does not include a transaction with `addr_time < begin` and `resp_time > end`, even though that transaction is active for the entire queried window.

### `apb.transfer_window`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "apb.transfer_window",
  "target": {"session_id": "<opened APB session>"},
  "args": {
    "name": "apb0",
    "time_range": {"begin": "200ns", "end": "400ns"},
    "limit": 3
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.apb.transfer_window.v1
summary:
  name: apb0
  begin: 200ns
  end: 400ns
  transaction_count: 3

transactions:
  time type addr data has_error
  215ns WR 'h0100 'hdeadbeef false
  245ns RD 'h0100 'hcafef00d false
  275ns WR 'h0200 'h12345678 false
```

Initial review note:

`apb.transfer_window` is compact and readable. It is close to a filtered `apb.query`, but the explicit time-window framing is useful for local APB debug.

### `control explanation view`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "control explanation view",
  "target": {"session_id": "<opened design session for UART fixture>"},
  "args": {
    "signal": "uart_tx.bit_counter"
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.control explanation view.v1
summary:
  signal: uart_tx.bit_counter
  control_dependency_count: 0

data:
  control_dependencies: [empty]
```

Review decision:

Mark `control explanation view` as a delete candidate.

Reason:

- The reviewed real output is effectively empty and does not explain a useful control relationship.
- Keeping this as a public action risks giving AI a tool that looks semantic but returns little actionable content.

### `counter explanation view`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "counter explanation view",
  "target": {"session_id": "<opened design session for UART fixture>"},
  "args": {
    "signal": "uart_tx.bit_counter"
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.counter explanation view.v1
summary:
  signal: uart_tx.bit_counter
  counter_like: false
  rule_count: 0
  confidence: medium

counter:
  confidence: medium
  confidence_reason: sequential rules were found but no increment/decrement pattern was proven
  counter_like: false
  rules: [empty]
  signal: uart_tx.bit_counter
```

Review decision:

Mark `counter explanation view` as a delete candidate.

Reason:

- The reviewed real output does not provide a useful counter explanation.
- For counter-oriented workflows, `counter.statistics` gives concrete waveform facts and should be preferred over this design-only explanation action.

### `detect_anomaly`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "detect_anomaly",
  "target": {"session_id": "<opened APB/complex waveform session>"},
  "args": {
    "signals": [
      "ai_complex_top.glitch_sig",
      "ai_complex_top.stuck_sig",
      "ai_complex_top.xz_bus"
    ],
    "time_range": {"begin": "0ns", "end": "200ns"},
    "checks": [
      {"type": "glitch", "min_pulse_width": "1ns"},
      {"type": "stuck", "min_duration": "100ns"},
      {"type": "unknown_xz"}
    ],
    "max_findings": 10
  },
  "output": {"verbosity": "full"}
}
```

XOUT:

```text
@xdebug.detect_anomaly.v1
summary:
  finding_count: 3
  truncated: false

data:
  finding_count: 3

findings:
  type signal severity time pulse_width value
  glitch ai_complex_top.glitch_sig info 96ns 0.2ns
  unknown_xz ai_complex_top.xz_bus warning 85ns 8'hxx known=false bits=xxxxxxxx width=8
  unknown_xz ai_complex_top.xz_bus warning 95ns 8'hxx known=false bits=zzzzzzzz width=8
  truncated: false
```

Review decision:

Mark `detect_anomaly` as a test enhancement candidate.

Reason:

- The action returned useful `glitch` and `unknown_xz` findings.
- The request also enabled `stuck`, but the reviewed XOUT did not include a `stuck` finding. Tests should be strengthened so every requested anomaly check type has explicit fixture evidence.
