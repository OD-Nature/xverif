# xdebug stream.* action implementation plan

## Goal

Add waveform-only `stream.*` actions for deterministic custom stream extraction.
The feature targets valid/data, valid/ready/data, valid/backpressure/data, and
optional sop/eop packetized streams. It does not replace `axi.*`, `apb.*`,
`list.*`, or design-side `interface.resolve`.

The first implementation must support both `clock_edge: "posedge"` and
`clock_edge: "negedge"` directly. Stream configuration input is JSON only:
inline JSON or a JSON file. YAML is intentionally unsupported.

## Public actions

Add these stable waveform actions:

- `stream.config.load`
- `stream.config.list`
- `stream.show`
- `stream.validate`
- `stream.query`
- `stream.export`

All six actions require an explicit live waveform `session_id`, consistent with
the current xdebug session contract.

## Config contract

`stream.config.load` accepts either:

- `args.config` with `{ "streams": [...] }`
- `args.streams` with an array of stream configs
- `args.config_path` or `args.file` pointing to a JSON file

`args.mode` is `replace` or `append`, defaulting to `replace`.

Each stream config requires:

- `name`
- `clock`
- `vld`
- at least one of `data`, `beat_fields`, or `packet_stable_fields`

Optional fields:

- `clock_edge` or `edge`: `posedge` or `negedge`, default `posedge`
- `reset`
- `rdy`
- `bp`
- `sop`
- `eop`
- `channel_id`
- `beat_fields`
- `packet_stable_fields`
- `description`

`reset` is an explicit object containing a one-bit signal and its polarity,
for example `{"signal":"top.rst_n","polarity":"active_low"}`.

Data field names must match `[A-Za-z_][A-Za-z0-9_]*` and must not use reserved
names: `time`, `cycle`, `vld`, `rdy`, `bp`, `sop`, `eop`, `transfer`, `stall`,
`packet_index`, or `beat_index`.

## Expression subset

Every signal-bearing stream field accepts a controlled expression subset:

- hierarchical signal path
- bit select and part select
- concat
- constants such as `1'b0`, `4'hf`, `32'hdead_beef`, `0`, `1`
- unary `!` and `~`
- binary `&`, `|`, `^`, `&&`, `||`
- compare `==`, `!=`, `>`, `>=`, `<`, `<=`
- parentheses

Unsupported SystemVerilog features must produce explicit errors, not silent
fallbacks. Unsupported v1 examples include function calls, class handles,
dynamic arrays, queues, associative arrays, `inside`, streaming operators, and
casts.

## Sampling and stream semantics

Sampling happens only on configured clock edges. `clock_edge` supports both
`posedge` and `negedge`.

Transfer rules:

- no `rdy` or `bp`: `transfer = vld && !reset`
- `rdy`: `transfer = vld && rdy && !reset`
- `bp`: `transfer = vld && !bp && !reset`
- `rdy` and `bp`: `transfer = vld && rdy && !bp && !reset`

Stall rules:

- `rdy`: `stall = vld && !rdy`
- `bp`: `stall = vld && bp`
- `rdy` and `bp`: `stall = vld && (!rdy || bp)`
- no `rdy` or `bp`: no stall semantics

Packet rules:

- sop/eop are not inferred.
- sop and eop must be provided together.
- `sop && transfer` starts a packet.
- `eop && transfer` ends a packet.
- sop/eop on the same transfer is a single-beat packet.
- query windows can mark partial packets.

X/Z handling:

- control X/Z is conservative: `vld=false`, `rdy=false`, `bp=true`,
  `reset=true`, `sop=false`, `eop=false`
- data X/Z is preserved in output and counted

## Query/export behavior

`stream.query` supports:

- `summary`
- `first_transfer`
- `last_transfer`
- `transfer_window`
- `first_stall`
- `last_stall`
- `stall_window`
- `first_packet`
- `last_packet`
- `packet_window`
- `filter.fields` 多字段 exact/range/mask 过滤（旧 `match_field` 已删除）

Default inline limit is 32 rows. Truncated inline results return
`truncated:true` and a hint to use `stream.export`.

`stream.export` always writes files. Default format is TSV, with CSV and xout
also accepted. It also writes `<output_file>.meta.json`.

## Implementation structure

Add `xdebug/src/waveform/stream/` with:

- `stream_config.*`
- `stream_manager.*`
- `stream_expr.*`
- `stream_analyzer.*`
- `stream_exporter.*`

Register stream actions in both the public ActionRegistry and the unified
engine action registry. Add stream storage to waveform session cleanup.

## Real waveform test requirement

Add a real VCS/FSDB fixture under `xdebug/testdata/waveform/stream_v1/`.

The SV testbench must generate real waveform activity for:

- `vld + data`
- `vld + rdy + data`
- `vld + bp + data`
- `vld + rdy + sop/eop + data`
- `vld + bp + sop/eop + data`
- `vld + rdy + bp + sop/eop + data`

The fixture must also cover:

- posedge sampling
- negedge sampling
- gated valid expression
- reset signal and polarity
- part select data field
- concat data field
- compare-derived data field
- channel_id filtering
- X/Z data and conservative X/Z control behavior

Each stream scenario must produce at least 10000 successful transfers. The SV
fixture writes an expected JSON sidecar. The pytest compares `stream.query` and
`stream.export` against this sidecar.

## Validation ladder

Focused gates:

- `make -C xdebug schema-test`
- `make -C xdebug contract-test`
- `make -C xdebug unit-test`
- `pytest -c xdebug/tests/pytest.ini xdebug/tests/synthetic/test_stream_v1_real_waveform.py`

Integration gates:

- MCP generic query smoke using `xverif_debug_query(action="stream.query")`
- existing non-AXI waveform smoke

License/VCS/FSDB commands should run outside the sandbox when needed.
