# xdebug 实战示例

本文给 AI agent 提供 xdebug 示例写法。示例采用“现象 -> 最小查询 -> 证据读取 -> 下一步”的结构，避免只堆命令。

## MCP 调用形态

MCP 场景下先用 `xverif_debug_session_open` 打开 session，再用 `xverif_debug_query` 进入 xdebug 原生 action。本文 JSON 片段只展示 query 的核心参数：

```json
{
  "session_id": "case_a",
  "action": "value.batch_at",
  "args": {},
  "limits": {},
  "output": {"verbosity": "compact"},
  "output_format": "json"
}
```

需要 SDK-free wrapper 或 raw CLI 时，把同一 `action/args/limits/output` 放进 [json-api.md](json-api.md) 的原生 xdebug request envelope。

## Ready 卡低

现象：`valid` 保持为 1，但 `ready` 长时间为 0。

最小查询：

```json
{
  "session_id": "case_a",
  "action": "value.batch_at",
  "args": {
    "time": "@stall",
    "signals": [
      "top.u_if.valid",
      "top.u_if.ready",
      "top.u_if.full",
      "top.u_if.state_q",
      "top.u_if.bp"
    ],
    "format": "hex"
  },
  "output_format": "json"
}
```

证据读取：

- `summary` 和 `data.values` 确认同一时间点的 valid/ready/full/state。
- 若 `ready=0` 且 `full=1`，下一步查 `full` 或 state 的 driver。
- 若返回 `truncated:true`，缩小 signal 列表或时间点，不要直接下结论。

下一步：

```json
{
  "session_id": "case_a",
  "action": "trace.active_driver",
  "args": {
    "signal": "top.u_if.ready",
    "time": "@stall",
    "include_control": true
  },
  "output_format": "json"
}
```

最终回答保留 `ready` 的值、stall 时间、源码窗口中的有效行、`file:line` 和 `signal_path`。

## Valid 未被接受

现象：valid 有脉冲，但没有形成 transfer。

最小查询：

```json
{
  "session_id": "case_a",
  "action": "event.find",
  "args": {
    "expr": "valid && !ready",
    "clock": "top.clk",
    "signals": {
      "valid": "top.u_if.valid",
      "ready": "top.u_if.ready"
    },
    "time_range": {"begin": "0ns", "end": "100us"},
    "mode": "first"
  },
  "output_format": "json"
}
```

证据读取：

- 用 `summary.first` / `summary.last` 锁定事件时间。
- 如果 event 返回上下文信号为 `?` 或字段不完整，不要猜值；对事件时间补 `value.batch_at`。

下一步：

```json
{
  "session_id": "case_a",
  "action": "handshake.inspect",
  "args": {
    "clock": "top.clk",
    "valid": "top.u_if.valid",
    "ready": "top.u_if.ready",
    "time_range": {"begin": "0ns", "end": "100us"},
    "max_stall_cycles": 16
  },
  "output_format": "json"
}
```

注意确认 ready 极性。active-high backpressure 不能直接当 active-high ready。

## AXI latency 或通道 stall

现象：AXI read/write 响应慢，或某个 channel valid/ready 长时间不能握手。

最小查询先加载映射：

```json
{
  "session_id": "case_a",
  "action": "axi.config.load",
  "args": {
    "name": "axi0",
    "config": {
      "clock": "top.aclk",
      "rst_n": "top.aresetn",
      "arvalid": "top.u_axi.arvalid",
      "arready": "top.u_axi.arready",
      "araddr": "top.u_axi.araddr",
      "arid": "top.u_axi.arid",
      "rvalid": "top.u_axi.rvalid",
      "rready": "top.u_axi.rready",
      "rdata": "top.u_axi.rdata",
      "rresp": "top.u_axi.rresp",
      "rlast": "top.u_axi.rlast"
    }
  },
  "output_format": "json"
}
```

然后查 stall：

```json
{
  "session_id": "case_a",
  "action": "axi.channel_stall",
  "args": {
    "name": "axi0",
    "channel": "r",
    "time_range": {"begin": "0ns", "end": "100us"},
    "limit": 20
  },
  "output_format": "json"
}
```

证据读取：

- 先看 `summary.sample_count`、`data.max_stall_cycles`、`data.findings[]`。
- 只有需要证明异常 transaction/beat 时，才加 `include_transactions` 或 `include_beats`。

## APB slow/error access

现象：APB 访问等待过长、读写数据不符合预期或 error response。

流程：

1. `apb.config.load` 注册 `clk/rst_n/paddr/psel/penable/pwrite/pwdata/prdata`，按需提供 `pready`。
2. `apb.query` 查目标时间窗口或地址。
3. 对 finding 时间用 `value.batch_at` 取 `psel/penable/pready/paddr/pwrite/pwdata/prdata`。

不要跳过 config.load。`apb.config.list` 只能列已加载配置，不会自动搜索 DUT。

## X/Z 传播

现象：某信号出现 X/Z 或 `known:false`。

最小查询：

```json
{
  "session_id": "case_a",
  "action": "detect_abnormal",
  "args": {
    "signals": ["top.u_if.data_leaf0", "top.u_if.data_leaf1", "top.u_if.valid", "top.u_if.ready"],
    "time_range": {"begin": "0ns", "end": "100us"},
    "checks": [{"type": "unknown_xz"}],
    "limit": 20
  },
  "output_format": "json"
}
```

证据读取：

- `known:false` 只是未知值证据，不是 root cause。
- packed struct / aggregate payload 必须由 AI 直接传最终 leaf signal path 检查；不要直接把 aggregate path 的 unknown finding 当作最终协议结论，也不要期待 xdebug 自动展开 struct。
- 找到第一处 unknown 后，用 `signal.changes` 缩小出现时间。
- combined session 下对同一时间调用 `trace.active_driver`。

## 地址或数据错误回溯

现象：总线地址、数据或 payload 与预期不一致。

思路：

1. 用 `value.batch_at` 同时取最终总线信号和候选上游路径，先确认错误来自哪条路径。
2. 对异常路径用 `trace.driver` 找赋值来源。
3. 用 `source.context` 读取赋值上下文。
4. 回到波形，用 `value.batch_at` 验证 driver 条件信号在异常时间的取值。

示例 batch：

```json
{
  "session_id": "case_a",
  "action": "value.batch_at",
  "args": {
    "time": "10462510ps",
    "signals": [
      "top.u_arb.arb_addr",
      "top.u_arb.arb_src",
      "top.u_blk.req_addr",
      "top.u_entry.req_addr",
      "top.u_axi.araddr"
    ],
    "format": "hex",
    "slice_hint": {"chunk_width": 32, "count": 4}
  },
  "output_format": "json"
}
```

若响应包含 `xbit_hints.commands[]`，把字段切分交给 xbit，不要由 AI 心算大位宽 hex。

## event 性能或截断

现象：event 查询窗口很大、超时或返回截断。

处理：

- 先缩小 `time_range`，优先查 `event.find` 的 first/last，不要直接 `event.export` 全量 rows。
- 单信号变化用 bounded `signal.changes`；周期统计用 `signal.statistics` 加 clock。
- `truncated:true` 时继续缩小窗口或调整具体 limits，不要把返回样本当全集。

## 生成 nWave 证据视图

现象：需要给用户或同事一个能打开同一组信号和 marker 的 `signal.rc`。

流程：

1. 用前面的查询确定关键时间、关键 bus、handshake 信号和 root-cause 信号。
2. 写 JSON 配置，包含 groups、subgroups、markers、expr_signals。
3. 用 `rc.generate` 校验 FSDB 信号并生成 rc。

```json
{
  "session_id": "case_a",
  "action": "rc.generate",
  "args": {
    "config_path": "wave_view.json",
    "output": {
      "path": "signal.rc"
    }
  },
  "output_format": "json"
}
```

默认不要把完整 rc 文本粘给用户；报告 `summary.rc_path`、marker、signal/group 计数和 validation 结果。

## 排障示例

现象：`SESSION_UNHEALTHY`、stdio-loop invalid JSON、socket timeout、license/NPI 失败。

定位顺序：

1. `xdebug log doctor --session <id> --json`
2. public actions：`actions.ndjson`
3. stdio-loop：`stdio.ndjson`
4. engine lifecycle：`lifecycle.ndjson`
5. transport：`transport.ndjson`
6. crash：`crash_marker.ndjson` 和 `log_health.ndjson`

对外共享日志前使用 `xdebug log bundle --session <id> --out debug_bundle.redacted.tgz --redact`。
