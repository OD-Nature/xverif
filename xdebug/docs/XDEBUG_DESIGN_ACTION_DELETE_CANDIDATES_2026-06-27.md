# xdebug action delete candidates

Date: 2026-06-27

## Decision

The following actions are marked as delete candidates:

- `port.trace`
- `instance.map`
- `interface.resolve`
- `signal.trend`

Current decision: remove these actions from the public xdebug action contract. They are no longer registered in the runtime catalog and their public specs, schemas, examples, response samples, and smoke-test enumerations have been removed. The implementation history and real XOUT evidence are kept here so the removal can be reviewed later.

Reason:

- The public request examples and runtime implementation are misaligned. The examples use `port`, `instance`, and `interface`, while the current implementation expects `args.path`.
- The XOUT output is mostly raw NPI structure. It is hard to scan and does not directly answer a common debug question.
- `port.trace` duplicates part of `instance.map` and adds a very wide trace table.
- `interface.resolve` did not expose useful modport information in the real local fixture below.
- `signal.trend` summarizes sampled value shape, but the observed output is thin and overlaps with richer waveform analysis actions.

## Real XOUT Evidence

These examples were run on a real local design database outside the sandbox because design/NPI/license-backed actions must run outside the sandbox.

Database:

```text
xdebug/testdata/combined/interface_port_root/out/simv.daidir
```

Source:

```text
xdebug/testdata/combined/interface_port_root/if_root_tb.sv
```

The session was opened explicitly first because these design actions require `target.session_id`.

### `port.trace`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "port.trace",
  "target": {"session_id": "<opened-session>"},
  "args": {"path": "if_root_tb.u_src"},
  "limits": {"max_results": 8},
  "output": {"verbosity": "compact"}
}
```

XOUT:

```text
@xdebug.port.trace.v1
summary:
  ok: true
  port_count: 5
  query: if_root_tb.u_src

object:
  full_name: if_root_tb.u_src

location:
  file: <xverif-repo>/xdebug/testdata/combined/interface_port_root/if_root_tb.sv
  line: 50
  name: u_src
  npi_type: 32
  text: if_source  u_src(.rst_n(if_root_tb.rst_n), .sel(if_root_tb.sel), .a(if_root_tb.a), .b(if_root_tb.b), .bus(if_root_tb.link));
  type: module
  ok: true
  port_count: 5

ports:
  direction highconn.full_name highconn.name highconn.npi_type highconn.text highconn.type lowconn.full_name lowconn.name lowconn.npi_type lowconn.text lowconn.type port.full_name port.name port.npi_type port.text port.type trace.confidence trace.confidence_reason trace.has_statement_only trace.mode trace.ok trace query field trace.resolution trace.result_count trace.truncated
  input if_root_tb.rst_n rst_n 48 if_root_tb.rst_n reg if_root_tb.u_src.rst_n rst_n 36 if_root_tb.u_src.rst_n net rst_n 44 rst_n port low trace contains statement_only fallback records true driver true if_root_tb.rst_n statement_only 2 false
  input if_root_tb.sel sel 48 if_root_tb.sel reg if_root_tb.u_src.sel sel 36 if_root_tb.u_src.sel net sel 44 sel port low trace contains statement_only fallback records true driver true if_root_tb.sel statement_only 3 false
  input if_root_tb.a a 48 if_root_tb.a reg if_root_tb.u_src.a a 36 if_root_tb.u_src.a net a 44 a port low trace contains statement_only fallback records true driver true if_root_tb.a statement_only 1 false
  input if_root_tb.b b 48 if_root_tb.b reg if_root_tb.u_src.b b 36 if_root_tb.u_src.b net b 44 b port low trace contains statement_only fallback records true driver true if_root_tb.b statement_only 1 false
  direction_-1 if_root_tb.link link 608 if_root_tb.link ref_obj if_root_tb.u_src.bus bus 608 if_root_tb.u_src.bus ref_obj bus 44 bus port unknown false driver true if_root_tb.link unknown 0 false
  query: if_root_tb.u_src
```

Assessment:

`port.trace` exposes port mapping plus per-port trace facts, but the XOUT table is too wide for practical agent or human consumption. The trace confidence is low for several rows and leans on statement-only fallback records. This looks more like internal diagnostic material than a useful public action.

### `instance.map`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "instance.map",
  "target": {"session_id": "<opened-session>"},
  "args": {"path": "if_root_tb.u_src"},
  "output": {"verbosity": "compact"}
}
```

XOUT:

```text
@xdebug.instance.map.v1
summary:
  ok: true
  port_count: 5
  query: if_root_tb.u_src

instance:
  full_name: if_root_tb.u_src

location:
  file: <xverif-repo>/xdebug/testdata/combined/interface_port_root/if_root_tb.sv
  line: 50
  name: u_src
  npi_type: 32
  text: if_source  u_src(.rst_n(if_root_tb.rst_n), .sel(if_root_tb.sel), .a(if_root_tb.a), .b(if_root_tb.b), .bus(if_root_tb.link));
  type: module
  ok: true
  port_count: 5

ports:
  direction highconn.full_name highconn.name highconn.npi_type highconn.text highconn.type lowconn.full_name lowconn.name lowconn.npi_type lowconn.text lowconn.type port.full_name port.name port.npi_type port.text port.type
  input if_root_tb.rst_n rst_n 48 if_root_tb.rst_n reg if_root_tb.u_src.rst_n rst_n 36 if_root_tb.u_src.rst_n net rst_n 44 rst_n port
  input if_root_tb.sel sel 48 if_root_tb.sel reg if_root_tb.u_src.sel sel 36 if_root_tb.u_src.sel net sel 44 sel port
  input if_root_tb.a a 48 if_root_tb.a reg if_root_tb.u_src.a a 36 if_root_tb.u_src.a net a 44 a port
  input if_root_tb.b b 48 if_root_tb.b reg if_root_tb.u_src.b b 36 if_root_tb.u_src.b net b 44 b port
  direction_-1 if_root_tb.link link 608 if_root_tb.link ref_obj if_root_tb.u_src.bus bus 608 if_root_tb.u_src.bus ref_obj bus 44 bus port
  query: if_root_tb.u_src
```

Assessment:

`instance.map` is the most understandable of the three because it answers "what is this instance connected to?" However, it still exposes low-level NPI type numbers and raw connection fields instead of a compact, user-oriented mapping.

### `interface.resolve`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "interface.resolve",
  "target": {"session_id": "<opened-session>"},
  "args": {"path": "if_root_tb.link"},
  "output": {"verbosity": "compact"}
}
```

XOUT:

```text
@xdebug.interface.resolve.v1
summary:
  modport_port_count: 0
  ok: true
  port_count: 1
  query: if_root_tb.link

data:
  modport_port_count: 0
  modport_ports: [empty]

object:
  full_name: if_root_tb.link

location:
  file: <xverif-repo>/xdebug/testdata/combined/interface_port_root/if_root_tb.sv
  line: 48
  name: link
  npi_type: 601
  text: data_if  link(.clk(if_root_tb.clk));
  type: interface
  ok: true
  port_count: 1

ports:
  direction highconn.full_name highconn.name highconn.npi_type highconn.text highconn.type lowconn.full_name lowconn.name lowconn.npi_type lowconn.text lowconn.type port.full_name port.name port.npi_type port.text port.type
  input if_root_tb.clk clk 48 if_root_tb.clk reg if_root_tb.link.clk clk 36 if_root_tb.link.clk net clk 44 clk port
  query: if_root_tb.link
```

Assessment:

`interface.resolve` has weak user-facing value in this fixture. It identifies the interface instance and its clock connection, but it reports `modport_port_count: 0` and does not surface the interface data/modport relationship that a user would likely expect.

## Follow-Up If Removal Is Chosen

If these actions are later removed, update these surfaces together:

- `xdebug/docs/action-inventory.md`
- `xdebug/specs/actions/actions.yaml`
- `xdebug/schemas/v1/actions/*.schema.json`
- `xdebug/examples/requests/*.basic.json`
- `xdebug/examples/responses/*.basic.json`
- `xdebug/src/engine/service/engine_design_handlers.cpp`
- contract tests that assert public action inventory

Removal follow-up completed in this cleanup: `xdebug/tests/design/run_semantics.sh`, `xdebug/tests/waveform/run_complex_wave.py`, public schema/example files, `doc/json_after_cleanup`, and `xverif_mcp/tools/test_actions.py` no longer depend on these actions.

## Waveform Delete Candidate Evidence

These examples were run on a real local waveform database outside the sandbox because waveform/NPI/license-backed actions must run outside the sandbox.

Database:

```text
xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb
```

### `signal.trend`

Request intent:

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.trend",
  "target": {"session_id": "<opened-session>"},
  "args": {
    "signal": "ai_complex_top.counter_nonmono",
    "clock": "ai_complex_top.clk",
    "time_range": {"begin": "40ns", "end": "110ns"}
  },
  "output": {"verbosity": "compact"}
}
```

XOUT:

```text
@xdebug.signal.trend.v1
data:
  signal: ai_complex_top.counter_nonmono
  sample_count: 7
  unknown_count: 0
  stable: false
  truncated: false
  initial_value: 5
  final_value: 8
  min_value: 4
  max_value: 8
  monotonic: none
```

Assessment:

`signal.trend` provides only a coarse sampled trend summary: first/final/min/max, stable flag, and monotonic class. It does not show the sampled timeline, transition evidence, or root-cause context. For agent-facing debug, this appears weaker than `signal.statistics`, `signal.changes`, or domain-specific checks. Marked as a delete candidate.
