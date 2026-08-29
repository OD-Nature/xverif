# 协议分析模式

协议工具分为两层：`iter_edge_samples` 流式读取同一个 clock 的采样行，纯 Python
状态机逐行完成配对和聚合。这样真实 pynpi 访问集中在一层，协议状态机可以用普通
Python fixture 做单元测试。默认输出 summary；需要事务、timeline 或 payload 时必须
选择 `detail=transactions|timeline|full` 并提供输出文件，协议示例不提供 `line_limit`。

时间字段保持 FSDB integer tick；数据库单位由 `meta.scale_unit` 单独说明。握手相关信号
含 X/Z 时不计 transfer，并通过 `analysis_quality=ambiguous`、unknown count 和首个时间保留证据。

## APB

`PREADY` 和 `PSLVERR` 都是必需配置，不允许省略后假设 zero-wait 或 no-error：

```json
{
  "clk": "top.pclk",
  "rst_n": "top.presetn",
  "edge": "negedge",
  "psel": "top.psel",
  "penable": "top.penable",
  "pready": "top.pready",
  "pslverr": "top.pslverr",
  "pwrite": "top.pwrite",
  "paddr": "top.paddr",
  "pwdata": "top.pwdata",
  "prdata": "top.prdata"
}
```

状态机记录 setup begin、access begin、completion，以及 wait cycle 和 error response。
completion 只在 `PSEL && PENABLE && PREADY` 成立时发生。

## AXI4 / AXI4-Lite

只支持 AXI4/AXI4-Lite 五个独立 channel；配置含 AXI3 `WID` 时明确拒绝：

- AW：`AWVALID && AWREADY`
- W：`WVALID && WREADY`
- B：`BVALID && BREADY`
- AR：`ARVALID && ARREADY`
- R：`RVALID && RREADY`

W channel 可以先于 AW handshake，因此写状态机先缓存 W burst，再和 AW 配对。B response
允许不同 ID 间重排，同 ID 保持 FIFO；R 必须用 RID 严格匹配 pending AR。orphan、beat
数量不匹配或 response dependency 违反属于 hard error，不返回部分 summary；扫描窗口结束仍
pending 是成功结果，并在 final pending/outstanding 与 reset-cleared 字段中区分。

标准 phase latency 同时统计：AW 到首 W、AW 到末 W、首 W 到末 W、末 W 到 B、AR 到首 R、
AR 到末 R、首 R 到末 R。`transactions` 不含 payload，只有 `full` 返回 data beats。

## Valid-ready / backpressure stream

配置必须恰好包含 `ready` 或 `bp` 之一；若使用 packet boundary，`sop` 和 `eop` 必须同时存在：

```json
{
  "clock": "top.clk",
  "edge": "posedge",
  "sample_point": "after",
  "rst_n": "top.rst_n",
  "valid": "top.valid",
  "ready": "top.ready",
  "data": "top.data",
  "sop": "top.sop",
  "eop": "top.eop",
  "fields": {"opcode": "top.opcode"}
}
```

ready 模式的 transfer 是 `valid && ready`，bp 模式是 `valid && !bp`。packet 状态机严格
检查 repeated SOP 和 orphan beat，返回 beat、packet、stall window 与 incomplete packet 统计。

## AI 自定义处理

这些 helper 是通用 API 和类的示例，不限制 AI 的处理方式。AI 可以在同一 Python 脚本中
按地址、ID、时间段或字段过滤，构造临时字典/队列/索引，关联其它日志，计算自定义分位数，
或把一次扫描结果缓存到任务内对象。优先让一次扫描直接生成所需结果；不要默认引入持久化
缓存数据库或把项目特定过滤器固化进公共 helper。

## 验证规则

第一次用于新项目时，和 xdebug protocol action、UVM monitor log 或已知 scoreboard 中至少
一个来源对齐。真实 pynpi/FSDB 验证必须在沙箱外执行，并只消费测试 catalog 提供的缓存；
cache miss 时报告 prepare 命令，不自动仿真或切换数据源。
