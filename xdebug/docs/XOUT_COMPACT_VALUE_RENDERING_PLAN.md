# xdebug XOUT Compact Value Rendering Plan

## Summary

XOUT is the human-readable response format for xdebug. This change keeps JSON
responses unchanged and only compacts XOUT rendering for waveform value objects.

Default rule:

- Known values with reliable width render as `<width>'h<hex>`, for example
  `32'h4000000c`.
- Known values without reliable width render as unsized hex, for example
  `'h22`.
- Values containing X/Z render the compact value plus diagnostics, for example
  `32'h400000xx known=false bits=010000000000000000000000xxxxxxxx width=32`.
- XOUT must not recursively expand `value`, `bits`, `known`, and `width` for
  normal known values.

JSON response schemas and action semantics are not changed.

## Affected Actions

The implementation updates the shared XOUT renderer paths used by CLI,
stdio-loop, and engine-generated text. These actions have visible value-object
changes:

- `value.at`
- `value.batch_at`
- `list.value_at`
- `verify.conditions`
- `event.find`
- `event.export`
- `signal.changes`
- `signal.stability`
- `signal.statistics`
- `expr.eval_at`
- `sampled_pulse.inspect`
- `detect_abnormal`
- `stream.query`
- `trace.active_driver`

These actions currently do not need dedicated value-object XOUT examples:

- `axi.*`
- `apb.*`
- `stream.config.load`
- `stream.config.list`
- `stream.show`
- `stream.validate`
- `stream.export`
- `session.*`
- `actions`
- `schema`
- `batch`
- `trace.active_driver_chain`
- `window.verify`
- `handshake.inspect`
- `signal.trend`
- design-only actions such as `trace.driver`, `trace expansion view`,
  `source.context`, and `interface.resolve`

## Expected XOUT Examples

### value.at

```text
@xdebug.value.at.v1
target:
  signal: top.sig_a
  time: 75ns

summary:
  status: ok
  value: 'h22
```

With X/Z:

```text
summary:
  status: ok
  value: 'hxx known=false
```

### value.batch_at

```text
@xdebug.value.batch_at.v1
summary:
  time: 75ns
  signal_count: 3
  x_or_z_count: 1

values:
  signal value status
  top.sig_a 'h22 ok
  top.sig_b 'h22 ok
  top.xz_bus 'hxx known=false ok
```

### list.value_at

```text
@xdebug.list.value_at.v1
summary:
  name: req_list
  time: 75ns

values:
  top.req_vld 1'h1
  top.req_data 'h4000000c
  top.req_opcode 'ha3
```

### verify.conditions

```text
@xdebug.verify.conditions.v1
summary:
  verdict: fail
  condition_count: 3
  passed: 1
  failed: 1
  unknown: 1

checks:
  signal op expected observed status
  top.sig_a == 'h22 'h22 pass
  top.sig_b == 'h23 'h22 fail
  top.xz_bus == 'h0 'hxx known=false unknown
```

### event.find

```text
@xdebug.event.find.v1
summary:
  event_count: 1
  first: 185ns
  mode: first

events:
  time fields signals
  185ns opcode='ha addr='h1000 vld=1'h1 rdy=1'h1
```

### event.export

```text
@xdebug.event.export.v1
summary:
  event_count: 3
  first: 185ns
  last: 215ns
  mode: export

examples:
  time fields signals
  185ns opcode='ha addr='h1000 vld=1'h1
  195ns opcode='ha addr='h1004 vld=1'h1
  205ns opcode='ha addr='h1008 vld=1'h1
```

### signal.changes

```text
@xdebug.signal.changes.v1
summary:
  transition_count: 4
  returned_change_rows: 5
  first_change: 10ns
  last_change: 50ns

data:
  signal: top.state
  initial_value: 'h0
  final_value: 'h3

changes:
  time value
  10ns 'h0
  20ns 'h1
  30ns 'h2
  40ns 'h3
```

### signal.stability

```text
@xdebug.signal.stability.v1
summary:
  transition_count: 1

data:
  signal: top.cfg_mode
  stable: true
  value: 'h2
  initial_value: 'h2
  final_value: 'h2
```

### signal.statistics

```text
@xdebug.signal.statistics.v1
summary:
  sampling_mode: raw_value_changes
  sample_count: 4
  transition_count: 3

data:
  signal: top.counter
  initial_value: 'h0
  final_value: 'h3
```

### expr.eval_at

```text
@xdebug.expr.eval_at.v1
summary:
  status: true
  known: true

operands:
  alias signal value
  vld top.req_vld 1'h1
  rdy top.req_rdy 1'h1
```

With X/Z:

```text
operands:
  alias signal value
  vld top.req_vld 1'h1
  rdy top.req_rdy 1'hx known=false bits=x width=1
```

### sampled_pulse.inspect

```text
@xdebug.sampled_pulse.inspect.v1
summary:
  sample_count: 100
  sampled_high_cycles: 12
  raw_valid_transition_count: 18
  payload_transition_count: 4
  risk_count: 1

first_risk:
  type: payload_changed_without_sampled_valid
  raw_time: 125ns
  payload: alias=data0 signal=top.data value=32'h4000000c
  sampled_valid: 1'h0
```

### detect_abnormal

```text
@xdebug.detect_abnormal.v1
summary:
  finding_count: 2

findings:
  type signal time value severity
  unknown_xz top.xz_bus 75ns 4'hx known=false bits=10xz width=4 warning
  stuck top.cfg_mode 100ns 2'h2 warning
```

### stream.query

`packet_at`:

```text
@xdebug.stream.query.v1
summary:
  stream: ready_packet
  packet_enabled: true
  complete_packet_count: 5000
  partial_packet_count: 0
  packet_count_status: exact

packet:
  packet_index: 3
  start_cycle: 18
  end_cycle: 21
  start_time: 185ns
  end_time: 215ns
  beat_count: 4
  packet_stable_fields: opcode=8'ha3
  first_fields: data=32'h4000000c seq=16'h000c
  last_fields: data=32'h4000000f seq=16'h000f

beat_fields_preview:
  total_beats: 4
  truncated: false

head:
  cycle time beat_index fields
  18 185ns 0 data=32'h4000000c seq=16'h000c
  19 195ns 1 data=32'h4000000d seq=16'h000d
```

`packet_window`:

```text
packets:
  packet_index start_time end_time beat_count packet_stable_fields first_fields last_fields
  0 65ns 95ns 4 opcode=8'ha0 data=32'h40000000 data=32'h40000003
  1 105ns 135ns 4 opcode=8'ha1 data=32'h40000004 data=32'h40000007
```

`match_field`:

```text
rows:
  cycle time packet_index beat_index fields packet_stable_fields
  42 425ns 9 2 data=32'h00001000 seq=16'h002a opcode=8'ha9
```

With X/Z:

```text
fields: data=32'h400000xx known=false bits=010000000000000000000000xxxxxxxx width=32
```

### trace.active_driver

```text
@xdebug.trace.active_driver.v1
summary:
  signal: top.u.ready
  requested_time: 100ns
  active_time: 95ns

events:
  time signal value
  95ns top.u.valid 1'h1
  95ns top.u.ready 1'h1

controls:
  signal value
  top.u.state 2'h2
```

With X/Z:

```text
controls:
  signal value
  top.u.state 2'hx known=false bits=xz width=2
```

## Implementation Steps

1. Add shared compact value helpers in the XOUT text builder layer.
2. Update CLI generic and specialized XOUT renderers to use the helpers.
3. Update engine generic XOUT rendering to use the same helpers for scalar
   detection, table columns, row cells, and nested field maps.
4. Keep JSON response generation unchanged.
5. Add unit and contract tests.
6. Add stream real-waveform XOUT assertions.

## Test Plan

- Unit tests:
  - known `{value,bits,known,width}` renders as `<width>'h...`
  - unsized known `{value,known}` renders as `'h...`
  - binary values infer width and render hex
  - X/Z values append diagnostics
  - nested field maps and table cells do not expand value objects
- Contract tests:
  - CLI XOUT and stdio-loop XOUT remain equivalent
  - `value.at`, `value.batch_at`, `verify.conditions`, and `signal.changes`
    do not show redundant value-object expansion
- Real waveform tests:
  - stream `packet_at`, `packet_window`, and `match_field` XOUT assertions
  - X/Z stream field assertion

License/NPI/FSDB-backed validation must run outside the sandbox.
