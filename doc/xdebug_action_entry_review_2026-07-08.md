# xdebug 全 action 入口与调试可用性评审

日期：2026-07-08。范围：当前 live catalog 70 个公开 xdebug action，覆盖 native `tools/xdebug --json -` 与 MCP 默认 xout 入口。

## 总览

- action 数量：70；分类分布：builtin=3，combined=2，design=6，session=6，waveform=53。
- native：worker 最终 `ok && response schema` 为 70/70；本报告抽取 native evidence 得到 native_ok=70/70、schema=70/70。主线程普通 HOME/UDS 聚合曾为 69/70，缺口是 `axi.request_response_pair`，隔离 HOME 重跑后通过。
- MCP：默认 xout 可读证据 70/70；target 调用最终 pass 69/70；`session.open` 是 raw xout wrapper blocker，但 backend xout 已产生。
- 发生失败或重试的 action：23/70。失败重试被作为入口可用性证据保留，不从结论中隐藏。
- 高复杂度 action：`counter.statistics`(17)，`event.export`(24)，`event.find`(24)，`expr.eval_at`(18)，`handshake.inspect`(21)，`signal.statistics`(17)，`stream.query`(17)，`value.batch_at`(16)。
- response schema 普遍开放：静态检查显示大部分 action 的 top/summary/data 仍允许额外字段或未约束业务 payload，schema 能验证 envelope，但 debug 字段稳定性不足。

## 双入口评审

- Native binary 入口最清晰：完整 `xdebug.v1` envelope，已用 action-specific response schema 校验；缺点是要调用者自己管理 `target.session_id` 和 session 生命周期。
- MCP query 入口最适合 AI 交互：`xverif_debug_session_open -> xverif_debug_query(session_id, action, args) -> close`，默认 xout 可读；风险是 MCP 外层 `args` 与 action inner `args` 同名，容易嵌套错。
- MCP raw_request 的 `output_format:"xout"` 存在 wrapper 问题：backend 输出了 xout 文本，但 wrapper 试图按 JSON 解析，返回 `XVERIF_BAD_JSON_RESPONSE`。
- AXI 重查询对 direct socket 30s timeout 敏感；`axi.analysis`、`axi.query`、`axi.request_response_pair` 需要更小 `time_range`、更低 limit，或更明确的 timeout/进度提示。

## 主要设计风险

- `list.export` schema/runtime 不一致：schema 允许 `tsv`，runtime 要求 `u64bin` 或 `hex_tsv`，但 `hex_tsv` 又被 schema 拒绝。
- `list.delete` schema 允许 integer `index`，实际 integer 触发 `INTERNAL_ENGINE_EXCEPTION type must be string`，字符串 index 成功。
- `stream.export` 直觉中的 `beats` 与 runtime enum 不一致，实际是 `transfer|packet|packet_beats`。
- `apb.query`/`axi.query` 的数量限制不是通用 `args.limit`，误传会被 schema 拒绝；需要明确 `num` 与 top-level `limits` 的边界。
- `session.gc` 是有副作用的清理 action，本轮真实执行曾移除非本轮 unhealthy native session；文档和工具说明应避免把它当只读检查。
- response schema 约束偏松，很多 action 的调试价值依赖 xout 文本和具体 `summary/data` 约定，而不是 schema 强合同。

## 证据文件

- `<repo>/tmp/xdebug_action_review_20260708/action_metadata.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/static_review.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/static_summary.md`
- `<repo>/tmp/xdebug_action_review_20260708/native_evidence.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/native_summary.md`
- `<repo>/tmp/xdebug_action_review_20260708/native_merged_best.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/native_retry_evidence.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/mcp_evidence.jsonl`
- `<repo>/tmp/xdebug_action_review_20260708/mcp_summary.md`
- `<repo>/tmp/xdebug_action_review_20260708/mcp_evidence_review.md`
- `<repo>/tmp/xdebug_action_review_20260708/fresh_agent_review.md`

## Action 逐项评审

## Action: `actions`

**Action / Category / Requires / Status**：`actions` / `builtin` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出当前运行时公开 action catalog。

**Native JSON Entry**：`tools/xdebug --json -`，action=`actions`，target keys=[]，args keys=[]。 required args=[]，optional args count=0。
```json
{
  "action": "actions",
  "api_version": "xdebug.v1",
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=actions, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.actions.v1
- summary:
- action_count: 70
- removed_count: 1
- 
- implemented:
- native key data: {"_bytes": 35246, "_truncated_json": "{\"actions\": [{\"category\": \"builtin\", \"handler_kind\": \"actions\", \"name\": \"actions\", \"request_examples\": [\"examples/requests/actions.basic.json\"], \"request_schema\": \"schemas/v1/actions/actions.request...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_actions_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=actions, output_format=xout) -> .json engine_forward apb.query waveform stable waveform schemas/v1/actions/apb.query.request.schema.json schemas/v1/actions/apb.query.response.schema.json engine_forward apb.tra...

**Parameter Complexity**：中。score=0，required=0，optional=0，真实重试=1。AI 主要风险：raw_request xout 会触发 MCP wrapper JSON 解析错误；query 入口可读。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于元入口，native envelope、MCP tool、batch 嵌套 args 容易混淆。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 raw_request xout 会触发 MCP wrapper JSON 解析错误；query 入口可读。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `apb.config.list`

**Action / Category / Requires / Status**：`apb.config.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出 APB 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`apb.config.list`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=2。
```json
{
  "action": "apb.config.list",
  "api_version": "xdebug.v1",
  "args": {
    "name": "apb0"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_apb"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=apb.config.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.apb.config.list.v1
- data:
- name: apb0
- sampling_mode: clock_edge
- clock: apb_vip_fixture_top.clk
- edge: posedge
- native key data: {"clock": "apb_vip_fixture_top.clk", "edge": "posedge", "name": "apb0", "pready": "apb_vip_fixture_top.apb_if.pready[0]", "pslverr": "apb_vip_fixture_top.apb_if.pslverr[0]", "rst_n": "apb_vip_fixture_top.rst_n", "sample_point": "before", "sampling_mode": "c...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_apb_config_list_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=4，required=1，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `apb.config.load`

**Action / Category / Requires / Status**：`apb.config.load` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：加载 APB 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`apb.config.load`，target keys=['session_id']，args keys=['config', 'name']。 required args=['name']，optional args count=4。
```json
{
  "action": "apb.config.load",
  "api_version": "xdebug.v1",
  "args": {
    "config": {
      "clock": "apb_vip_fixture_top.clk",
      "edge": "posedge",
      "paddr": "apb_vip_fixture_top.apb_if.paddr",
      "penable": "apb_vip_fixture_top.apb_if.penable",
      "prdata": "apb_vip_fixture_top.apb_if.prdata[0]",
      "pready": "apb_vip_fixture_top.apb_if.pready[0]",
      "psel": "apb_vip_fixture_top.apb_if.psel[0]",
      "pslverr": "apb_vip_fixture_top.apb_if.pslverr[0]",
      "pwdata": "apb_vip_fixture_top.apb_if.pwdata",
      "pwrite": "apb_vip_fixture_top.apb_if.pwrite",
      "rst_n": "apb_vip_fixture_top.rst_n"
    },
    "name": "apb0"
  },
  "output": {
    "pretty": false,
  ... truncated ...
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=apb.config.load, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.apb.config.load.v1
- summary:
- name: apb0
- status: loaded
- 
- data:
- native key data: {"config": {"clock": "apb_vip_fixture_top.clk", "edge": "posedge", "name": "apb0", "pready": "apb_vip_fixture_top.apb_if.pready[0]", "pslverr": "apb_vip_fixture_top.apb_if.pslverr[0]", "rst_n": "apb_vip_fixture_top.rst_n", "sample_point": "before", "samplin...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_apb_config_load_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=10，required=1，optional=4，分支 anyOf=1/oneOf=0。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `apb.cursor`

**Action / Category / Requires / Status**：`apb.cursor` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：在 APB transfer 间移动游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`apb.cursor`，target keys=['session_id']，args keys=['direction', 'name', 'op']。 required args=['name', 'op']，optional args count=3。
```json
{
  "action": "apb.cursor",
  "api_version": "xdebug.v1",
  "args": {
    "direction": "all",
    "name": "apb0",
    "op": "begin"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_apb"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=apb.cursor, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.apb.cursor.v1
- summary:
- name: apb0
- op: begin
- direction: all
- found: true
- native key data: {"transaction": {"addr": "00000000", "data": "11223344", "has_error": false, "is_write": true, "time": 125000}}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_apb_cursor_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=7，required=2，optional=3。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `apb.query`

**Action / Category / Requires / Status**：`apb.query` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查询 APB transfer。

**Native JSON Entry**：`tools/xdebug --json -`，action=`apb.query`，target keys=['session_id']，args keys=['address', 'direction', 'name']。 required args=['name']，optional args count=7。
```json
{
  "action": "apb.query",
  "api_version": "xdebug.v1",
  "args": {
    "address": "'hf0",
    "direction": "read",
    "name": "apb0"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_apb"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=apb.query, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.apb.query.v1
- summary:
- name: apb0
- direction: write
- found: true
- addr: 00000000
- native key data: {"transaction": {"addr": "000000f0", "data": "bad000f0", "has_error": true, "is_write": false, "time": 525000}}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_apb_query_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=apb.query, default xout) -> xverif_debug_session_close -> validation failed for additional property 'limit': instance invalid as per false-schema

**Parameter Complexity**：中。score=9，required=1，optional=7，真实重试=1。AI 主要风险：args.limit 会被 schema 拒绝；应使用 num 或 top-level limits。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 args.limit 会被 schema 拒绝；应使用 num 或 top-level limits。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `apb.transfer_window`

**Action / Category / Requires / Status**：`apb.transfer_window` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：实验性 APB 窗口分析。

**Native JSON Entry**：`tools/xdebug --json -`，action=`apb.transfer_window`，target keys=['session_id']，args keys=['limit', 'name', 'time_range']。 required args=['name']，optional args count=4。
```json
{
  "action": "apb.transfer_window",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 20,
    "name": "apb0",
    "time_range": {
      "begin": "0ns",
      "end": "1us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_apb"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=apb.transfer_window, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.apb.transfer_window.v1
- summary:
- name: apb0
- begin: 0ns
- end: 1000000ns
- transaction_count: 2
- native key data: {"transactions": [{"addr": "'h00000000", "data": "'h11223344", "has_error": false, "time": "125ns", "type": "WR"}, {"addr": "'h00000004", "data": "'h55667788", "has_error": false, "time": "165ns", "type": "WR"}, {"addr": "'h00000008", "data": "'ha5a55a5a", ...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_apb_transfer_window_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=7，required=1，optional=4。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.analysis`

**Action / Category / Requires / Status**：`axi.analysis` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：汇总 AXI 行为。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.analysis`，target keys=['session_id']，args keys=['analysis', 'direction', 'name']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.analysis",
  "api_version": "xdebug.v1",
  "args": {
    "analysis": "latency",
    "direction": "all",
    "name": "axi0"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.analysis, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.analysis.v1
- summary:
- name: axi0
- analysis: osd
- max: 134.0
- min: 0.0
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_axi_analysis_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=axi.analysis, default xout) -> xverif_debug_session_close -> direct session socket timed out after 30000ms: ~/.xdebug/engine/sessions/mcp_axi_axi_anal_c2c40de945c6a522/socket

**Parameter Complexity**：中。score=6，required=1，optional=4，真实重试=1。AI 主要风险：latency 分析在 MCP direct 入口触发 30s timeout；osd 成功但耗时接近上限。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 latency 分析在 MCP direct 入口触发 30s timeout；osd 成功但耗时接近上限。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.channel_stall`

**Action / Category / Requires / Status**：`axi.channel_stall` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：实验性 AXI stall 分析。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.channel_stall`，target keys=['session_id']，args keys=['channel', 'limit', 'name', 'time_range']。 required args=['name']，optional args count=6。
```json
{
  "action": "axi.channel_stall",
  "api_version": "xdebug.v1",
  "args": {
    "channel": "aw",
    "limit": 8,
    "name": "axi0",
    "time_range": {
      "begin": "0ns",
      "end": "1us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.channel_stall, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.channel_stall.v1
- summary:
- sampling_mode: clock_edge
- clock: axi_vip_fixture_top.clk
- edge: posedge
- sample_time_semantics: time is sample_time
- native key data: {"channel": "aw", "data_stability_violations": 0, "findings": [], "name": "axi0", "ready_without_valid_cycles": 87}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_channel_stall_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=13，required=1，optional=6，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.config.list`

**Action / Category / Requires / Status**：`axi.config.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出 AXI 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.config.list`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=2。
```json
{
  "action": "axi.config.list",
  "api_version": "xdebug.v1",
  "args": {
    "name": "axi0"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.config.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.config.list.v1
- data:
- name: axi0
- sampling_mode: clock_edge
- clock: axi_vip_fixture_top.clk
- edge: posedge
- native key data: {"clock": "axi_vip_fixture_top.clk", "edge": "posedge", "name": "axi0", "rst_n": "axi_vip_fixture_top.rst_n", "sample_point": "before", "sampling_mode": "clock_edge"}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_config_list_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=4，required=1，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.config.load`

**Action / Category / Requires / Status**：`axi.config.load` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：加载 AXI 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.config.load`，target keys=['session_id']，args keys=['config', 'name']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.config.load",
  "api_version": "xdebug.v1",
  "args": {
    "config": {
      "araddr": "axi_vip_fixture_top.axi_vip_if.master_if[0].araddr",
      "arburst": "axi_vip_fixture_top.axi_vip_if.master_if[0].arburst",
      "arid": "axi_vip_fixture_top.axi_vip_if.master_if[0].arid",
      "arlen": "axi_vip_fixture_top.axi_vip_if.master_if[0].arlen",
      "arready": "axi_vip_fixture_top.axi_vip_if.master_if[0].arready",
      "arsize": "axi_vip_fixture_top.axi_vip_if.master_if[0].arsize",
      "arvalid": "axi_vip_fixture_top.axi_vip_if.master_if[0].arvalid",
      "awaddr": "axi_vip_fixture_top.axi_vip_if.master_if[0].awaddr",
      "awburst": "axi_vip_fixture_top.axi_vip_if.
  ... truncated ...
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.config.load, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.config.load.v1
- summary:
- name: axi0
- status: loaded
- 
- data:
- native key data: {"config": {"clock": "axi_vip_fixture_top.clk", "edge": "posedge", "name": "axi0", "rst_n": "axi_vip_fixture_top.rst_n", "sample_point": "before", "sampling_mode": "clock_edge"}}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_config_load_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=10，required=1，optional=4，分支 anyOf=1/oneOf=0。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.cursor`

**Action / Category / Requires / Status**：`axi.cursor` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：在 AXI transfer 间移动游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.cursor`，target keys=['session_id']，args keys=['direction', 'name', 'op']。 required args=['name', 'op']，optional args count=3。
```json
{
  "action": "axi.cursor",
  "api_version": "xdebug.v1",
  "args": {
    "direction": "all",
    "name": "axi0",
    "op": "begin"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.cursor, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.cursor.v1
- summary:
- name: axi0
- op: begin
- direction: all
- found: true
- native key data: {"transaction": {"addr": "00000000000008c0", "id": "00", "is_write": true, "len": "000", "time": 415000}}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_cursor_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=7，required=2，optional=3。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.export`

**Action / Category / Requires / Status**：`axi.export` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：导出 AXI 数据。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.export`，target keys=['session_id']，args keys=['format', 'name', 'output', 'time_range']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.export",
  "api_version": "xdebug.v1",
  "args": {
    "format": "tsv",
    "name": "axi0",
    "output": {
      "path": "<repo>/tmp/xdebug_action_review_20260708/native_axi_export"
    },
    "time_range": {
      "begin": "0ns",
      "end": "1us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.export, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.export.v1
- summary:
- name: axi0
- write_count: 3200
- read_count: 3200
- total_count: 6400
- native key data: {"begin": "0ns", "end": "1000ns", "meta_file": "<repo>/tmp/xdebug_action_review_20260708/native_axi_export.meta.json", "read_file": "<repo>/tmp/xdebug_action_review_20260708/native_axi_export.read.tsv", "scan_begin": "0ns", "scan_end": "13973275ns", "write_file": "<repo>/tmp...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_export_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=11，required=1，optional=4，分支 anyOf=1/oneOf=0。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.latency_outlier`

**Action / Category / Requires / Status**：`axi.latency_outlier` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：实验性 AXI latency 异常。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.latency_outlier`，target keys=['session_id']，args keys=['limit', 'name', 'time_range']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.latency_outlier",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 5,
    "name": "axi0",
    "time_range": {
      "begin": "0ns",
      "end": "200ms"
    }
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.latency_outlier, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.latency_outlier.v1
- data:
- name: axi0
- begin: 0ns
- end: 200000000ns
- transaction_count: 5
- native key data: {"begin": "0ns", "end": "200000000ns", "name": "axi0", "outlier_count": 5, "outliers": [{"addr": "'h000000000000d4e0", "addr_time": "515ns", "beats": 12, "burst": "'h1", "data": ["'h000000000000000000000000000000000000000000000000000000000000000000000000000...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_latency_outlier_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=1。

**Parameter Complexity**：中。score=7，required=1，optional=4，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.outstanding_timeline`

**Action / Category / Requires / Status**：`axi.outstanding_timeline` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：实验性 AXI outstanding 时间线。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.outstanding_timeline`，target keys=['session_id']，args keys=['limit', 'name', 'time_range']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.outstanding_timeline",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 20,
    "name": "axi0",
    "time_range": {
      "begin": "0ns",
      "end": "200ms"
    }
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.outstanding_timeline, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.outstanding_timeline.v1
- summary:
- sampling_mode: clock_edge
- clock: axi_vip_fixture_top.clk
- edge: posedge
- sample_time_semantics: time is sample_time
- native key data: {"name": "axi0", "samples": [{"read": 0, "time": "205ns", "write": 0}, {"read": 0, "time": "215ns", "write": 0}, {"read": 0, "time": "225ns", "write": 0}, {"read": 0, "time": "235ns", "write": 0}, {"read": 0, "time": "245ns", "write": 0}, {"read": 0, "time"...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_axi_outstanding_timeline_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=1。

**Parameter Complexity**：中。score=7，required=1，optional=4，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.query`

**Action / Category / Requires / Status**：`axi.query` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查询 AXI channel/transaction。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.query`，target keys=['session_id']，args keys=['direction', 'name', 'num']。 required args=['name']，optional args count=7。
```json
{
  "action": "axi.query",
  "api_version": "xdebug.v1",
  "args": {
    "direction": "write",
    "name": "axi0",
    "num": 1
  },
  "limits": {
    "timeout_ms": 180000
  },
  "output": {
    "verbosity": "full"
  },
  "target": {
    "session_id": "native_retry3_20260708_3637875_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.query, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.query.v1
- summary:
- name: axi0
- direction: write
- found: true
- addr: 00000000000008c0
- native key data: {"transaction": {"addr": "00000000000008c0", "burst": "1", "data": ["00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_axi_query_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=axi.query, default xout) -> xverif_debug_session_close -> validation failed for additional property 'limit': instance invalid as per false-schema

**Parameter Complexity**：高。score=9，required=1，optional=7，真实重试=4。AI 主要风险：args.limit 会被 schema 拒绝；应使用 num 或 top-level limits；完整查询耗时接近 direct timeout。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 args.limit 会被 schema 拒绝；应使用 num 或 top-level limits；完整查询耗时接近 direct timeout。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `axi.request_response_pair`

**Action / Category / Requires / Status**：`axi.request_response_pair` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：实验性 AXI 请求响应配对。

**Native JSON Entry**：`tools/xdebug --json -`，action=`axi.request_response_pair`，target keys=['session_id']，args keys=['limit', 'name', 'time_range']。 required args=['name']，optional args count=4。
```json
{
  "action": "axi.request_response_pair",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 20,
    "name": "axi0",
    "time_range": {
      "begin": "0ns",
      "end": "200ms"
    }
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_axi"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=axi.request_response_pair, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.axi.request_response_pair.v1
- data:
- name: axi0
- begin: 0ns
- end: 1000ns
- transaction_count: 1
- native key data: {"begin": "0ns", "end": "200000000ns", "name": "axi0", "transaction_count": 20, "transactions": [{"addr": "'h000000000000ef58", "addr_time": "415ns", "beats": 13, "burst": "'h1", "data": ["'h000000000000000000000000000000000000000000000000000000000000000000...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry3_axi_request_response_pair_target_attempt3.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=axi.request_response_pair, default xout) -> xverif_debug_sessi... -> direct session socket timed out after 30000ms: ~/.xdebug/engine/sessions/mcp_axi_axi_requ_3ff04597de88d1c6/socket
- MCP attempt2: xverif_debug_session_open -> xverif_debug_query(action=axi.request_response_pair, default xout) -> xverif_debug_sessi... -> direct session transport failed for session: mcp_retry2_axi_request_response_pair_20260708

**Parameter Complexity**：高。score=7，required=1，optional=4，真实重试=3。AI 主要风险：大窗口容易 SESSION_TRANSPORT_FAILED；缩到 0ns..1us 且 limit=1 后成功。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 大窗口容易 SESSION_TRANSPORT_FAILED；缩到 0ns..1us 且 limit=1 后成功。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `batch`

**Action / Category / Requires / Status**：`batch` / `builtin` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：批量执行多个 xdebug request。

**Native JSON Entry**：`tools/xdebug --json -`，action=`batch`，target keys=[]，args keys=['mode', 'requests']。 required args=['requests']，optional args count=1。
```json
{
  "action": "batch",
  "api_version": "xdebug.v1",
  "args": {
    "mode": "continue_on_error",
    "requests": [
      {
        "action": "schema",
        "api_version": "xdebug.v1",
        "args": {
          "action": "actions",
          "kind": "response"
        },
        "output": {
          "pretty": false,
          "verbosity": "compact"
        }
      },
      {
        "action": "expr.normalize",
        "api_version": "xdebug.v1",
        "args": {
          "expr": "valid && !ready"
        },
        "output": {
          "pretty": false,
          "verbosity": "compact"
        }
      }
    ]
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=batch, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.batch.v1
- summary:
- count: 1
- all_ok: true
- 
- results:
- native key data: {"results": [{"action": "schema", "api_version": "xdebug.v1", "data": {"schema": {"$id": "xdebug.actions.response.v1", "$schema": "https://json-schema.org/draft/2020-12/schema", "additionalProperties": true, "description": "actions response: 列出当前运行时公开 actio...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_batch_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=batch, output_format=xout) -> @xdebug.batch.v1 summary: count: 1 all_ok: true results: api_version ok action tool.name tool.version summary.action summary.kind data.schema_path xdebug.v1 true schema xdebug 0...

**Parameter Complexity**：中。score=4，required=1，optional=1，真实重试=1。AI 主要风险：native batch 嵌套 request 与 MCP batch 外层 tool args 容易混淆；raw xout wrapper 也失败。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于元入口，native envelope、MCP tool、batch 嵌套 args 容易混淆。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 native batch 嵌套 request 与 MCP batch 外层 tool args 容易混淆；raw xout wrapper 也失败。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `counter.statistics`

**Action / Category / Requires / Status**：`counter.statistics` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：统计计数器行为。

**Native JSON Entry**：`tools/xdebug --json -`，action=`counter.statistics`，target keys=['session_id']，args keys=['clock', 'cnt', 'edge', 'limit', 'time_range', 'vld']。 required args=['clock', 'time_range', 'vld', 'cnt']，optional args count=4。
```json
{
  "action": "counter.statistics",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "cnt": "ai_complex_top.hs_data",
    "edge": "posedge",
    "limit": 1000,
    "time_range": {
      "begin": "100ns",
      "end": "220ns"
    },
    "vld": {
      "expr": "valid && ready",
      "signals": {
        "ready": "ai_complex_top.hs_ready",
        "valid": "ai_complex_top.hs_valid"
      }
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=counter.statistics, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.counter.statistics.v1
- summary:
- sampling_mode: clock_edge
- clock: ai_complex_top.clk
- edge: posedge
- sample_time_semantics: time is sample_time
- native key data: {"average_value": "27", "begin": "100ns", "cnt": "ai_complex_top.hs_data", "end": "220ns", "max_count": 1, "max_first_time": "195ns", "max_value": "48", "min_count": 1, "min_first_time": "135ns", "min_value": "16", "valid_false_count": 9, "vld": {"expr": "v...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_counter_statistics_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=17，required=4，optional=4，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `cursor.delete`

**Action / Category / Requires / Status**：`cursor.delete` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：删除游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`cursor.delete`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=1。
```json
{
  "action": "cursor.delete",
  "api_version": "xdebug.v1",
  "args": {
    "name": "mark_a"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=cursor.delete, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.cursor.delete.v1
- data:
- status: deleted
- name: cur0
- native key data: {"name": "mark_a", "status": "deleted"}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_cursor_delete_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `cursor.get`

**Action / Category / Requires / Status**：`cursor.get` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：读取命名游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`cursor.get`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=1。
```json
{
  "action": "cursor.get",
  "api_version": "xdebug.v1",
  "args": {
    "name": "mark_a"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=cursor.get, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.cursor.get.v1
- cursor:
- name: cur0
- time: 75ns
- origin: manual
- created_at: 1783502614
- native key data: {"cursor": {"clock": "", "created_at": 1783502448, "name": "mark_a", "note": "", "origin": "manual", "time": "75ns", "updated_at": 1783502448}}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_cursor_get_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `cursor.list`

**Action / Category / Requires / Status**：`cursor.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`cursor.list`，target keys=['session_id']，args keys=[]。 required args=[]，optional args count=1。
```json
{
  "action": "cursor.list",
  "api_version": "xdebug.v1",
  "args": {},
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=cursor.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.cursor.list.v1
- cursors:
- name time note origin clock created_at updated_at
- cur0 75ns manual 1783502615 1783502615
- active_cursor: cur0
- cursor_count: 1
- native key data: {"active_cursor": "mark_a", "cursor_count": 1, "cursors": [{"clock": "", "created_at": 1783502448, "name": "mark_a", "note": "", "origin": "manual", "time": "75ns", "updated_at": 1783502448}]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_cursor_list_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=1，required=0，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `cursor.set`

**Action / Category / Requires / Status**：`cursor.set` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：保存命名时间游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`cursor.set`，target keys=['session_id']，args keys=['name', 'time']。 required args=['name', 'time']，optional args count=1。
```json
{
  "action": "cursor.set",
  "api_version": "xdebug.v1",
  "args": {
    "name": "mark_a",
    "time": "75ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=cursor.set, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.cursor.set.v1
- cursor:
- name: cur0
- time: 75ns
- origin: manual
- created_at: 1783502613
- native key data: {"cursor": {"clock": "", "created_at": 1783502448, "name": "mark_a", "note": "", "origin": "manual", "time": "75ns", "updated_at": 1783502448}, "resolved_time": {"source": "75ns", "time": "75ns"}, "status": "set"}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_cursor_set_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=5，required=2，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `cursor.use`

**Action / Category / Requires / Status**：`cursor.use` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：激活游标。

**Native JSON Entry**：`tools/xdebug --json -`，action=`cursor.use`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=1。
```json
{
  "action": "cursor.use",
  "api_version": "xdebug.v1",
  "args": {
    "name": "mark_a"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=cursor.use, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.cursor.use.v1
- data:
- status: active
- active_cursor: cur0
- 
- cursor:
- native key data: {"active_cursor": "mark_a", "cursor": {"clock": "", "created_at": 1783502448, "name": "mark_a", "note": "", "origin": "manual", "time": "75ns", "updated_at": 1783502448}, "status": "active"}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_cursor_use_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `detect_abnormal`

**Action / Category / Requires / Status**：`detect_abnormal` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：扫描常见波形异常。

**Native JSON Entry**：`tools/xdebug --json -`，action=`detect_abnormal`，target keys=['session_id']，args keys=['checks', 'limit', 'signals', 'time_range']。 required args=['signals']，optional args count=4。
```json
{
  "action": "detect_abnormal",
  "api_version": "xdebug.v1",
  "args": {
    "checks": [
      {
        "type": "unknown_xz"
      },
      {
        "type": "glitch"
      },
      {
        "type": "stuck"
      }
    ],
    "limit": 10,
    "signals": [
      "ai_complex_top.glitch_sig",
      "ai_complex_top.stuck_sig",
      "ai_complex_top.xz_bus"
    ],
    "time_range": {
      "begin": "0ns",
      "end": "300ns"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=detect_abnormal, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.detect_abnormal.v1
- summary:
- finding_count: 3
- truncated: false
- 
- data:
- native key data: {"findings": [{"pulse_width": "0.2ns", "severity": "info", "signal": "ai_complex_top.glitch_sig", "time": "96ns", "type": "glitch"}, {"severity": "warning", "signal": "ai_complex_top.xz_bus", "time": "85ns", "type": "unknown_xz", "value": {"bits": "xxxxxxxx...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_detect_abnormal_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=12，required=1，optional=4，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `event.config.list`

**Action / Category / Requires / Status**：`event.config.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出事件配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`event.config.list`，target keys=['session_id']，args keys=['limit']。 required args=[]，optional args count=3。
```json
{
  "action": "event.config.list",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 10
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=event.config.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.event.config.list.v1
- data:
- name: evt0
- sampling_mode: clock_edge
- clock: ai_complex_top.clk
- edge: posedge
- native key data: {"count": 1, "events": ["ev0"]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_event_config_list_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=0，optional=3。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `event.config.load`

**Action / Category / Requires / Status**：`event.config.load` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：保存事件查询配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`event.config.load`，target keys=['session_id']，args keys=['config_path', 'name']。 required args=['name']，optional args count=2。
```json
{
  "action": "event.config.load",
  "api_version": "xdebug.v1",
  "args": {
    "config_path": "<xverif-repo>/xdebug/testdata/waveform/ai_complex_wave/config/event0.json",
    "name": "ev0"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=event.config.load, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.event.config.load.v1
- summary:
- name: evt0
- status: loaded
- 
- data:
- native key data: {"config": {"clock": "ai_complex_top.clk", "edge": "posedge", "fields": {"payload_lo": {"left": 3, "right": 0, "signal": "payload"}}, "name": "ev0", "rst_n": "ai_complex_top.rst_n", "sample_point": "before", "signals": {"payload": "ai_complex_top.event_payl...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_event_config_load_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=4，required=1，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `event.export`

**Action / Category / Requires / Status**：`event.export` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：导出满足表达式的事件。

**Native JSON Entry**：`tools/xdebug --json -`，action=`event.export`，target keys=['session_id']，args keys=['expr', 'limit', 'name', 'time_range']。 required args=['expr']，optional args count=13。
```json
{
  "action": "event.export",
  "api_version": "xdebug.v1",
  "args": {
    "expr": "vld && !rdy",
    "limit": 3,
    "name": "retry_evt0",
    "time_range": {
      "begin": "0ns",
      "end": "200ns"
    }
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=event.export, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.event.export.v1
- summary:
- event_count: 2
- mode: export
- inline: true
- sampling_mode: clock_edge
- native key data: {"begin": "0ns", "end": "200ns", "events": [{"fields": {"payload_lo": {"bits": "1010", "known": true, "value": "4'ha", "width": 4}}, "signals": {"payload": {"bits": "01011010", "known": true, "value": "8'h5a", "width": 8}, "rdy": {"bits": "0", "known": true...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_event_export_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=1。

**Parameter Complexity**：高。score=24，required=1，optional=13，分支 anyOf=1/oneOf=1，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `event.find`

**Action / Category / Requires / Status**：`event.find` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查找满足表达式的事件样例。

**Native JSON Entry**：`tools/xdebug --json -`，action=`event.find`，target keys=['session_id']，args keys=['clock', 'edge', 'expr', 'limit', 'signals']。 required args=['expr']，optional args count=13。
```json
{
  "action": "event.find",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "edge": "negedge",
    "expr": "valid && !ready",
    "limit": 5,
    "signals": {
      "ready": "ai_complex_top.hs_ready",
      "valid": "ai_complex_top.hs_valid"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=event.find, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.event.find.v1
- summary:
- event_count: 1
- mode: first
- inline: true
- sampling_mode: clock_edge
- native key data: {"begin": "0ns", "end": "max", "events": [{"fields": {}, "signals": {"ready": {"bits": "0", "known": true, "value": "1'h0", "width": 1}, "valid": {"bits": "1", "known": true, "value": "1'h1", "width": 1}}, "time": "150ns"}]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_event_find_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：高。score=24，required=1，optional=13，分支 anyOf=1/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `expr.eval_at`

**Action / Category / Requires / Status**：`expr.eval_at` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：在指定时间求布尔/表达式值。

**Native JSON Entry**：`tools/xdebug --json -`，action=`expr.eval_at`，target keys=['session_id']，args keys=['clock', 'expr', 'signals', 'time']。 required args=['expr', 'time', 'signals', 'clock']，optional args count=5。
```json
{
  "action": "expr.eval_at",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "expr": "valid && !ready",
    "signals": {
      "ready": "ai_complex_top.hs_ready",
      "valid": "ai_complex_top.hs_valid"
    },
    "time": "150ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=expr.eval_at, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.expr.eval_at.v1
- summary:
- expr: valid&&!ready
- time: 145ns
- status: true
- clock_edge_hit: true
- native key data: {"clock_context": {"bracket_complete": true, "clock": "ai_complex_top.clk", "clock_edge_hit": true, "clock_edge_kind": "negedge", "edge": "negedge", "next_sample_time": "160ns", "previous_sample_time": "140ns", "requested_time": "150ns", "sample_point_appli...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_expr_eval_at_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：高。score=18，required=4，optional=5，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。 与 value.at/batch/list/expr 单点采样重叠，按单信号/批量/list/表达式选择。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `expr.normalize`

**Action / Category / Requires / Status**：`expr.normalize` / `design` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：规范化表达式。

**Native JSON Entry**：`tools/xdebug --json -`，action=`expr.normalize`，target keys=['session_id']，args keys=['expr']。 required args=['expr']，optional args count=6。
```json
{
  "action": "expr.normalize",
  "api_version": "xdebug.v1",
  "args": {
    "expr": "(tx_fifo_empty == 0) && enable"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_design"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=expr.normalize, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.expr.normalize.v1
- summary:
- expr: valid && !ready
- source: string_fallback
- confidence: low
- 
- native key data: {"confidence": "low", "confidence_reason": "parsed from raw string without NPI handle", "expr": {"args": [{"args": [{"name": "(tx_fifo_empty", "type": "signal"}, {"name": "0)", "type": "signal"}], "op": "eq"}, {"name": "enable", "type": "signal"}], "op": "a...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_expr_normalize_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=8，required=1，optional=6。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：未发现明显能力冲突；主要风险来自入口字段或资源前置条件。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `handshake.inspect`

**Action / Category / Requires / Status**：`handshake.inspect` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：检查 valid/ready 握手。

**Native JSON Entry**：`tools/xdebug --json -`，action=`handshake.inspect`，target keys=['session_id']，args keys=['clock', 'data', 'ready', 'time_range', 'valid']。 required args=['clock', 'valid', 'ready']，optional args count=7。
```json
{
  "action": "handshake.inspect",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "data": [
      "ai_complex_top.hs_data"
    ],
    "ready": "ai_complex_top.hs_ready",
    "time_range": {
      "begin": "100ns",
      "end": "220ns"
    },
    "valid": "ai_complex_top.hs_valid"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=handshake.inspect, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.handshake.inspect.v1
- summary:
- sampling_mode: clock_edge
- clock: ai_complex_top.clk
- edge: negedge
- sample_time_semantics: time is sample_time
- native key data: {"data_stability_violations": 0, "findings": [], "ready_without_valid_cycles": 3}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_handshake_inspect_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：高。score=21，required=3，optional=7，分支 anyOf=0/oneOf=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.add`

**Action / Category / Requires / Status**：`list.add` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：向信号列表追加一个信号。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.add`，target keys=['session_id']，args keys=['name', 'signal']。 required args=['name', 'signal']，optional args count=1。
```json
{
  "action": "list.add",
  "api_version": "xdebug.v1",
  "args": {
    "name": "basic",
    "signal": "ai_complex_top.hs_valid"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.add, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.add.v1
- summary:
- name: basic
- signal: ai_complex_top.sig_a
- status: added
- added: true
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_add_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=5，required=2，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.create`

**Action / Category / Requires / Status**：`list.create` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：创建命名信号列表。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.create`，target keys=['session_id']，args keys=['name', 'signals']。 required args=['name']，optional args count=2。
```json
{
  "action": "list.create",
  "api_version": "xdebug.v1",
  "args": {
    "name": "basic",
    "signals": [
      "ai_complex_top.sig_a",
      "ai_complex_top.sig_b"
    ]
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.create, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.create.v1
- summary:
- name: basic
- status: created
- created: true
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_create_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=8，required=1，optional=2，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.delete`

**Action / Category / Requires / Status**：`list.delete` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：从信号列表删除信号或 index。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.delete`，target keys=['session_id']，args keys=['name', 'signal']。 required args=['name']，optional args count=3。
```json
{
  "action": "list.delete",
  "api_version": "xdebug.v1",
  "args": {
    "name": "basic",
    "signal": "ai_complex_top.hs_valid"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.delete, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.delete.v1
- summary:
- name: basic
- deleted: true
- removed: 2
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_list_delete_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=list.delete, default xout) -> xverif_debug_session_close -> unhandled exception while running action list.delete: [json.exception.type_error.302] type must be string, but is number

**Parameter Complexity**：中。score=11，required=1，optional=3，分支 anyOf=1/oneOf=1，真实重试=1。AI 主要风险：schema 允许 integer index，但 MCP evidence 显示 integer index 触发内部 type must be string；字符串 index 成功。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：需要修复。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 schema 允许 integer index，但 MCP evidence 显示 integer index 触发内部 type must be string；字符串 index 成功。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.diff`

**Action / Category / Requires / Status**：`list.diff` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查找 list 在时间窗口内的首次差异。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.diff`，target keys=['session_id']，args keys=['name', 'time_range']。 required args=['name', 'time_range']，optional args count=1。
```json
{
  "action": "list.diff",
  "api_version": "xdebug.v1",
  "args": {
    "name": "retry_basic",
    "time_range": {
      "begin": "0ns",
      "end": "120ns"
    }
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.diff, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.diff.v1
- summary:
- name: basic
- diff_found: true
- diff_time: 55ns
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_diff_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=1。

**Parameter Complexity**：中。score=6，required=2，optional=1，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.export`

**Action / Category / Requires / Status**：`list.export` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：导出 list 数据。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.export`，target keys=['session_id']，args keys=['format', 'name', 'output', 'time_range']。 required args=['name']，optional args count=5。
```json
{
  "action": "list.export",
  "api_version": "xdebug.v1",
  "args": {
    "format": "u64bin",
    "name": "retry3_basic",
    "output": {
      "path": "<repo>/tmp/xdebug_action_review_20260708/native_retry3_basic_list.u64bin"
    },
    "time_range": {
      "begin": "0ns",
      "end": "400ns"
    }
  },
  "output": {
    "verbosity": "full"
  },
  "target": {
    "session_id": "native_retry3_20260708_3637875_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.export, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.export.v1
- summary:
- name: basic
- signal_count: 2
- row_count: 6
- format: u64bin.v1
- native key data: {"begin": "0ns", "end": "400ns", "manifest_file": "<repo>/tmp/xdebug_action_review_20260708/native_retry3_basic_list.u64bin/manifest.json", "output_dir": "<repo>/tmp/xdebug_action_review_20260708/native_retry3_basic_list.u64bin", "signals": [{"columns": 3, "file": "000...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry4_list_export_target_attempt4.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=list.export, default xout) -> xverif_debug_session_close -> list.export requires at least 256ns; use list.value_at or value.batch_at for point reads
- MCP attempt2: xverif_debug_session_open -> xverif_debug_query(action=list.export, default xout) -> xverif_debug_session_close -> format must be u64bin or hex_tsv
- MCP attempt3: xverif_debug_session_open -> xverif_debug_query(action=list.export, default xout) -> xverif_debug_session_close -> instance not found in required enum

**Parameter Complexity**：高。score=9，required=1，optional=5，真实重试=6。AI 主要风险：schema/runtime drift：schema 允许 tsv/csv/hex/u64bin，runtime 实际要求 u64bin 或 hex_tsv，hex_tsv 又被 schema 拒绝。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：需要修复。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 schema/runtime drift：schema 允许 tsv/csv/hex/u64bin，runtime 实际要求 u64bin 或 hex_tsv，hex_tsv 又被 schema 拒绝。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.show`

**Action / Category / Requires / Status**：`list.show` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：显示信号列表内容。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.show`，target keys=['session_id']，args keys=['name']。 required args=[]，optional args count=2。
```json
{
  "action": "list.show",
  "api_version": "xdebug.v1",
  "args": {
    "name": "basic"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.show, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.show.v1
- summary:
- name: basic
- signal_count: 2
- 
- signals:
- native key data: {"signals": [{"index": 1, "signal": "ai_complex_top.sig_a"}, {"index": 2, "signal": "ai_complex_top.sig_b"}, {"index": 3, "signal": "ai_complex_top.hs_valid"}]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_show_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=2，required=0，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.validate`

**Action / Category / Requires / Status**：`list.validate` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：验证 list 中信号是否存在。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.validate`，target keys=['session_id']，args keys=['name']。 required args=['name']，optional args count=1。
```json
{
  "action": "list.validate",
  "api_version": "xdebug.v1",
  "args": {
    "name": "basic"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.validate, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.validate.v1
- summary:
- name: basic
- all_found: true
- 
- signals:
- native key data: {"signals": [{"signal": "ai_complex_top.sig_a", "status": "ok"}, {"signal": "ai_complex_top.sig_b", "status": "ok"}, {"signal": "ai_complex_top.hs_valid", "status": "ok"}]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_validate_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `list.value_at`

**Action / Category / Requires / Status**：`list.value_at` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：读取 list 内所有信号在指定时间的值。

**Native JSON Entry**：`tools/xdebug --json -`，action=`list.value_at`，target keys=['session_id']，args keys=['clock', 'format', 'name', 'time']。 required args=['name', 'time', 'clock']，optional args count=4。
```json
{
  "action": "list.value_at",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "format": "hex",
    "name": "basic",
    "time": "75ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=list.value_at, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.list.value_at.v1
- target:
- name: basic
- time: 75ns
- 
- values:
- native key data: {"clock_context": {"bracket_complete": true, "clock": "ai_complex_top.clk", "clock_edge_hit": true, "clock_edge_kind": "posedge", "edge": "negedge", "next_sample_time": "80ns", "previous_sample_time": "70ns", "requested_time": "75ns", "sample_point_applied"...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_list_value_at_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=10，required=3，optional=4。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。 与 value.at/batch/list/expr 单点采样重叠，按单信号/批量/list/表达式选择。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `rc.generate`

**Action / Category / Requires / Status**：`rc.generate` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：根据分组生成波形 rc。

**Native JSON Entry**：`tools/xdebug --json -`，action=`rc.generate`，target keys=['session_id']，args keys=['config_path', 'output']。 required args=['config_path', 'output']，optional args count=1。
```json
{
  "action": "rc.generate",
  "api_version": "xdebug.v1",
  "args": {
    "config_path": "<repo>/tmp/xdebug_action_review_20260708/native_rc_config.json",
    "output": {
      "path": "<repo>/tmp/xdebug_action_review_20260708/native_signal.rc"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=rc.generate, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.rc.generate.v1
- summary:
- written: true
- config_path: <repo>/tmp/xdebug_action_review_20260708/mcp_rc_config.json
- rc_path: <repo>/tmp/xdebug_action_review_20260708/mcp_generated_signal.rc
- valid: true
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_rc_generate_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=6，required=2，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：未发现明显能力冲突；主要风险来自入口字段或资源前置条件。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `sampled_pulse.inspect`

**Action / Category / Requires / Status**：`sampled_pulse.inspect` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：检查未被 clock 采到的 valid 短脉冲。

**Native JSON Entry**：`tools/xdebug --json -`，action=`sampled_pulse.inspect`，target keys=['session_id']，args keys=['clock', 'edge', 'limit', 'payload', 'time_range', 'valid']。 required args=['clock', 'valid']，optional args count=7。
```json
{
  "action": "sampled_pulse.inspect",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "edge": "posedge",
    "limit": 5,
    "payload": "ai_complex_top.hs_data",
    "time_range": {
      "begin": "0ns",
      "end": "200ns"
    },
    "valid": "ai_complex_top.glitch_sig"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=sampled_pulse.inspect, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.sampled_pulse.inspect.v1
- summary:
- sampling_mode: clock_edge
- clock: ai_complex_top.clk
- edge: negedge
- sample_time_semantics: time is sample_time
- native key data: {"_bytes": 4084, "_truncated_json": "{\"begin\": \"0ns\", \"end\": \"200ns\", \"findings\": [{\"nearest_sample_edge\": \"95ns\", \"next_sample_edge\": \"105ns\", \"previous_sample_edge\": \"95ns\", \"raw_begin\": \"96ns\", \"raw_end\": \"96.2ns\", \"raw_val...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_sampled_pulse_inspect_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=12，required=2，optional=7。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。 与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `schema`

**Action / Category / Requires / Status**：`schema` / `builtin` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：返回指定 action 的 request/response JSON schema。

**Native JSON Entry**：`tools/xdebug --json -`，action=`schema`，target keys=[]，args keys=['action', 'kind']。 required args=[]，optional args count=2。
```json
{
  "action": "schema",
  "api_version": "xdebug.v1",
  "args": {
    "action": "value.at",
    "kind": "response"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=schema, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.schema.v1
- summary:
- action: signal.statistics
- kind: request
- 
- schema:
- native key data: {"schema": {"$id": "xdebug.value.at.response.v1", "$schema": "https://json-schema.org/draft/2020-12/schema", "additionalProperties": true, "description": "value.at response: 读取单个信号在指定时间的值。", "properties": {"action": {"enum": ["value.at"], "type": "string"},...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_schema_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=schema, output_format=xout) -> @xdebug.schema.v1 summary: action: signal.statistics kind: request schema: _schema: https://json-schema.org/draft/2020-12/schema _id: xdebug.signal.statistics.request.v1 title: ...

**Parameter Complexity**：中。score=2，required=0，optional=2，真实重试=1。AI 主要风险：raw_request xout 会触发 MCP wrapper JSON 解析错误；schema 内容可读但 wrapper 状态为失败。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于元入口，native envelope、MCP tool、batch 嵌套 args 容易混淆。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 raw_request xout 会触发 MCP wrapper JSON 解析错误；schema 内容可读但 wrapper 状态为失败。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `scope.list`

**Action / Category / Requires / Status**：`scope.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出 FSDB scope 或信号。

**Native JSON Entry**：`tools/xdebug --json -`，action=`scope.list`，target keys=['session_id']，args keys=['max_depth', 'path', 'recursive']。 required args=[]，optional args count=4。
```json
{
  "action": "scope.list",
  "api_version": "xdebug.v1",
  "args": {
    "max_depth": 1,
    "path": "ai_complex_top",
    "recursive": false
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=scope.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.scope.list.v1
- summary:
- path: ai_complex_top
- recursive: true
- returned_signal_count: 23
- total_signal_count: 23
- native key data: {"scopes": [], "signals": ["ai_complex_top.clk", "ai_complex_top.rst_n", "ai_complex_top.sig_a", "ai_complex_top.sig_b", "ai_complex_top.xz_bus", "ai_complex_top.stable_sig", "ai_complex_top.stuck_sig", "ai_complex_top.glitch_sig", "ai_complex_top.counter_i...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_scope_list_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=1。

**Parameter Complexity**：中。score=4，required=0，optional=4，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：未发现明显能力冲突；主要风险来自入口字段或资源前置条件。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `scope.roots`

**Action / Category / Requires / Status**：`scope.roots` / `waveform` / `any` / Native=pass; Schema=pass; MCP=pass。

**Capability**：发现 waveform/design 根。

**Native JSON Entry**：`tools/xdebug --json -`，action=`scope.roots`，target keys=['session_id']，args keys=['source']。 required args=[]，optional args count=2。
```json
{
  "action": "scope.roots",
  "api_version": "xdebug.v1",
  "args": {
    "source": "auto"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=scope.roots, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.scope.roots.v1
- summary:
- recommended: ai_complex_top
- source: auto
- roots: 1
- matched: 0
- native key data: {"design_roots": [], "limitations": ["design roots unavailable: design not loaded"], "roots": [{"design": null, "path": "ai_complex_top", "sources": ["wave"], "status": "wave_only", "wave": {"def_name": "ai_complex_top", "full_name": "ai_complex_top", "name...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_scope_roots_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=2，required=0，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：未发现明显能力冲突；主要风险来自入口字段或资源前置条件。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.close`

**Action / Category / Requires / Status**：`session.close` / `session` / `session` / Native=pass; Schema=pass; MCP=pass。

**Capability**：关闭指定 session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.close`，target keys=['session_id']，args keys=['session_id']。 required args=[]，optional args count=1。
```json
{
  "action": "session.close",
  "api_version": "xdebug.v1",
  "args": {
    "session_id": "native_review_20260708_3613710_session_actions"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_session_actions"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=session.close, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.session.close.v1
- summary:
- session_id: mcp_retry_session_actions_20260708
- mode: waveform
- removed: true
- 
- native key data: {"backends": {"action": "session.kill", "api_version": "xdebug.v1", "data": {}, "error": null, "ok": true, "request_id": "", "session": null, "summary": {"id": "native_review_20260708_3613710_session_actions", "killed": true, "session_id": "native_review_20...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_session_close_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.close, output_format=xout) -> @xdebug.session.close.v1 summary: session_id: mcp_raw_session_open_20260708 mode: waveform removed: true session: id: mcp_raw_session_open_20260708 session_id: mcp_raw_session_o...

**Parameter Complexity**：中。score=1，required=0，optional=1，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.doctor`

**Action / Category / Requires / Status**：`session.doctor` / `session` / `session` / Native=pass; Schema=pass; MCP=pass。

**Capability**：诊断当前 session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.doctor`，target keys=['session_id']，args keys=[]。 required args=[]，optional args count=0。
```json
{
  "action": "session.doctor",
  "api_version": "xdebug.v1",
  "args": {},
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_session_actions"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=session.doctor, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.session.doctor.v1
- summary:
- session_id: mcp_retry_session_actions_20260708
- mode: waveform
- healthy: true
- 
- native key data: {"health": {"action": "session.doctor", "api_version": "xdebug.v1", "data": {"health": {"healthy": true, "id": "native_review_20260708_3613710_session_actions", "message": "Session is healthy", "session_id": "native_review_20260708_3613710_session_actions",...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_session_doctor_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.doctor, output_format=xout) -> @xdebug.session.doctor.v1 summary: session_id: mcp_raw_session_open_20260708 mode: waveform healthy: true health: api_version: xdebug.v1 ok: true action: session.doctor tool: na...

**Parameter Complexity**：中。score=0，required=0，optional=0，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.gc`

**Action / Category / Requires / Status**：`session.gc` / `session` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：清理过期 session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.gc`，target keys=[]，args keys=[]。 required args=[]，optional args count=0。
```json
{
  "action": "session.gc",
  "api_version": "xdebug.v1",
  "args": {},
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=session.gc, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.session.gc.v1
- summary:
- status: completed
- before_count: 5
- kept_count: 2
- removed_count: 3
- native key data: {"_bytes": 22186, "_truncated_json": "{\"before\": [{\"created_at\": 1783442525, \"file_dir\": \"~/.xdebug/engine/sessions/smoke2_bbea1df62ed711e2/transport\", \"fsdb\": \"<design-repo>/dv/run/out/sanity/test/bsg_cache_nb_smoke_tc_1/waves.fs...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_session_gc_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.gc, output_format=xout) -> @xdebug.session.gc.v1 summary: status: completed before_count: 0 kept_count: 0 removed_count: 0 data: before: [empty] kept: [empty] removed: [empty]

**Parameter Complexity**：中。score=0，required=0，optional=0，真实重试=1。AI 主要风险：有全局清理副作用；本轮曾清理非本轮 unhealthy native session，不能当纯只读 action。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 有全局清理副作用；本轮曾清理非本轮 unhealthy native session，不能当纯只读 action。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.kill`

**Action / Category / Requires / Status**：`session.kill` / `session` / `session` / Native=pass; Schema=pass; MCP=pass。

**Capability**：强制移除指定 session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.kill`，target keys=['session_id']，args keys=['session_id']。 required args=[]，optional args count=1。
```json
{
  "action": "session.kill",
  "api_version": "xdebug.v1",
  "args": {
    "session_id": "native_review_20260708_3613710_session_kill"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_session_kill"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=session.kill, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.session.kill.v1
- summary:
- session_id: mcp_retry_session_kill_20260708
- mode: waveform
- removed: true
- 
- native key data: {"backends": {"action": "session.kill", "api_version": "xdebug.v1", "data": {}, "error": null, "ok": true, "request_id": "", "session": null, "summary": {"id": "native_review_20260708_3613710_session_kill", "killed": true, "session_id": "native_review_20260...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_session_kill_query_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.kill, output_format=xout) -> @xdebug.session.kill.v1 summary: session_id: mcp_raw_session_kill_20260708 mode: waveform removed: true session: id: mcp_raw_session_kill_20260708 session_id: mcp_raw_session_ki...

**Parameter Complexity**：中。score=1，required=0，optional=1，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.list`

**Action / Category / Requires / Status**：`session.list` / `session` / `session` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出当前 session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.list`，target keys=[]，args keys=[]。 required args=[]，optional args count=0。
```json
{
  "action": "session.list",
  "api_version": "xdebug.v1",
  "args": {},
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=session.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.session.list.v1
- summary:
- session_count: 1
- expired_removed_count: 0
- 
- sessions:
- native key data: {"_bytes": 11175, "_truncated_json": "{\"sessions\": [{\"created_at\": 1783442525, \"file_dir\": \"~/.xdebug/engine/sessions/smoke2_bbea1df62ed711e2/transport\", \"fsdb\": \"<design-repo>/dv/run/out/sanity/test/bsg_cache_nb_smoke_tc_1/waves....
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry_session_list_query_attempt3.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.list, output_format=xout) -> @xdebug.session.list.v1 summary: session_count: 1 expired_removed_count: 0 sessions: id session_id mode fsdb socket_path

**Parameter Complexity**：中。score=0，required=0，optional=0，真实重试=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `session.open`

**Action / Category / Requires / Status**：`session.open` / `session` / `any` / Native=pass; Schema=pass; MCP=wrapper_blocker。

**Capability**：打开 design/waveform session。

**Native JSON Entry**：`tools/xdebug --json -`，action=`session.open`，target keys=['fsdb']，args keys=['name']。 required args=['name']，optional args count=6。
```json
{
  "action": "session.open",
  "api_version": "xdebug.v1",
  "args": {
    "name": "native_review_20260708_3613710_open_action"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "fsdb": "<xverif-repo>/xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb"
  }
}
```

**MCP Entry**：xverif_debug_raw_request(request.action=session.open, output_format=xout)

**Execution Evidence**：
- @xdebug.session.open.v1
- summary:
- session_id: mcp_raw_session_kill_20260708
- mode: waveform
- 
- session:
- native key data: {"session": {"file_dir": "~/.xdebug/engine/sessions/native_review_20_0aec419b5632383d/transport", "fsdb": "<xverif-repo>/xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb", "id": "native_review_20260708_3613710_open_action", "mode": "waveform", "server_hos...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_session_open_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_raw_request(request.action=session.open, output_format=xout) -> @xdebug.session.open.v1 summary: session_id: mcp_raw_session_open_20260708 mode: waveform session: id: mcp_raw_session_open_20260708 session_id: mcp_raw_session_open_20260708 mo...
- MCP attempt2: xverif_debug_raw_request(request.action=session.open, output_format=xout) -> @xdebug.session.open.v1 summary: session_id: mcp_raw_session_kill_20260708 mode: waveform session: id: mcp_raw_session_kill_20260708 session_id: mcp_raw_session_kill_20260708 mo...

**Parameter Complexity**：中。score=8，required=1，optional=6，真实重试=2。AI 主要风险：MCP raw xout wrapper blocker：backend 输出 @xdebug.session.open.v1，但 tool 返回 XVERIF_BAD_JSON_RESPONSE。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：需要修复。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 MCP raw xout wrapper blocker：backend 输出 @xdebug.session.open.v1，但 tool 返回 XVERIF_BAD_JSON_RESPONSE。 强调 native target.session_id 与 MCP 外层 session_id 的边界。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `signal.canonicalize`

**Action / Category / Requires / Status**：`signal.canonicalize` / `design` / `design` / Native=pass; Schema=pass; MCP=pass。

**Capability**：返回信号 canonical 名称。

**Native JSON Entry**：`tools/xdebug --json -`，action=`signal.canonicalize`，target keys=['session_id']，args keys=['signal']。 required args=['signal']，optional args count=1。
```json
{
  "action": "signal.canonicalize",
  "api_version": "xdebug.v1",
  "args": {
    "signal": "uart_16550.tx_fifo_empty"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_design"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=signal.canonicalize, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.signal.canonicalize.v1
- summary:
- query: uart_16550.RXDin
- ambiguous: false
- 
- data:
- native key data: {"aliases": [], "ambiguous": false, "base_signal": null, "canonical": "uart_16550.tx_fifo_empty", "fsdb_candidates": [], "leaf": null, "port_mappings": [], "query": "uart_16550.tx_fifo_empty", "rtl_path": null, "scope": null, "select": null}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_signal_canonicalize_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `signal.changes`

**Action / Category / Requires / Status**：`signal.changes` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：读取信号变化点。

**Native JSON Entry**：`tools/xdebug --json -`，action=`signal.changes`，target keys=['session_id']，args keys=['limit', 'signal', 'time_range']。 required args=['signal']，optional args count=5。
```json
{
  "action": "signal.changes",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 4,
    "signal": "ai_complex_top.sig_a",
    "time_range": {
      "begin": "0ns",
      "end": "120ns"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=signal.changes, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.signal.changes.v1
- summary:
- signal: ai_complex_top.sig_a
- returned_change_rows: 3
- actual_transition_count: 2
- truncated: false
- native key data: {"begin": "0ns", "end": "120ns", "final_value": {"bits": "00100010", "known": true, "value": "8'h22", "width": 8}, "first_change": "0ns", "includes_initial_value": true, "initial_value": {"bits": "00000000", "known": true, "value": "8'h00", "width": 8}, "la...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_signal_changes_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=8，required=1，optional=5。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。 与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `signal.resolve`

**Action / Category / Requires / Status**：`signal.resolve` / `design` / `design` / Native=pass; Schema=pass; MCP=pass。

**Capability**：解析设计信号。

**Native JSON Entry**：`tools/xdebug --json -`，action=`signal.resolve`，target keys=['session_id']，args keys=['signal']。 required args=['signal']，optional args count=1。
```json
{
  "action": "signal.resolve",
  "api_version": "xdebug.v1",
  "args": {
    "signal": "uart_16550.tx_fifo_empty"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_design"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=signal.resolve, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.signal.resolve.v1
- summary:
- count: 1
- ok: true
- query: uart_16550.RXDin
- status: ok
- native key data: {"count": 1, "matches": [{"file": "<xverif-repo>/xdebug/testdata/design/uart/uart_16550.sv", "line": 65, "signal": "uart_16550.tx_fifo_empty", "type": "net"}], "message": "", "ok": true, "query": "uart_16550.tx_fifo_empty", "status": "ok"}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_signal_resolve_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `signal.stability`

**Action / Category / Requires / Status**：`signal.stability` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：检查信号窗口内是否稳定。

**Native JSON Entry**：`tools/xdebug --json -`，action=`signal.stability`，target keys=['session_id']，args keys=['signal', 'time_range']。 required args=['signal']，optional args count=6。
```json
{
  "action": "signal.stability",
  "api_version": "xdebug.v1",
  "args": {
    "signal": "ai_complex_top.stable_sig",
    "time_range": {
      "begin": "0ns",
      "end": "400ns"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=signal.stability, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.signal.stability.v1
- data:
- signal: ai_complex_top.stable_sig
- begin: 0ns
- end: 400ns
- 
- native key data: {"begin": "0ns", "changes": [{"time": "0ns", "value": {"bits": "1", "known": true, "value": "1'h1", "width": 1}}], "end": "400ns", "final_value": {"bits": "1", "known": true, "value": "1'h1", "width": 1}, "first_change": "0ns", "initial_value": {"bits": "1"...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_signal_stability_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=14，required=1，optional=6，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `signal.statistics`

**Action / Category / Requires / Status**：`signal.statistics` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：统计信号活动。

**Native JSON Entry**：`tools/xdebug --json -`，action=`signal.statistics`，target keys=['session_id']，args keys=['clock', 'limit', 'signal', 'time_range']。 required args=['signal']，optional args count=9。
```json
{
  "action": "signal.statistics",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "limit": 1000,
    "signal": "ai_complex_top.hs_valid",
    "time_range": {
      "begin": "120ns",
      "end": "210ns"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=signal.statistics, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.signal.statistics.v1
- summary:
- sampling_mode: clock_edge
- clock: ai_complex_top.clk
- edge: negedge
- sample_time_semantics: time is sample_time
- native key data: {"activity": {"first_high_time": "130ns", "high_burst_count": 1, "last_fall_time": "200ns", "last_high_time": "190ns", "max_high_cycles": 7}, "begin": "120ns", "end": "210ns", "final": {"known": true, "value": "'b0", "width": 1}, "first": {"known": true, "v...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_signal_statistics_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=17，required=1，optional=9，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。 与 signal changes/statistics/stability/counter/detect 重叠，raw timeline 与 sampled statistics 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `source.context`

**Action / Category / Requires / Status**：`source.context` / `design` / `none` / Native=pass; Schema=pass; MCP=pass。

**Capability**：读取源码上下文。

**Native JSON Entry**：`tools/xdebug --json -`，action=`source.context`，target keys=[]，args keys=['context_lines', 'file', 'line']。 required args=['file', 'line']，optional args count=3。
```json
{
  "action": "source.context",
  "api_version": "xdebug.v1",
  "args": {
    "context_lines": 3,
    "file": "<xverif-repo>/xdebug/testdata/design/uart/uart_tx.sv",
    "line": 70
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=source.context, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.source.context.v1
- summary:
- file: <xverif-repo>/xdebug/testdata/design/uart/uart_16550.sv
- line: 164
- 
- data:
- native key data: {"context_kind": "if", "enclosing": {"begin_line": 70, "end_line": 76, "name": "", "type": "if"}, "symbol": ""}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_source_context_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=7，required=2，optional=3。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.config.list`

**Action / Category / Requires / Status**：`stream.config.list` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：列出 stream 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.config.list`，target keys=['session_id']，args keys=[]。 required args=[]，optional args count=2。
```json
{
  "action": "stream.config.list",
  "api_version": "xdebug.v1",
  "args": {},
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.config.list, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.config.list.v1
- summary:
- count: 7
- 
- streams:
- name sampling_mode clock edge handshake packet field_count channel_id_valid allow_interleaving sample_point
- native key data: {"streams": [{"allow_interleaving": false, "channel_id_valid": "every_beat", "clock": "stream_v1_top.clk", "edge": "posedge", "field_count": 3, "handshake": "vld/bp", "name": "bp_packet", "packet": "sop/eop", "sample_point": "before", "sampling_mode": "cloc...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_stream_config_list_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=2，required=0，optional=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.config.load`

**Action / Category / Requires / Status**：`stream.config.load` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：加载 stream 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.config.load`，target keys=['session_id']，args keys=['config_path', 'mode']。 required args=[]，optional args count=6。
```json
{
  "action": "stream.config.load",
  "api_version": "xdebug.v1",
  "args": {
    "config_path": "<xverif-repo>/xdebug/testdata/waveform/stream_v1/config/streams.json",
    "mode": "replace"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.config.load, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.config.load.v1
- summary:
- loaded: 7
- mode: replace
- 
- streams:
- native key data: {"issues": [{"code": "CLOCK_COMPLEX", "message": "clock expression is not a plain signal; edge detection uses expression dependency changes", "severity": "WARNING", "stream": "valid_only"}], "streams": ["valid_only", "ready_stream", "bp_stream", "ready_pack...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_stream_config_load_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=10，required=0，optional=6，分支 anyOf=1/oneOf=0。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 属于 session/list/cursor/config 状态边界，name/session_id/list/config 容易放错层级。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.export`

**Action / Category / Requires / Status**：`stream.export` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：导出 stream 查询结果。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.export`，target keys=['session_id']，args keys=['format', 'kind', 'output', 'stream', 'time_range']。 required args=['stream']，optional args count=7。
```json
{
  "action": "stream.export",
  "api_version": "xdebug.v1",
  "args": {
    "format": "tsv",
    "kind": "transfer",
    "output": {
      "path": "<repo>/tmp/xdebug_action_review_20260708/native_ready_stream.tsv"
    },
    "stream": "ready_stream",
    "time_range": {
      "begin": "0ns",
      "end": "250us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.export, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.export.v1
- summary:
- stream: ready_stream
- sampling_mode: clock_edge
- clock: stream_v1_top.clk
- edge: posedge
- native key data: {"format": "tsv", "kind": "transfer", "meta_file": "<repo>/tmp/xdebug_action_review_20260708/native_ready_stream.tsv.meta.json", "output_file": "<repo>/tmp/xdebug_action_review_20260708/native_ready_stream.tsv", "row_count": 15059}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_stream_export_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=stream.export, default xout) -> xverif_debug_session_close -> kind must be transfer, packet, or packet_beats

**Parameter Complexity**：中。score=13，required=1，optional=7，真实重试=1。AI 主要风险：kind=beats 被 runtime 拒绝，实际允许 transfer/packet/packet_beats。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 kind=beats 被 runtime 拒绝，实际允许 transfer/packet/packet_beats。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.query`

**Action / Category / Requires / Status**：`stream.query` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查询 stream transfer。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.query`，target keys=['session_id']，args keys=['limit', 'match', 'query', 'stream', 'time_range']。 required args=['stream', 'query']，optional args count=7。
```json
{
  "action": "stream.query",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 8,
    "match": {
      "field": "low8",
      "op": "==",
      "value": "8'h5a"
    },
    "query": "match_field",
    "stream": "ready_stream",
    "time_range": {
      "begin": "0ns",
      "end": "250us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.query, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.query.v1
- summary:
- stream: ready_stream
- sampling_mode: clock_edge
- clock: stream_v1_top.clk
- edge: posedge
- native key data: {"_bytes": 4850, "_truncated_json": "{\"hint\": \"use stream.export for large result\", \"query\": \"match_field\", \"rows\": [{\"beat_index\": 0, \"bp\": false, \"channel_id\": {\"bits\": \"10\", \"known\": true, \"value\": \"2'h2\", \"width\": 2}, \"cycle...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_stream_query_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=17，required=2，optional=7，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.show`

**Action / Category / Requires / Status**：`stream.show` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：显示 stream 定义和摘要。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.show`，target keys=['session_id']，args keys=['stream']。 required args=['stream']，optional args count=1。
```json
{
  "action": "stream.show",
  "api_version": "xdebug.v1",
  "args": {
    "stream": "ready_stream"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.show, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.show.v1
- summary:
- stream: ready_stream
- handshake: vld/rdy
- packet_enabled: false
- 
- native key data: {"config": {"allow_interleaving": false, "channel_id": "stream_v1_top.ready_chid", "channel_id_valid": "every_beat", "clock": "stream_v1_top.clk", "data_fields": {"addr": "{stream_v1_top.ready_addr_hi, stream_v1_top.ready_addr_lo}", "data": "stream_v1_top.r...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_stream_show_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=3，required=1，optional=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `stream.validate`

**Action / Category / Requires / Status**：`stream.validate` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：验证 stream 配置。

**Native JSON Entry**：`tools/xdebug --json -`，action=`stream.validate`，target keys=['session_id']，args keys=['limit', 'stream', 'time_range']。 required args=['stream']，optional args count=6。
```json
{
  "action": "stream.validate",
  "api_version": "xdebug.v1",
  "args": {
    "limit": 512,
    "stream": "ready_stream",
    "time_range": {
      "begin": "0ns",
      "end": "250us"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_stream"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=stream.validate, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.stream.validate.v1
- summary:
- stream: ready_stream
- ok: true
- 
- data:
- native key data: {"dynamic": {"clock": "stream_v1_top.clk", "clock_edges": 20011, "control_xz_count": 0, "data_xz_count": 0, "edge": "posedge", "first_stall": {"cycles": 1, "end_cycle": 12, "end_time": "125ns", "reason": "rdy_low", "start_cycle": 11, "start_time": "115ns"},...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_stream_validate_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=9，required=1，optional=6。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 AXI/APB 专用和 stream 通用抽取重叠，标准总线优先专用，内部 vld-data 优先 stream。 与 handshake/stream/sampled pulse 重叠，协议统计、流抽取、missed sampling 要分开。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 返回中继续保留 name、time_range、direction/query 和 truncated 字段，便于二次缩小窗口。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `trace.active_driver`

**Action / Category / Requires / Status**：`trace.active_driver` / `combined` / `combined` / Native=pass; Schema=pass; MCP=pass。

**Capability**：在指定时间找 active driver。

**Native JSON Entry**：`tools/xdebug --json -`，action=`trace.active_driver`，target keys=['session_id']，args keys=['include_trace', 'signal', 'time']。 required args=['signal', 'time']，optional args count=7。
```json
{
  "action": "trace.active_driver",
  "api_version": "xdebug.v1",
  "args": {
    "include_trace": true,
    "signal": "active_driver_tb.u_dut.q",
    "time": "26ns"
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_combined"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=trace.active_driver, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.trace.active_driver.v1
- summary:
- signal: active_driver_tb.q
- requested_time: 50ns
- active_time: 45ns
- path_count: 5
- native key data: {"paths": [{"file": "<xverif-repo>/xdebug/testdata/combined/active_driver/active_driver_tb.sv", "line": 20, "signal_path": ["active_driver_tb.u_dut.data_b", "active_driver_tb.u_dut.q"], "source_context": [{"active": false, "line": 17, "text": " else if (sel)"}, ...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_trace_active_driver_target_attempt1.xout`

**Retry / Failure Record**：
有重试计数但未展开失败明细：MCP=0，native=2。

**Parameter Complexity**：中。score=12，required=2，optional=7，真实重试=2。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `trace.active_driver_chain`

**Action / Category / Requires / Status**：`trace.active_driver_chain` / `combined` / `combined` / Native=pass; Schema=pass; MCP=pass。

**Capability**：展开 active driver 链。

**Native JSON Entry**：`tools/xdebug --json -`，action=`trace.active_driver_chain`，target keys=['session_id']，args keys=['clk_period', 'signal', 'time']。 required args=['signal', 'time']，optional args count=3。
```json
{
  "action": "trace.active_driver_chain",
  "api_version": "xdebug.v1",
  "args": {
    "clk_period": "10ns",
    "signal": "active_driver_tb.u_dut.q",
    "time": "26ns"
  },
  "output": {
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_retry_20260708_3624728_combined"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=trace.active_driver_chain, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.trace.active_driver_chain.v1
- summary:
- signal: active_driver_tb.q
- start_time: 50ns
- hop_count: 3
- termination: primary_input
- native key data: {"hops": [{"file": "<xverif-repo>/xdebug/testdata/combined/active_driver/active_driver_tb.sv", "index": 0, "line": 20, "signal_path": ["active_driver_tb.u_dut.data_b", "active_driver_tb.u_dut.q"], "source_context": [{"active": false, "line": 17, "text": " else i...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_retry2_trace_active_driver_chain_target_attempt2.xout`

**Retry / Failure Record**：
- MCP attempt1: xverif_debug_session_open -> xverif_debug_query(action=trace.active_driver_chain, default xout) -> xverif_debug_sessi... -> validation failed for additional property 'depth': instance invalid as per false-schema

**Parameter Complexity**：高。score=8，required=2，optional=3，真实重试=3。AI 主要风险：args.depth 被 schema 拒绝；深度应放 limits.max_depth。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用但高迷惑风险。

**Recommendations**：补 action-specific 最小模板和反例，并在错误提示中指出正确字段位置。 args.depth 被 schema 拒绝；深度应放 limits.max_depth。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `trace.driver`

**Action / Category / Requires / Status**：`trace.driver` / `design` / `design` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查找信号直接 driver。

**Native JSON Entry**：`tools/xdebug --json -`，action=`trace.driver`，target keys=['session_id']，args keys=['include_trace', 'signal']。 required args=['signal']，optional args count=6。
```json
{
  "action": "trace.driver",
  "api_version": "xdebug.v1",
  "args": {
    "include_trace": false,
    "signal": "uart_16550.tx_fifo_empty"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_design"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=trace.driver, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.trace.driver.v1
- summary:
- signal: uart_16550.RXDin
- mode: driver
- path_count: 3
- truncated: false
- native key data: {"paths": [{"file": "<xverif-repo>/xdebug/testdata/design/uart/uart_tx.sv", "line": 30, "signal_path": ["uart_16550.tx_channel.tx_fifo_empty", "uart_16550.tx_fifo_empty"], "source_context": [{"active": false, "line": 27, "text": " input tx_fifo_push,"}, {"active...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_trace_driver_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=8，required=1，optional=6。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `trace.load`

**Action / Category / Requires / Status**：`trace.load` / `design` / `design` / Native=pass; Schema=pass; MCP=pass。

**Capability**：查找信号 load。

**Native JSON Entry**：`tools/xdebug --json -`，action=`trace.load`，target keys=['session_id']，args keys=['include_trace', 'signal']。 required args=['signal']，optional args count=6。
```json
{
  "action": "trace.load",
  "api_version": "xdebug.v1",
  "args": {
    "include_trace": false,
    "signal": "uart_16550.tx_fifo_empty"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_design"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=trace.load, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.trace.load.v1
- summary:
- signal: uart_16550.RXDin
- mode: load
- path_count: 5
- truncated: false
- native key data: {"_bytes": 7639, "_truncated_json": "{\"paths\": [{\"file\": \"<xverif-repo>/xdebug/testdata/design/uart/uart_register_file.sv\", \"line\": 323, \"signal_path\": [\"uart_16550.control.LSR\", \"uart_16550.tx_fifo_empty\"], \"source_context\": [{\"active\": false,...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_trace_load_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：低。score=8，required=1，optional=6。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 design trace/combined active driver 重叠，无时间点用静态 trace，有波形时间点用 active driver。

**Verdict**：可用。

**Recommendations**：保持当前入口，文档只需保留最小示例。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `value.at`

**Action / Category / Requires / Status**：`value.at` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：读取单个信号在指定时间的值。

**Native JSON Entry**：`tools/xdebug --json -`，action=`value.at`，target keys=['session_id']，args keys=['clock', 'format', 'signal', 'time']。 required args=['signal', 'time', 'clock']，optional args count=5。
```json
{
  "action": "value.at",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "format": "hex",
    "signal": "ai_complex_top.sig_a",
    "time": "75ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=value.at, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.value.at.v1
- target:
- signal: ai_complex_top.sig_a
- time: 75ns
- clock: ai_complex_top.clk
- edge: negedge
- native key data: {"clock_context": {"bracket_complete": true, "clock": "ai_complex_top.clk", "clock_edge_hit": true, "clock_edge_kind": "posedge", "edge": "negedge", "next_sample_time": "80ns", "previous_sample_time": "70ns", "requested_time": "75ns", "sample_point_applied"...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_value_at_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=12，required=3，optional=5。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 value.at/batch/list/expr 单点采样重叠，按单信号/批量/list/表达式选择。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `value.batch_at`

**Action / Category / Requires / Status**：`value.batch_at` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：批量读取多个信号值。

**Native JSON Entry**：`tools/xdebug --json -`，action=`value.batch_at`，target keys=['session_id']，args keys=['clock', 'format', 'signals', 'time']。 required args=['signals', 'time', 'clock']，optional args count=5。
```json
{
  "action": "value.batch_at",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "format": "hex",
    "signals": [
      "ai_complex_top.sig_a",
      "ai_complex_top.sig_b"
    ],
    "time": "75ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=value.batch_at, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.value.batch_at.v1
- target:
- time: 95ns
- signal_count: 2
- 
- values:
- native key data: {"clock_context": {"bracket_complete": true, "clock": "ai_complex_top.clk", "clock_edge_hit": true, "clock_edge_kind": "posedge", "edge": "negedge", "next_sample_time": "80ns", "previous_sample_time": "70ns", "requested_time": "75ns", "sample_point_applied"...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_value_batch_at_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=16，required=3，optional=5，分支 anyOf=0/oneOf=1。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 value.at/batch/list/expr 单点采样重叠，按单信号/批量/list/表达式选择。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `verify.conditions`

**Action / Category / Requires / Status**：`verify.conditions` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：在单个时间验证条件集合。

**Native JSON Entry**：`tools/xdebug --json -`，action=`verify.conditions`，target keys=['session_id']，args keys=['clock', 'conditions', 'time']。 required args=['conditions', 'time', 'clock']，optional args count=3。
```json
{
  "action": "verify.conditions",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "conditions": [
      {
        "op": "==",
        "signal": "ai_complex_top.sig_a",
        "value": "'h22"
      },
      {
        "op": "==",
        "signal": "ai_complex_top.sig_b",
        "value": "'h22"
      }
    ],
    "time": "75ns"
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=verify.conditions, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.verify.conditions.v1
- summary:
- time: 95ns
- verdict: fail
- condition_count: 3
- all_passed: false
- native key data: {"checks": [{"expected": "'h22", "known": true, "observed": {"known": true, "value": "'h22"}, "op": "==", "pass": true, "samples": {"after": {"status": "ok", "value": {"known": true, "value": "'h22"}}, "before": {"status": "ok", "value": {"known": true, "va...
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_verify_conditions_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=10，required=3，optional=3。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：中。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## Action: `window.verify`

**Action / Category / Requires / Status**：`window.verify` / `waveform` / `waveform` / Native=pass; Schema=pass; MCP=pass。

**Capability**：按 clock 在窗口内验证条件。

**Native JSON Entry**：`tools/xdebug --json -`，action=`window.verify`，target keys=['session_id']，args keys=['clock', 'conditions', 'time_range']。 required args=['clock', 'conditions']，optional args count=5。
```json
{
  "action": "window.verify",
  "api_version": "xdebug.v1",
  "args": {
    "clock": "ai_complex_top.clk",
    "conditions": [
      {
        "expr": "valid && !ready",
        "mode": "eventually",
        "signals": {
          "ready": "ai_complex_top.hs_ready",
          "valid": "ai_complex_top.hs_valid"
        }
      }
    ],
    "time_range": {
      "begin": "120ns",
      "end": "210ns"
    }
  },
  "output": {
    "pretty": false,
    "verbosity": "compact"
  },
  "target": {
    "session_id": "native_review_20260708_3613710_generic"
  }
}
```

**MCP Entry**：xverif_debug_session_open -> xverif_debug_query(action=window.verify, default xout) -> xverif_debug_session_close

**Execution Evidence**：
- @xdebug.window.verify.v1
- summary:
- all_passed: true
- sample_count: 4
- failed_samples: 0
- unknown_samples: 0
- native key data: {"conditions": [{"expr": "valid&&!ready", "failed_samples": 3, "mode": "eventually", "pass_samples": 1, "passed": true, "unknown_samples": 0}]}
- MCP evidence file: `<repo>/tmp/xdebug_action_review_20260708/mcp_window_verify_target_attempt1.xout`

**Retry / Failure Record**：
无失败重试记录；首次或既有矩阵请求成功。

**Parameter Complexity**：中。score=11，required=2，optional=5。AI 主要风险：按 action-specific schema 生成请求即可；避免把其它 action 的同名字段迁入。

**Response Debug Value**：高。response schema 对业务字段约束偏弱，读者仍需看 summary/data/xout 具体字段。

**Conflict / Overlap**：与 event/window/expr/value 条件查询重叠，需按找点、证明、单点求值区分。

**Verdict**：可用。

**Recommendations**：补充稳定 xout 示例，突出 required 字段和常见错误字段。 后续可收紧 response schema 的 summary/data 字段，减少脚本和 AI 对文本格式的依赖。

## 附录：执行矩阵摘要

| action | native | schema | mcp | mcp retries | complexity | overlap |
| --- | --- | --- | --- | ---: | --- | --- |
| `actions` | pass | pass | pass | 1 | 中 | meta_dispatch |
| `apb.config.list` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream,stateful_registry_boundary |
| `apb.config.load` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream,stateful_registry_boundary |
| `apb.cursor` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream |
| `apb.query` | pass | pass | pass | 1 | 中 | protocol_vs_generic_stream |
| `apb.transfer_window` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream |
| `axi.analysis` | pass | pass | pass | 1 | 中 | protocol_vs_generic_stream |
| `axi.channel_stall` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream |
| `axi.config.list` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream,stateful_registry_boundary |
| `axi.config.load` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream,stateful_registry_boundary |
| `axi.cursor` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream |
| `axi.export` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream |
| `axi.latency_outlier` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream |
| `axi.outstanding_timeline` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream |
| `axi.query` | pass | pass | pass | 1 | 高 | protocol_vs_generic_stream |
| `axi.request_response_pair` | pass | pass | pass | 2 | 高 | protocol_vs_generic_stream |
| `batch` | pass | pass | pass | 1 | 中 | meta_dispatch |
| `counter.statistics` | pass | pass | pass | 0 | 中 | signal_time_series |
| `cursor.delete` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `cursor.get` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `cursor.list` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `cursor.set` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `cursor.use` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `detect_abnormal` | pass | pass | pass | 0 | 中 | signal_time_series |
| `event.config.list` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `event.config.load` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `event.export` | pass | pass | pass | 0 | 高 | condition_window_event |
| `event.find` | pass | pass | pass | 0 | 高 | condition_window_event |
| `expr.eval_at` | pass | pass | pass | 0 | 高 | condition_window_event,value_sampling |
| `expr.normalize` | pass | pass | pass | 0 | 低 |  |
| `handshake.inspect` | pass | pass | pass | 0 | 高 | valid_ready_stream |
| `list.add` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `list.create` | pass | pass | pass | 0 | 中 | stateful_registry_boundary |
| `list.delete` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `list.diff` | pass | pass | pass | 0 | 中 | stateful_registry_boundary |
| `list.export` | pass | pass | pass | 3 | 高 | stateful_registry_boundary |
| `list.show` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `list.validate` | pass | pass | pass | 0 | 低 | stateful_registry_boundary |
| `list.value_at` | pass | pass | pass | 0 | 中 | stateful_registry_boundary,value_sampling |
| `rc.generate` | pass | pass | pass | 0 | 低 |  |
| `sampled_pulse.inspect` | pass | pass | pass | 0 | 中 | signal_time_series,valid_ready_stream |
| `schema` | pass | pass | pass | 1 | 中 | meta_dispatch |
| `scope.list` | pass | pass | pass | 0 | 中 |  |
| `scope.roots` | pass | pass | pass | 0 | 低 |  |
| `session.close` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `session.doctor` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `session.gc` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `session.kill` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `session.list` | pass | pass | pass | 1 | 中 | stateful_registry_boundary |
| `session.open` | pass | pass | wrapper_blocker | 2 | 中 | stateful_registry_boundary |
| `signal.canonicalize` | pass | pass | pass | 0 | 低 | design_trace_root_cause |
| `signal.changes` | pass | pass | pass | 0 | 低 | signal_time_series,condition_window_event |
| `signal.resolve` | pass | pass | pass | 0 | 低 | design_trace_root_cause |
| `signal.stability` | pass | pass | pass | 0 | 中 | signal_time_series |
| `signal.statistics` | pass | pass | pass | 0 | 中 | signal_time_series,condition_window_event |
| `source.context` | pass | pass | pass | 0 | 低 | design_trace_root_cause |
| `stream.config.list` | pass | pass | pass | 0 | 低 | protocol_vs_generic_stream,stateful_registry_boundary |
| `stream.config.load` | pass | pass | pass | 0 | 中 | protocol_vs_generic_stream,stateful_registry_boundary |
| `stream.export` | pass | pass | pass | 1 | 中 | valid_ready_stream,protocol_vs_generic_stream |
| `stream.query` | pass | pass | pass | 0 | 中 | valid_ready_stream,protocol_vs_generic_stream |
| `stream.show` | pass | pass | pass | 0 | 低 | valid_ready_stream,protocol_vs_generic_stream |
| `stream.validate` | pass | pass | pass | 0 | 低 | valid_ready_stream,protocol_vs_generic_stream |
| `trace.active_driver` | pass | pass | pass | 0 | 中 | design_trace_root_cause |
| `trace.active_driver_chain` | pass | pass | pass | 1 | 高 | design_trace_root_cause |
| `trace.driver` | pass | pass | pass | 0 | 低 | design_trace_root_cause |
| `trace.load` | pass | pass | pass | 0 | 低 | design_trace_root_cause |
| `value.at` | pass | pass | pass | 0 | 中 | value_sampling |
| `value.batch_at` | pass | pass | pass | 0 | 中 | value_sampling |
| `verify.conditions` | pass | pass | pass | 0 | 中 | condition_window_event |
| `window.verify` | pass | pass | pass | 0 | 中 | condition_window_event |

## 交叉评审

fresh agent 和 MCP evidence 复核的独立结论与主报告总体一致：70/70 action 有可读证据，MCP 侧 69/70 target pass，`session.open` 是 raw xout wrapper blocker。

fresh agent 新增或强化的重点如下：
- FRESH-RISK-01：`list.export` 是 schema/backend/response format 三方错位，不只是示例错误。
- FRESH-RISK-02：`axi.request_response_pair` 证据口径内部不一致，主线程 native merged 缺失、worker isolated HOME 通过、MCP retry 缩窗通过。
- FRESH-RISK-03：MCP `raw_request` 默认 xout 会把 backend 成功 xout 包装成 JSON 错误。
- FRESH-RISK-04：response schema 对 debug 事实字段约束太弱。
- FRESH-RISK-05：stateful registry 边界会让 MCP 主批次出现非确定失败。
- FRESH-RISK-06：AXI action 之间 `direction` 接受范围不一致，容易从 query/cursor 迁移到分析类 action。
- FRESH-RISK-07：`output` / `format` 在 wrapper、native envelope、action args 中重名。
- FRESH-RISK-08：高复杂度 action 缺少足够强的最小模板和反例。

MCP 复核额外确认：最终 `mcp_final_session_list.xout` 与 `mcp_session_list_now.xout` 均为空；中间 `session.gc` 曾清理 unhealthy native session，因此报告把它标为有副作用 action。

## 2026-07-08 AI 参数误用修复映射

本轮把子 agent 调用中的错误参数视为 action 入口可用性证据，而不是隐藏为执行噪声。已落地修复如下：

| 误用/失败证据 | 根因 | 修复 |
| --- | --- | --- |
| `apb.query` / `axi.query` 误传 `args.limit` 或旧 `args.num` | protocol query 的数量/索引字段位置不统一，AI 会从相邻 action 复制 `limit` | request schema/runtime/docs 改为 `args.query.index` / `args.query.limit`；`query.index` 保持旧语义 1-based；`query.limit` 返回前 N 条 transactions；schema 负例拒绝 `args.num`、`args.limit` 和 query action 的 `direction:"all"` |
| `list.export` 传 `tsv` 或 `hex_tsv` 在 schema/runtime 间互相矛盾 | request enum、runtime accepted format、response manifest format 三方漂移 | request 只允许 `args.format:"u64bin"`；runtime 对其它 format 返回 `INVALID_REQUEST`；response schema 明确 `summary.format:"u64bin.v1"` |
| `list.delete` 传 integer `index` 导致 nlohmann type exception | schema 允许 integer/string，但 runtime 按 string 读取 | runtime 支持 integer/string index，并对非法类型返回稳定 `INVALID_REQUEST` |
| `stream.export` 传 `kind:"beats"` | schema 没有 enum，runtime 到 handler 才报错 | schema 收紧 `kind` 为 `transfer / packet / packet_beats`，format 收紧为 `tsv / csv / xout`；skill 示例和 action-reference 强调不是 `beats` |
| `trace.active_driver_chain` 传 `args.depth` | 深度字段位于 top-level `limits.max_depth`，但 action 名和常识容易诱导 `args.depth` | schema 继续拒绝 `args.depth`；新增负例测试；action-reference/examples/schema hints 明确写 `limits.max_depth` |
| MCP `xverif_debug_raw_request(output_format="xout")` 把 backend XOUT 成功误报 JSON parse 错 | xdebug adapter 用 JSON runner 解析默认 xout | adapter 改为 xout 返回文本，json/envelope 才解析 dict；MCP tool help 和 skill docs 同步默认 xout 合同；新增 adapter 单测 |
| `direction:"all"` 被 query schema 接受但 runtime 当 write 处理 | schema 承诺了 runtime 不支持的 query 语义 | `apb.query` / `axi.query` schema 收紧为 `read/write`；cursor/analysis 等 action 继续以 action-specific schema 为准 |

已验证：

- `make -C xdebug schema-test`
- `make -C xdebug contract-test`
- `make -C xdebug unit-test`
- `make -C xdebug test-fast`
- 沙箱外 `make -C xdebug test-regression`
- `PYTHONPATH=xverif_mcp/src pytest -q xverif_mcp/tests/test_direct_output_formats.py`
- `git diff --check`

环境记录：

- 第一次在默认沙箱内执行 `make -C xdebug test-regression`，后段 VCS/license/NPI 回归失败；这是环境执行位置错误，已按项目规则追加到 `AGENTS.md`。沙箱外重跑同一目标通过。

未完全完成的计划项：

- 本轮没有把 70 个 action 的 response schema 全量收紧到最终形态；只收紧了本轮硬漂移涉及的 `list.export` 和 `stream.export` 稳定字段，并保留全量 response schema 收紧作为后续专项。
- 本轮没有重写所有 `event/window/signal` action 为统一表达式接口；`event.find/export` 已是 `expr + (name 或 clock+signals)` 形态，`window.verify` 和 signal 类保持专用 action 合同。

## 2026-07-08 fresh-agent 后续闭环

fresh agent 在主修复后又指出几类可继续误导 AI 的残留点。本轮已把其中硬合同问题继续闭环：

- `trace.active_driver_chain`：移除 runtime 对 `args.limits` 的兼容读取，只保留 top-level `limits.max_depth`；request schema 和 contract 负例同步拒绝 `args.limits`、`args.depth`。
- 旧文档残留：清理 `PAYLOAD_COMPACT`、`LIST_EXPORT_XWAVEFORM_PLAN` 和 skill 文档中仍会诱导 `include_transactions`、`include_accesses`、`hex_tsv` 的可执行示例或公共合同描述。
- `list.delete`：补 contract 测试覆盖 integer index、string index 和非法 object index；复杂波形回归使用 integer index 走 runtime 成功路径，避免 schema/runtime 再次漂移。
- MCP raw request：已覆盖 xout 成功文本和 json dict 两条入口；非零 raw request 的专门 adapter 单测尚未新增，后续可作为 MCP wrapper error-path 专项补充。

最终补充验证：

- `python3 xdebug/tools/sync_runtime_request_schemas.py --check`
- `python3 xdebug/tools/sync_action_schema_hints.py --check`
- `git diff --check`
- `make -C xdebug schema-test`
- `make -C xdebug contract-test`
- `make -C xdebug unit-test`
- `make -C xdebug test-fast`
- 沙箱外 `make -C xdebug test-regression`
- `PYTHONPATH=xverif_mcp/src pytest -q xverif_mcp/tests/test_direct_output_formats.py`
