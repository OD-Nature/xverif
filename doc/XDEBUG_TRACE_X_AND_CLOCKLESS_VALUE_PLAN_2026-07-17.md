# xdebug `trace.x` 与无时钟点值查询实施计划

日期：2026-07-17
状态：已完成（第二阶段）

## 1. 启动与 Goal 约束

实施第一步必须先将本计划完整写入当前文档。文档落盘后立即创建不设 token
budget 的 goal，`objective` 使用本计划书完整内容。只有确认 goal 处于 active
状态后，才允许修改源码、fixture、schema 或其它文档。

## 2. 目标

- 新增 combined action `trace.x`：从指定 signal/time 开始，任一 bit 为 X 即启动，
  沿 active trace、波形变化和层次连接向更早的因果位置追踪，直到找到 X 起点、
  上游不再呈现 X，或遇到明确边界。
- `value.at`、`value.batch_at` 的 `clock` 改为可选；省略时直接读取指定 FSDB
  时间的最终值，传入时保持现有 clock-sampled 行为。
- 控制 X、驱动 X、越界选择等原因采用 best-effort 证据；不能精确证明时返回
  部分证据和明确状态，不强行声称根因。

## 3. 公共合同与实现

- `value.at` 必填 `signal,time`，`value.batch_at` 必填 `signals,time`。
  - 无 `clock`：`sampling_mode=raw_time`，直接点读，不伪造边沿前后样本。
  - 有 `clock`：`sampling_mode=clock_sampled`，现有 `edge/sample_point` 语义不变。
  - 无 `clock` 却传 `edge` 或 `sample_point` 时返回 `INVALID_ARGUMENT`。
  - 默认十六进制，XOUT/JSON 值统一使用 `'h`、`'b`、`'d` 前缀。
- `trace.x` 为 experimental combined action，必填 `signal,time`，可选
  `value_format=hex|bin|dec`，默认 `hex`。限制使用顶层 `limits.max_depth`、
  `max_nodes`、`max_time_steps` 和 `max_trace_signals`；不引入 `clock`、
  `clk_period` 或半周期窗口。
- 追踪状态为 `(canonical_signal,time,x_mask)`：
  - 查询点任一 bit 为 X 即追踪，只传播相关 `x_mask`；Z 本身不作为 X。
  - 使用 `SignalChangeCursor` 回溯当前 X 可见区间，在 X 出现时间调用共享
    active-trace resolver。
  - 组合路径保持 causal time；跨 `always`/时序边界使用 active time 向更早时间推进。
  - module port、interface/modport 使用现有连接解析逻辑穿透。
  - assignment RHS、控制条件和动态 select index 作为图分支，不强行压成单链。
  - bit-select index 可解析且越界时尽力记录 base、index、合法范围和源码位置；
    证据不足时仍返回有效 partial 结果。
- 返回 `summary` 与 `data.nodes/edges/origins/limitations`：
  - `evidence_status=proven|best_effort|unresolved` 区分证据强度。
  - termination 至少覆盖 `not_x_at_query_time`、`origin_found`、
    `x_not_observable_upstream`、`primary_input_x`、`force_x`、
    `x_present_at_fsdb_start`、`undumped_boundary`、`control_only`、
    `loop_detected` 和 `limit`。
  - origin 允许是候选原因；只有证据充分时标为 `proven`。
  - XOUT 输出 signal/time/value/X mask/关系/源码表，并在末尾列 origins、
    limitations 和 termination。
- 同步 action inventory、生成源、request/response schema、examples、runtime registry、
  MCP catalog、xverif skill、架构说明和安装镜像，不只修改生成产物。

## 4. 测试与验收

- Goal 激活后的第一项技术验证是建立正式 `xdebug.trace_x_xprop` fixture，使用
  VCS `-xprop=tmerge` 编译并生成 daidir、FSDB 和 Xprop instrumentation 记录。
  所有 VCS/NPI/FSDB 测试在沙箱外执行，不自动切换非 Xprop 仿真。
- `value.at/batch_at` 覆盖无 clock 单点/批量点读、同时间戳最终值、X/Z、缺失信号、
  时间越界、value format、既有 clock 模式，以及无 clock 搭配 `edge/sample_point`
  的明确拒绝。
- `trace.x` Xprop fixture 覆盖：X 穿过多个 `always`、多级 module port、
  interface/modport、未知控制条件造成 X、RHS/driver 自身为 X、动态 bit-select
  index 越界造成 X、部分 bit 为 X，以及跨时序边界向更早时间追踪。
- 复杂场景最低验收是 action 不崩溃、不循环、能穿过可解析边界，并以正确
  termination/evidence status 收口；仅对稳定可证明的 fixture 断言精确根因。
- 补充非 X、FSDB 起点已有 X、X 上游不可见、undumped、force、循环和 limits；
  校验 JSON schema、XOUT 前缀与 compact 输出。
- 执行 schema 同步与审计、全仓 fast gate，并在沙箱外执行新增 combined/Xprop
  suite、`xdebug.contract` 和相关 active-trace 回归。所有测试和 skill 镜像验收
  完成后才将 goal 标记 complete。

## 5. 默认边界

- v1 仅以 `tmerge` 作为正式语义和验收模式，不把 `xmerge` 混入根因合同。
- 不要求所有 X 成因都有精确证据，禁止把 best-effort 包装成 proven。
- 不修改 `trace.active_driver` 或 `trace.active_driver_chain` 的现有公共行为；仅复用
  或下沉共享 helper。
- 本计划不默认包含 Git commit 或 push。

## 6. 实施结果（2026-07-18）

- 已新增 experimental combined action `trace.x`，先检查查询值是否含 X，再复用
  active-trace 图穿过 assignment、module port、interface/modport 和更早 active time；
  返回 `proven|best_effort|unresolved` 证据等级与明确 termination。
- 已实现 `limits.max_time_steps`，定义为允许处理的不同 trace time 数量；达到上限时
  返回 `termination:"limit"` 和对应 limitation，不再存在公开参数静默忽略。
- `value.at` / `value.batch_at` 已支持无 clock 精确点读，canonical
  `summary.sampling_mode` 区分 `raw_time` 与 `clock_sampled`；无 clock 搭配
  `edge/sample_point` 会明确拒绝。默认 hex，hex/bin/decimal 使用 `'h` / `'b` / `'d`。
- 已建立 `xdebug.trace_x_xprop` 正式 fixture，VCS 使用 `-xprop=tmerge`，覆盖多个
  always、module/interface/modport、控制 X、driver X、越界 bit-select、部分 bit X 和
  temporal active trace。
- schema、examples、action inventory、MCP projection、README、xverif skill 和架构说明
  已同步；repo skill 已安装并验收到 Codex/Claude 两个镜像。
- 验证通过：schema/example 全套静态审计、fast gate 237 tests、xdebug.contract 71 tests、
  trace_x_xprop 1 test、active_semantics 1 test、active_zero_evidence 15 tests、
  active_trace.p0 6 tests，以及 engine/frontend 全量编译。

## 7. 第二阶段：多分支 DFS、深度续查与 XOUT 渲染

### 7.1 目标与默认值

- `trace.x` 改为多分支 DFS 追踪。RHS 和 control 同等按“传播时刻是否含 X”判断，
  不要求发生跳变；Z-only 不作为 X 依赖。
- 新增 `limits.max_chains`，最小为 1、默认值为 8。它限制返回的叶子 chain 总数；
  `max_depth` 继续独立限制单条 chain 深度。
- 每条 branch、每一跳都重新寻找依赖信号从非 X 进入连续 X 区间的
  `x_onset_time`，再从该时间继续 active-driver 追踪。因此 `trace.x` 可以沿 chain
  多次向更早时间推进，不受 active trace chain 只在开始时推进一次的规则限制。
- `trace.active_driver_chain` 和 `trace.x` 因 `max_depth` 停止时，都必须返回可直接
  续查的 signal、time、value 和调用参数。
- 两个 action 的源码窗口、相邻源码合并、active-line 标记和 source grouping 复用
  `trace_source_path_formatter` helper，不复制第二套源码合并 renderer。

### 7.2 追踪、分裂与限制合同

- 根信号在查询时刻不含 X 时返回 `not_x_at_query_time`。含 X 时反向遍历 value
  changes，跨过所有仍含 X 的值；即使 X pattern 或 X mask 改变也继续，直到最近的
  非 X，后一变更时刻即当前信号的 `x_onset_time`。
- 在当前信号的 `x_onset_time` 确定 active statements，收集 RHS、control、
  port/interface 依赖，并在传播时刻采样。仅含 X 的依赖进入下一层。
- 多个 X 依赖按源码文件、行号、canonical signal path 稳定排序，以显式 LIFO stack
  做 DFS。同一 canonical signal 同时作为 RHS/control 时只创建一个子分支，并保留
  全部 relation 标签。
- 根 chain 计为 1。分裂时复用当前 chain 作为第一个子分支，其余分支消耗新配额。
  超出 `max_chains` 的依赖写入对应 chain 的 `pending_x_dependencies` 和
  `omitted_x_dependency_count`，不生成额外 chain。
- `max_depth` 只停止命中的 chain；其他 chain 继续。全局 `max_nodes` 或
  `max_time_steps` 耗尽时停止剩余 DFS，并返回所有已完成和待处理 chain 的现场。
- visited key 以单条 chain 的 `(signal,x_onset_time)` 判断环路；不同 chain 可以到达
  同一节点。完成与受限 chain 并存时，顶层 `termination=partial`。
- force、primary input、FSDB 起始即为 X、undumped、动态 select 越界、环路和上游 X
  不可见形成明确边界；证据不足时返回 best-effort/limitation，不做 fallback。

### 7.3 深度 frontier 与 AI 续查合同

- 两个 action 统一增加 `data.depth_frontiers[]`。仅当
  `termination_detail=max_depth` 时出现，每项包含 `chain_id`、`signal`、`time`、
  `value`、可用时的 `x_mask` 和 `stopped_after_depth`。
- frontier 表示尚未处理、下一次应作为 action 输入的信号，而不是上一跳已处理完的
  节点。其 value 必须在对应 signal/time 实际点读，不能沿用父节点值。
- active-driver chain 的 frontier time 使用依赖的 active time；`trace.x` 使用该依赖
  自己的 `x_onset_time`。
- 顶层 `suggested_next_actions[]` 同时给出：
  - `continue_from_depth_frontier`：从 frontier signal/time 继续，保持当前有效深度；
  - `rerun_from_root_with_higher_depth`：从原始 signal/time 重跑，建议 max depth 翻倍。
- 建议对象必须包含可直接调用的 `action`、`args` 和 `limits`。其他显式 limits 原样
  保留，不改变 session、transport、backend 或数据源。只有 `max_depth` 触发 depth
  continuation；其他 limit 不生成错误建议。

示例 JSON：

```json
{
  "data": {
    "depth_frontiers": [
      {
        "chain_id": "c1",
        "signal": "tb.dut.u_mid.src_x",
        "time": "75ns",
        "value": "'hx",
        "x_mask": "'b1",
        "stopped_after_depth": 8
      }
    ]
  },
  "suggested_next_actions": [
    {
      "action": "trace.x",
      "reason": "continue_from_depth_frontier",
      "chain_id": "c1",
      "args": {
        "signal": "tb.dut.u_mid.src_x",
        "time": "75ns",
        "value_format": "hex"
      },
      "limits": {"max_depth": 8, "max_chains": 8}
    },
    {
      "action": "trace.x",
      "reason": "rerun_from_root_with_higher_depth",
      "args": {
        "signal": "tb.dut.out",
        "time": "120ns",
        "value_format": "hex"
      },
      "limits": {"max_depth": 16, "max_chains": 8}
    }
  ]
}
```

### 7.4 XOUT 预期

`trace.active_driver_chain` 深度停止：

```text
@xdebug.trace.active_driver_chain.v1

summary:
signal: tb.dut.out
time: 120ns
termination: limit
termination_detail: max_depth
hop_count: 8
truncated: true

source: rtl/core.sv:41-45
   41 | always_comb begin
>  42 |   out = mid;
   43 | end

active_signals:
chain  hop  time   relation  line  signal_path
c0     0    120ns  root      42    tb.dut.out
c0     1    95ns   rhs       42    tb.dut.mid

depth_frontiers:
chain  signal               time  value  stopped_after_depth
c0     tb.dut.u_mid.source  75ns  'hxx   8

next:
mode                               action                     signal               time   max_depth
continue_from_depth_frontier       trace.active_driver_chain  tb.dut.u_mid.source  75ns   8
rerun_from_root_with_higher_depth  trace.active_driver_chain  tb.dut.out           120ns  16
```

`trace.x` 多分支及深度停止：

```text
@xdebug.trace.x.v1

summary:
signal: tb.dut.out
time: 120ns
termination: partial
chain_count: 3
completed_chain_count: 2
limited_chain_count: 1
truncated: true

source: rtl/core.sv:41-45
   41 | always_comb begin
>  42 |   out = enable ? lhs ^ rhs : hold;
   43 | end

active_signals:
chain  hop  time   relation  line  signal_path
c0     0    120ns  root      42    tb.dut.out
c0     1    80ns   rhs       42    tb.dut.lhs
c1     1    90ns   rhs       42    tb.dut.rhs
c2     1    75ns   control   42    tb.dut.enable

chains:
chain  status        current_signal       current_time  value  reason
c0     origin_found  tb.dut.src_a         40ns          'hx    force_x
c1     origin_found  tb.src_b             20ns          'hxx   primary_input_x
c2     limit         tb.dut.u_ctrl.src_x  55ns          'hx    max_depth

depth_frontiers:
chain  signal               time  value  x_mask  stopped_after_depth
c2     tb.dut.u_ctrl.src_x  55ns  'hx    'b1     8

next:
chain  mode                               action   signal               time   max_depth  max_chains
c2     continue_from_depth_frontier       trace.x  tb.dut.u_ctrl.src_x  55ns   8          8
-      rerun_from_root_with_higher_depth  trace.x  tb.dut.out           120ns  16         8
```

所有 value 按 `value_format` 使用 `'h`、`'b`、`'d` 前缀，默认十六进制。
`depth_frontiers` 和 `next` 固定放在源码与 chain 状态之后。

### 7.5 实验、测试与交付

- 修改追踪实现前，在仓库外临时目录、沙箱外运行 VCS `-xprop=tmerge` 与 NPI/FSDB
  探针，验证两个 RHS 同时 X、control 与 RHS 同时 X、多个 active assignment、X mask
  改变但持续含 X、同时间点变化、FSDB 起始即为 X，以及 frontier 时间语义。
- 正式 fixture 覆盖多 RHS X、control X、多层 always、module port、
  interface/modport、动态 bit-select 越界和后续节点再次分裂。
- 验证稳定 DFS 顺序及 `max_chains=1/2/8`，省略时默认 8，chain 数永不超限。
- 验证单条 chain 可以多次向更早 X onset 推进；验证多个 chain 同时 depth limit 时，
  每个受限 chain 都有独立 frontier 和续查参数。
- 覆盖两个 action 的默认深度和显式 `max_depth=1/2/8`：frontier 续查能够接上原链，
  提高深度重跑能够包含原 frontier，非深度 limit 不生成 depth continuation。
- 同步 action source、schema 生成源、request/response examples、action reference、
  xverif skill 和 xdebug 架构说明。
- 运行 schema generator/check、runtime compatibility、example validation、XOUT 单元测试
  和正式 catalog suite。所有 NPI、FSDB、VCS、xprop 测试均在沙箱外执行。

## 8. 第二阶段实施结果（2026-07-18）

- `trace.x` 已切换为显式 LIFO 的稳定 DFS；每条 chain 独立回溯 X onset，允许在后续
  hop 继续向更早时间推进。RHS、control 与 port/interface 依赖统一按传播时刻是否
  含 X 过滤，多依赖会分裂为并行 chain。
- 已新增 `limits.max_chains`，默认 8。达到上限时不丢弃现场，而是在保留的 chain 上
  返回 `pending_x_dependencies`、分支事件和 limitation。
- `trace.x` 与 `trace.active_driver_chain` 在 `max_depth` 停止时均返回
  `data.depth_frontiers[]` 和顶层 `suggested_next_actions[]`，包含可直接续查的 signal、
  time、value、action args 与 limits；同时给出从根提高深度重跑的建议。
- 两个 action 共用 `trace_source_path_formatter` 的源码合并、active line、chain 表、
  frontier、next 和 limitation 渲染。真实 XOUT 已确认顺序为 summary、query/source、
  active signals、chains、depth frontiers、next、limitations，默认值显示为十六进制，
  例如 `8'hxx`。
- 正式 xprop fixture 已扩展两个 RHS 同时为 X、control 与 RHS 同时为 X、分支限额和
  深度 frontier 场景；原有多 always、module/interface、控制 X、driver X 和越界
  bit-select 覆盖继续保留。
- 验证通过：全量编译；schema 生成一致性、Draft-7 runtime audit、158 个 schema 与
  153 个 example；fast gate 237 项；`skills.xverif` 8 项；`xdebug.contract` 71 项；
  `xdebug.trace_x_xprop` 1 项；`xdebug.active_semantics` 1 项；`xdebug.cpp_unit` 1 个
  catalog suite；nightly `xdebug.active_trace.p0` 6 项。xverif skill 已同步并 diff 验收
  `~/.codex/skills/xverif` 与 `~/.claude/skills/xverif`。
