# xdebug 常见 Debug Recipes

本文是面向 AI agent 的工作流速查。执行时仍以 runtime `actions`、`schema` 和 examples 为最终契约。

## MCP 入口规则

MCP 场景下，本文所有原生 xdebug action 都通过 `xverif_debug_query` 进入：先 `xverif_debug_session_open` 得到 session，再把 `action`/`args`/`limits`/`output` 传给 query。不要把常规 debug workflow 改走 `xverif_debug_raw_request`；raw request 不维护 MCP 托管的 stdio-loop/LSF session。

## 通用原则

- 先 compact 查询，再按需 include。
- 先定位时间点，再做因果 join。
- 同一时间多信号取值用 `value.batch_at`。
- 不要导出全量 rows/samples/transactions 作为第一步。
- 最终结论必须保留 `signal/time/value/file:line/finding/confidence/truncated`。

## Ready 卡低

1. `value.batch_at` 取 `valid/ready/full/state/backpressure`。
2. `signal.changes` 查 `ready` 首次卡住或最后变化时间。
3. 有 `daidir + fsdb + time` 时用 `trace.active_driver` 查当前生效 driver。
4. 若 driver 指向 `full`、state 或 grant 条件，补 `value.at` / `value.batch_at` 查控制信号值。
5. 用 `source.context include_source:true` 获取最终源码 evidence。

请求骨架：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {"session_id": "case_a"},
  "args": {
    "time": "@stall",
    "signals": ["top.u.valid", "top.u.ready", "top.u.full", "top.u.state_q"],
    "format": "hex"
  }
}
```

## Valid 有脉冲但没被接受

1. `event.find` 或 `event.export` 查 `valid && !ready`。
2. `handshake.inspect` 找 long stall 或 accept gap。
3. `value.batch_at` 取 payload、ready、backpressure、state。
4. `trace.driver` 或 `trace.active_driver` 查 ready/backpressure 的设计原因。

表达式查找：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {"session_id": "case_a"},
  "args": {
    "expr": "valid && !ready",
    "clk": "top.clk",
    "signals": {
      "valid": "top.u.valid",
      "ready": "top.u.ready"
    },
    "time_range": {"begin": "0ns", "end": "100us"},
    "mode": "first"
  }
}
```

## AXI latency 异常

1. `axi.analysis` 用 compact 查 latency/outstanding/response findings。
2. 对 top abnormal 的 begin/end 设 cursor 或直接用 TimeSpec。
3. `value.batch_at` 查 AW/W/B/AR/R channel 的 valid/ready/id/resp。
4. 只有需要证明异常 transaction/beat 时才加 `include_transactions:true` 或 `include_beats:true`。

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.analysis",
  "target": {"session_id": "wave_case"},
  "args": {
    "name": "axi0",
    "analysis": "latency",
    "direction": "read",
    "time_range": {"begin": "0ns", "end": "100us"},
    "max_items": 20
  }
}
```

## APB slow/error access

1. `apb.query` 查 error/slow findings。
2. 对 finding 的 time/window 用 `value.batch_at` 取 `psel/penable/pready/pslverr/paddr/pwrite`。
3. 只有需要完整访问明细时才加 `include_accesses:true`。

## X/Z 传播

1. `detect_anomaly` 查 `unknown_xz`。
2. `signal.changes` 找第一个 X/Z 出现时间。
3. 有 combined 资源时用 `trace.active_driver` 在该时间查生效 driver。
4. 用 `trace.expand` 向上游扩展，寻找 X/Z 源。

## Counter / FSM 异常

1. `value.at` 或 `signal.statistics` 确认状态/计数异常。
2. `fsm.explain` 获取状态更新规则。
3. `trace.driver` 查更新条件。
4. `source.context` 获取 `file:line` evidence。

## 当前生效 driver join

使用条件：必须有 `daidir + fsdb + signal + requested_time`。

1. 波形侧先定位异常时间。
2. `value.batch_at` 取相关信号。
3. `trace.active_driver` 做 active trace。
4. `resolved`：保留 driver kind、file/line、active_time、control evidence。
5. `control_only`：继续查 control signal 值，不要宣称已解析 direct data driver。
6. `unresolved`：回到 `trace.driver`、`trace.expand` 或源码 `rg` 缩小信号路径。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {"session_id": "case_a"},
  "args": {
    "signal": "top.u.ready",
    "requested_time": "@stall",
    "include_control": true,
    "include_parity": true
  }
}
```

## 生成波形证据视图

当用户需要给 nWave 打开同一组信号、marker、analog 波形或表达式信号时，用 `rc.generate`。不要让 AI 手写 rc；由 xdebug 校验 FSDB 信号和 marker 时间后生成。

详细配置见 [rc-generate.md](rc-generate.md)。

## APB/AXI 协议查询

**必须先用 config.load 注册信号映射，再进行任何 query/analysis。**

### 前置条件：加载配置

APB 示例（9 信号）：

```json
{
  "api_version": "xdebug.v1",
  "action": "apb.config.load",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "apb0",
    "config": {
      "clk": "top.pclk",
      "rst_n": "top.presetn",
      "paddr": "top.u_dut.paddr",
      "psel": "top.u_dut.psel",
      "penable": "top.u_dut.penable",
      "pwrite": "top.u_dut.pwrite",
      "pwdata": "top.u_dut.pwdata",
      "prdata": "top.u_dut.prdata",
      "pready": "top.u_dut.pready"
    }
  }
}
```

AXI 示例（26 信号，5 通道各需 valid/ready + data/addr/id/last/strobe + clk + rst_n）：

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.config.load",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "axi0",
    "config": {
      "clk": "top.aclk",
      "rst_n": "top.aresetn",
      "awvalid": "top.u_dut.awvalid",
      "awready": "top.u_dut.awready",
      "awaddr": "top.u_dut.awaddr",
      "awlen": "top.u_dut.awlen",
      "awsize": "top.u_dut.awsize",
      "awburst": "top.u_dut.awburst",
      "awid": "top.u_dut.awid",
      "wvalid": "top.u_dut.wvalid",
      "wready": "top.u_dut.wready",
      "wdata": "top.u_dut.wdata",
      "wstrb": "top.u_dut.wstrb",
      "wlast": "top.u_dut.wlast",
      "bvalid": "top.u_dut.bvalid",
      "bready": "top.u_dut.bready",
      "bid": "top.u_dut.bid",
      "bresp": "top.u_dut.bresp",
      "arvalid": "top.u_dut.arvalid",
      "arready": "top.u_dut.arready",
      "araddr": "top.u_dut.araddr",
      "arlen": "top.u_dut.arlen",
      "arsize": "top.u_dut.arsize",
      "arburst": "top.u_dut.arburst",
      "arid": "top.u_dut.arid",
      "rvalid": "top.u_dut.rvalid",
      "rready": "top.u_dut.rready",
      "rdata": "top.u_dut.rdata",
      "rresp": "top.u_dut.rresp",
      "rid": "top.u_dut.rid",
      "rlast": "top.u_dut.rlast"
    }
  }
}
```

### 查询

加载后用 `apb.config.list` / `axi.config.list` 确认已注册，然后：

- `apb.query` / `axi.query`：查指定时间窗口的传输。
- `axi.analysis`：查异常（protocol violation、timing outlier 等）。
- `axi.channel_stall`：查通道级停顿热点。
- `axi.latency_outlier`：查延迟异常。
- `axi.outstanding_timeline`：查未完成事务的时间线。

**没有 config.load，query 会报 `MISSING_FIELD: requires args.name or latest config`。** config 字段名以实际代码中的 VIP/DUT 信号名为准，没有自动检测。
