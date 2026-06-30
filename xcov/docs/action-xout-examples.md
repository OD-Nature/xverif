# xcov action xout examples

本文件由真实 VDB `/home/yian/uart_example/sim/merged.vdb` 生成。每个条目包含请求 JSON 和真实 `xout` 返回。

生成约束：使用真实 NPI backend，不解析 URG HTML，不包含旧 action。

## actions

### Request

```json
{"api_version":"xcov.v1","request_id":"actions","action":"actions"}
```

### XOUT

```text
XOUT_BEGIN request_id=actions action=actions
@xcov.v1 ok action=actions request_id=actions

summary:
  matched_count: 18
  returned: 18
  truncated: false
  output_path: null

items:
  name                       status  api_version
  session.open               p0      xcov.v1
  session.status             p0      xcov.v1
  session.close              p0      xcov.v1
  tests.list                 p0      xcov.v1
  metrics.list               p0      xcov.v1
  scope.summary              p0      xcov.v1
  scope.children             p0      xcov.v1
  scope.search               p0      xcov.v1
  code_coverage.summary      p0      xcov.v1
  code_coverage.holes        p0      xcov.v1
  function_coverage.summary  p0      xcov.v1
  function_coverage.holes    p0      xcov.v1
  source.map                 p0      xcov.v1
  source.annotate            p0      xcov.v1
  assert.summary             p0      xcov.v1
  export.code_coverage       p0      xcov.v1
  export.function_coverage   p0      xcov.v1
  export.assert              p0      xcov.v1

XOUT_END request_id=actions
```

## session.open

### Request

```json
{"api_version":"xcov.v1","request_id":"open","action":"session.open","target":{"vdb":"/home/yian/uart_example/sim/merged.vdb"},"args":{"name":"live-doc","reuse":false}}
```

### XOUT

```text
XOUT_BEGIN request_id=open action=session.open
@xcov.v1 ok action=session.open request_id=open

summary:
  session_id: live-doc
  state: alive
  vdb: /home/yian/uart_example/sim/merged.vdb
  test_count: 1
  top_scope_count: null
  worker: npi_python
  matched_count: 1
  returned: 1
  truncated: false
  output_path: null

XOUT_END request_id=open
```

## session.status

### Request

```json
{"api_version":"xcov.v1","request_id":"session-status","action":"session.status","target":{"session_id":"live-doc"}}
```

### XOUT

```text
XOUT_BEGIN request_id=session-status action=session.status
@xcov.v1 ok action=session.status request_id=session-status

summary:
  session_id: live-doc
  state: alive
  vdb: /home/yian/uart_example/sim/merged.vdb
  test_count: 1
  top_scope_count: null
  worker: npi_python
  cached_indexes: lazy
  matched_count: 1
  returned: 1
  truncated: false
  output_path: null

XOUT_END request_id=session-status
```

## tests.list

### Request

```json
{"api_version":"xcov.v1","request_id":"tests-list","action":"tests.list","target":{"session_id":"live-doc"}}
```

### XOUT

```text
XOUT_BEGIN request_id=tests-list action=tests.list
@xcov.v1 ok action=tests.list request_id=tests-list

summary:
  matched_count: 1
  returned: 1
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc

filters:
  include: 
  exclude: 
  match_field: name

items:
  name
  /home/yian/uart_example/sim/merged.vdb/test

XOUT_END request_id=tests-list
```

## metrics.list

### Request

```json
{"api_version":"xcov.v1","request_id":"metrics-list","action":"metrics.list","target":{"session_id":"live-doc"}}
```

### XOUT

```text
XOUT_BEGIN request_id=metrics-list action=metrics.list
@xcov.v1 ok action=metrics.list request_id=metrics-list

summary:
  matched_count: 7
  returned: 7
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: null
  test: merged

items:
  metric      covered  coverable  missing  coverage_pct  name        full_name
  line        427      839        412      50.8939       line        line
  toggle      866      1652       786      52.4213       toggle      toggle
  branch      230      430        200      53.4884       branch      branch
  condition   488      598        110      81.6054       condition   condition
  fsm         45       66         21       68.1818       fsm         fsm
  assert      32       38         6        84.2105       assert      assert
  functional  2946     4138       1192     71.1938       functional  functional

XOUT_END request_id=metrics-list
```

## scope.summary

### Request

```json
{"api_version":"xcov.v1","request_id":"scope-summary","action":"scope.summary","target":{"session_id":"live-doc"},"args":{"scope":"uart_tb"}}
```

### XOUT

```text
XOUT_BEGIN request_id=scope-summary action=scope.summary
@xcov.v1 ok action=scope.summary request_id=scope-summary

summary:
  matched_count: 1
  returned: 1
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: uart_tb
  test: merged

filters:
  include: 
  exclude: 
  match_field: full_name

items:
  name     full_name  covered  coverable  missing  coverage_pct
  uart_tb  uart_tb    2052     2900       848      70.7586

coverage:
  metric      coverage_pct
  line        95.7547
  toggle      52.8049
  branch      93.2489
  condition   97.1944
  fsm         68.1818
  assert      92.3077
  functional  62.5

XOUT_END request_id=scope-summary
```

## scope.children

### Request

```json
{"api_version":"xcov.v1","request_id":"scope-children","action":"scope.children","target":{"session_id":"live-doc"},"args":{"scope":"uart_tb","limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=scope-children action=scope.children
@xcov.v1 ok action=scope.children request_id=scope-children

summary:
  matched_count: 7
  returned: 5
  truncated: true
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: uart_tb
  test: merged

filters:
  include: 
  exclude: 
  match_field: full_name

items:
  name                  full_name                     coverage_pct
  APB                   uart_tb.APB                   22.2689
  APB_PROTOCOL_MONITOR  uart_tb.APB_PROTOCOL_MONITOR  31.8966
  DUT                   uart_tb.DUT                   78.7968
  IRQ                   uart_tb.IRQ                   100.0
  MODEM                 uart_tb.MODEM                 100.0

XOUT_END request_id=scope-children
```

## scope.search

### Request

```json
{"api_version":"xcov.v1","request_id":"scope-search","action":"scope.search","target":{"session_id":"live-doc"},"args":{"query":{"include_patterns":["*uart*"],"match_field":"full_name"},"limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=scope-search action=scope.search
@xcov.v1 ok action=scope.search request_id=scope-search

summary:
  matched_count: 15
  returned: 5
  truncated: true
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: null
  test: merged

filters:
  include: *uart*
  exclude: 
  match_field: full_name

items:
  name                  full_name                     coverage_pct
  uart_seq_pkg          uart_seq_pkg                  100.0
  uart_tb               uart_tb                       70.7586
  uart_vseq_pkg         uart_vseq_pkg                 60.0
  APB                   uart_tb.APB                   22.2689
  APB_PROTOCOL_MONITOR  uart_tb.APB_PROTOCOL_MONITOR  31.8966

XOUT_END request_id=scope-search
```

## code_coverage.summary

### Request

```json
{"api_version":"xcov.v1","request_id":"code-summary","action":"code_coverage.summary","target":{"session_id":"live-doc"},"args":{"group_by":"metric"}}
```

### XOUT

```text
XOUT_BEGIN request_id=code-summary action=code_coverage.summary
@xcov.v1 ok action=code_coverage.summary request_id=code-summary

summary:
  matched_count: 6
  returned: 6
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: null
  test: merged
  metrics: line,toggle,branch,condition,fsm,assert

filters:
  include: 
  exclude: 
  match_field: full_name

items:
  metric     covered  coverable  missing  coverage_pct  name       full_name
  line       427      839        412      50.8939       line       line
  toggle     866      1652       786      52.4213       toggle     toggle
  branch     230      430        200      53.4884       branch     branch
  condition  488      598        110      81.6054       condition  condition
  fsm        45       66         21       68.1818       fsm        fsm
  assert     32       38         6        84.2105       assert     assert

XOUT_END request_id=code-summary
```

## code_coverage.holes

### Request

```json
{"api_version":"xcov.v1","request_id":"code-holes","action":"code_coverage.holes","target":{"session_id":"live-doc"},"args":{"scope":"uart_tb","metrics":["line","toggle","branch","condition","fsm","assert"],"query":{"exclude_patterns":["*uvm*"],"match_field":"full_name"},"limits":{"max_items":8}}}
```

### XOUT

```text
XOUT_BEGIN request_id=code-holes action=code_coverage.holes
@xcov.v1 ok action=code_coverage.holes request_id=code-holes

summary:
  matched_count: 4
  returned: 4
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: uart_tb
  test: merged
  metrics: line,toggle,branch,condition,fsm,assert
  note: Detailed uncovered code coverage items are available via export.code_coverage. For complex processing, use x-npi and learn the pynpi coverage APIs.

filters:
  include: 
  exclude: *uvm*
  match_field: full_name

items:
  name                  full_name                     coverage_pct  line_pct  toggle_pct  branch_pct  condition_pct  fsm_pct  assert_pct
  uart_tb               uart_tb                       70.7815       95.7547   52.8049     93.2489     97.1944        68.1818  92.3077
  APB                   uart_tb.APB                   22.2689       null      21.6102     null        null           null     100.0
  APB_PROTOCOL_MONITOR  uart_tb.APB_PROTOCOL_MONITOR  30.8036       100.0     24.7573     null        null           null     100.0
  DUT                   uart_tb.DUT                   78.7968       95.5556   62.7367     93.2489     97.1944        68.1818  75.0

XOUT_END request_id=code-holes
```

## function_coverage.summary

### Request

```json
{"api_version":"xcov.v1","request_id":"function-summary","action":"function_coverage.summary","target":{"session_id":"live-doc"},"args":{"group_by":"covergroup","limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=function-summary action=function_coverage.summary
@xcov.v1 ok action=function_coverage.summary request_id=function-summary

summary:
  matched_count: 15
  returned: 5
  truncated: true
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  test: merged

filters:
  include: 
  exclude: 
  match_field: full_name

items:
  covergroup                                                            covered  coverable  missing  coverage_pct  raw_coverage_pct
  uart_tb.APB_PROTOCOL_MONITOR::APB_accesses_cg                         5        8          3        66.6667       62.5
  modem_agent_pkg::modem_coverage_monitor::modem_lines_cg               272      272        0        100.0         100.0
  uart_env_pkg::uart_interrupt_coverage_monitor::tx_word_format_int_cg  51       51         0        100.0         100.0
  uart_env_pkg::uart_rx_coverage_monitor::rx_word_format_cg             51       51         0        100.0         100.0
  uart_env_pkg::uart_reg_access_coverage_monitor::reg_access_cg         27       27         0        100.0         100.0

XOUT_END request_id=function-summary
```

## function_coverage.holes

### Request

```json
{"api_version":"xcov.v1","request_id":"function-holes","action":"function_coverage.holes","target":{"session_id":"live-doc"},"args":{"levels":["bin"],"query":{"include_patterns":["*APB_accesses_cg*"],"match_field":"full_name"},"limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=function-holes action=function_coverage.holes
@xcov.v1 ok action=function_coverage.holes request_id=function-holes

summary:
  matched_count: 3
  returned: 3
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  test: merged

filters:
  include: *APB_accesses_cg*
  exclude: 
  match_field: full_name

items:
  covergroup                                     coverpoint  cross    bin          covered  coverable  count  coverage_pct  status       file                                                            line
  uart_tb.APB_PROTOCOL_MONITOR::APB_accesses_cg  ERR         null     err          0        1          0      0.0           not_covered  /home/yian/uart_example/sim/../protocol_monitor/apb_monitor.sv  130
  uart_tb.APB_PROTOCOL_MONITOR::APB_accesses_cg  null        APB_CVR  [write|err]  0        1          0      0.0           not_covered  /home/yian/uart_example/sim/../protocol_monitor/apb_monitor.sv  135
  uart_tb.APB_PROTOCOL_MONITOR::APB_accesses_cg  null        APB_CVR  [read|err]   0        1          0      0.0           not_covered  /home/yian/uart_example/sim/../protocol_monitor/apb_monitor.sv  135

XOUT_END request_id=function-holes
```

## source.map

### Request

```json
{"api_version":"xcov.v1","request_id":"source-map","action":"source.map","target":{"session_id":"live-doc"},"args":{"file":"host_if_seq_pkg.sv","line":20,"window":0,"metrics":["assert"],"limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=source-map action=source.map
@xcov.v1 ok action=source.map request_id=source-map

summary:
  matched_count: 0
  returned: 0
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  file: host_if_seq_pkg.sv
  line: 20
  window: 0

filters:
  include: 
  exclude: 
  match_field: full_name

items:

XOUT_END request_id=source-map
```

## source.annotate

### Request

```json
{"api_version":"xcov.v1","request_id":"source-annotate","action":"source.annotate","target":{"session_id":"live-doc"},"args":{"file":"host_if_seq_pkg.sv","line":20,"window":0,"metrics":["assert"],"include_source_text":true,"limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=source-annotate action=source.annotate
@xcov.v1 ok action=source.annotate request_id=source-annotate

summary:
  matched_count: 0
  returned: 0
  truncated: false
  output_mode: inline
  output_path: null
  artifact_format: json
  note: source text is unavailable from file path; coverage annotations still use NPI evidence
  session_id: live-doc
  file: host_if_seq_pkg.sv
  line: 20
  window: 0
  include_source_text: true

filters:
  include: 
  exclude: 
  match_field: full_name

items:

XOUT_END request_id=source-annotate
```

## assert.summary

### Request

```json
{"api_version":"xcov.v1","request_id":"assert-summary","action":"assert.summary","target":{"session_id":"live-doc"},"args":{"limits":{"max_items":5}}}
```

### XOUT

```text
XOUT_BEGIN request_id=assert-summary action=assert.summary
@xcov.v1 ok action=assert.summary request_id=assert-summary

summary:
  matched_count: 38
  returned: 5
  truncated: true
  output_mode: inline
  output_path: null
  artifact_format: json
  session_id: live-doc
  scope: null
  test: merged

filters:
  include: 
  exclude: 
  match_field: full_name

items:
  name               full_name          covered  coverable  missing  coverage_pct  status       attempts  real_successes  without_attempts
  TX_BUSY_CHK        TX_BUSY_CHK        1        1          0        100.0         covered      11332430  878             0
  TX_FIFO_EMPTY_CHK  TX_FIFO_EMPTY_CHK  1        1          0        100.0         covered      11332430  11103458        0
  TX_FIFO_FULL_CHK   TX_FIFO_FULL_CHK   1        1          0        100.0         covered      11332430  3317            0
  TX_FIFO_OK_CHK     TX_FIFO_OK_CHK     1        1          0        100.0         covered      11332430  225649          0
  RX_BE_CHK          RX_BE_CHK          0        1          1        0.0           not_covered  11332430  0               0

XOUT_END request_id=assert-summary
```

## export.code_coverage

### Request

```json
{"api_version":"xcov.v1","request_id":"export-code","action":"export.code_coverage","target":{"session_id":"live-doc"},"args":{"scope":"uart_tb","threshold_pct":100.0,"output":{"path":"/tmp/xcov-doc-code-coverage.md","allow_absolute_path":true}}}
```

### XOUT

```text
XOUT_BEGIN request_id=export-code action=export.code_coverage
@xcov.v1 ok action=export.code_coverage request_id=export-code

summary:
  session_id: live-doc
  scope: uart_tb
  test: merged
  threshold_pct: 100.0
  matched_count: 236
  returned: 0
  truncated: false
  output_mode: file
  output_path: /tmp/xcov-doc-code-coverage.md
  artifact_format: md
  note: Markdown export only. For complex processing, use x-npi and learn the pynpi coverage APIs.

items:

XOUT_END request_id=export-code
```

## export.function_coverage

### Request

```json
{"api_version":"xcov.v1","request_id":"export-function","action":"export.function_coverage","target":{"session_id":"live-doc"},"args":{"threshold_pct":100.0,"output":{"path":"/tmp/xcov-doc-function-coverage.md","allow_absolute_path":true}}}
```

### XOUT

```text
XOUT_BEGIN request_id=export-function action=export.function_coverage
@xcov.v1 ok action=export.function_coverage request_id=export-function

summary:
  session_id: live-doc
  scope: null
  test: merged
  threshold_pct: 100.0
  matched_count: 465
  returned: 0
  truncated: false
  output_mode: file
  output_path: /tmp/xcov-doc-function-coverage.md
  artifact_format: md
  note: Markdown export only. For complex processing, use x-npi and learn the pynpi coverage APIs.

items:

XOUT_END request_id=export-function
```

## export.assert

### Request

```json
{"api_version":"xcov.v1","request_id":"export-assert","action":"export.assert","target":{"session_id":"live-doc"},"args":{"scope":"uart_tb","threshold_pct":100.0,"output":{"path":"/tmp/xcov-doc-assert.md","allow_absolute_path":true}}}
```

### XOUT

```text
XOUT_BEGIN request_id=export-assert action=export.assert
@xcov.v1 ok action=export.assert request_id=export-assert

summary:
  session_id: live-doc
  scope: uart_tb
  test: merged
  threshold_pct: 100.0
  matched_count: 9
  returned: 0
  truncated: false
  output_mode: file
  output_path: /tmp/xcov-doc-assert.md
  artifact_format: md
  note: Markdown export only. For complex processing, use x-npi and learn the pynpi coverage APIs.

items:

XOUT_END request_id=export-assert
```

## session.close

### Request

```json
{"api_version":"xcov.v1","request_id":"session-close","action":"session.close","target":{"session_id":"live-doc"}}
```

### XOUT

```text
XOUT_BEGIN request_id=session-close action=session.close
@xcov.v1 ok action=session.close request_id=session-close

summary:
  session_id: live-doc
  state: closed
  vdb: /home/yian/uart_example/sim/merged.vdb
  test_count: 1
  top_scope_count: null
  worker: npi_python
  matched_count: 1
  returned: 1
  truncated: false
  output_path: null

XOUT_END request_id=session-close
```
