# xdebug Active Trace Ambiguous RHS 证据收口计划

日期：2026-07-17
状态：已实施

## 1. 启动与 Goal 约束

实施第一步必须先将本计划完整写入当前文档。文档落盘后立即创建不设
token budget 的 goal，`objective` 使用本计划书完整内容。只有确认 goal 处于
active 状态后，才允许修改源码、schema、fixture 或其它文档。

实施期间以本文档为 source of truth。如果必须改变已确认的公共合同，先更新
本计划和 goal 内容，再继续实施。

## 2. 目标与语义

- 删除 `trace.active_driver_chain` 遗留的 `± clk_period/2` RHS 推测，不再根据
  半周期内哪个信号变化来自动选择下一跳。
- 统一以现有公共 resolver 的精确 FSDB change time、`npi_trace_driver_by_hdl2`
  和 `npi_check_active_handle` 作为 active statement 事实源。
- ambiguous 时展示每条 active statement 的全部 RHS 信号在精确
  `active_time` 之前和该时刻的最终值，但这些值只用于解释，不再用于
  自动选择唯一根因。
- 不增加 clock 推断、邻近时间、波形启发式、alias 兼容或其它静默 fallback。

## 3. 实现收口

- 从 runtime、request schema、生成源、examples、skill 和文档彻底删除
  `args.clk_period`；旧请求由严格 schema 明确拒绝，不保留 alias、deprecated
  warning 或接受后忽略。
- active chain 先用公共 resolver 确定 `active_time` 和 active statements：
  - 无 active statement：保持现有 `unresolved`/port-boundary 语义。
  - 多个 active assignments：返回 `ambiguous`，`termination_detail` 为
    `multiple_active_candidates`。
  - 唯一 active assignment 且存在多个 RHS signals：停止递归，返回
    `ambiguous`，`termination_detail` 为 `multiple_rhs_sources`。
  - 唯一且可由 `npiRhs` 明确解析为直接 signal：继续追踪。constant/root
    assignment 正常终止，不制造 ambiguous。
- ambiguous 时从每条 active statement 的 `sigHdlVec` 提取全部精确 RHS 路径，
  排除 LHS 并去重；多个 active assignments 按 statement 分组，禁止把不同 statement
  的 RHS 混成一个集合。
- 以该 hop 的精确 `active_time` 为唯一采样边界：
  - `before` 是严格早于 `active_time` 的最后值。
  - `after` 是 `active_time` 时刻的最终 FSDB 值。
  - 每项返回 value、known、status 和实际 value time；X/Z 保留原值并标记
    `known:false`，缺失信号或数值保留该行并报告状态。
- 对外新增 `data.ambiguity_evidence`，包含 ambiguity kind、active time、
  statement/file/line、完整 RHS samples、总数和完整性字段；XOUT 仅在
  ambiguous 时增加 RHS 前后值表。
- RHS 数量超过 `limits.max_trace_signals` 时明确返回不完整、遗漏数量及
  `truncation_scope=ambiguity_rhs_samples`，不得静默截断。
- 简化层必须保留该证据，response schema 关闭未知字段；同步 response example、
  response-fields、action reference 和 xdebug 架构说明。

## 4. 测试计划

- Contract：
  - 删除 `clk_period` 正例并增加 schema 拒绝负例。
  - 校验两种 ambiguity detail、严格 response shape、完整性和 XOUT 表格。
- 真实 NPI/FSDB：
  - phase5 `top.u_dut.dout[2] @ 10ns` 必须保持 active statement 为 `dut.sv:37`，
    chain 返回 `multiple_rhs_sources`，并返回
    `en1/src_a/ctrl_sel/ctrl_mode/src_b/src_c` 全部前后值。
  - 新增多个 active assignments 场景，验证按 statement 分组。
  - 覆盖 unchanged、changed、X/Z、missing value、same-timestamp final value 和 RHS
    数量截断。
  - 保持现有 4-hop direct chain、port boundary、zero-evidence、limit 和 loop 行为。
- 检查与门禁：
  - 运行三个 schema 同步检查、runtime compatibility audit、schema/examples validation。
  - 沙箱外运行 `xdebug.contract`、`xdebug.active_semantics`、
    `xdebug.active_zero_evidence`、`xdebug.active_trace.phase5`。
  - 运行 `skills.xverif` 与全仓 fast gate；需要重建 fixture 时只显式准备相关 fixture，
    不自动 prepare、不切换测试层级。

## 5. 验收与默认决策

- Goal 只有在源码、schema、examples、skill、架构文档和全部必需测试完成且
  worktree 经审计后才能标记 `complete`。
- `active_time` 是 RHS 证据的唯一 causal anchor；不围绕原始 requested time 返回
  第二套样本。
- `after` 定义为 `active_time` 时刻 FSDB 最终值，不承诺展示同时间戳内的中间
  delta/glitch。
- 新 RHS 值只解释 ambiguous，不参与自动选择下一跳。
- 本计划不默认包含 Git commit 或 push。

## 6. 实施结果

- 已删除 runtime、request schema、request example 和 handler 中的
  `args.clk_period`；strict schema 会拒绝旧参数。
- active chain 仅在 `npiRhs` 明确解析为直接 signal 时继续；多个 active
  assignments 和多个 RHS sources 分别返回已规划的 termination detail。
- `data.ambiguity_evidence` 已按 statement 分组，使用精确 `active_time` 返回
  before/after、value time、known/status/changed，以及完整性和截断字段；XOUT
  仅在 ambiguous 时增加表格。真实 fixture 已覆盖 changed/unchanged、X/Z、
  同时间戳最终值，以及 design 中存在但 FSDB 未记录的 RHS `signal_not_found`。
- 已同步 response schema/examples、action catalog、xverif skill references 和
  xdebug 架构说明，并安装验收 Codex/Claude skill 镜像。
- 已通过 schema/runtime/example 静态检查、C++ formatter unit、全仓 fast gate，
  以及 host 环境下的 `xdebug.contract`、`xdebug.active_semantics`、
  `xdebug.active_zero_evidence` 和 `xdebug.active_trace.phase5`。
