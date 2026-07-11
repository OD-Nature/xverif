# xverif Skill 信息架构与 Debug Workflow 重构计划

## 启动与 Goal 规则

1. 实施前先将本计划写入本文件并核对 diff。
2. 计划落盘后创建 goal，再修改其他文件。
3. Goal 覆盖两个实施阶段、关联测试和 Codex/Claude skill 镜像同步。
4. 不允许因失败自动切换 surface、transport、backend、数据源或测试层级。

## 总体设计

将 `xverif-cli` 与 `xverif-mcp` 合并为唯一通用入口 `xverif`：

- `xverif`：能力路由和验证 workflow。
- `xverif-admin`：MCP、SDK-free、transport、LSF、timeout、session 运维。
- `x-npi`：批量 FSDB/VDB 扫描和定制分析。
- `xwiki`：持续知识查询及授权写回。
- `xeda-runner`：执行 make/VCS/simv/Verdi。

`xverif` 内部划分为 `core/`、`capabilities/`、`workflows/`、`surfaces/`、`generated/` 和 `specs/`。旧 `xverif-cli`、`xverif-mcp` 直接退场，不保留兼容壳。

## xdebug 主文件与全量 Action Reference

`capabilities/xdebug.md` 按一次完整 debug 流程组织，并明确：

- 主文件只承担高频 action 决策和推荐证据链。
- 每个流程阶段都提供到 `generated/xdebug-actions.md` 的进一步路由。
- 全量 action reference 覆盖 runtime registry 的全部 action，并包含用途、资源类型、适用时机、required inputs、关键限制、关联 workflow 以及 schema/example 位置。
- 精确参数以 runtime catalog、action-specific schema 和 checked-in example 为准。
- 主文件没有覆盖任务所需能力时，先查全量 action reference，不能猜参数或绕到低层工具。

## xdebug 标准 Debug 流程

### 1. 建立资源、Scope 和 Config

- 判断使用 `daidir`、`fsdb` 或 combined session。
- 使用 `scope.roots`、`scope.list` 确认 hierarchy、信号和最终 leaf path。
- 保存 clock、reset、valid、ready、data、payload leaf、state、counter、channel/id/opcode。
- packed struct/aggregate 必须落实到 leaf signal。
- 优先加载和复用项目已有 config。

### 2. 定位异常时间和现场

- `value.at`：已知时间，只检查一个信号。
- `value.batch_at`：已知时间，检查一组相关信号并保存现场。
- `signal.changes`：观察单信号在受限窗口内的变化。
- `signal.statistics`：观察活动率、变化次数和持续时间等统计。
- `event.find`：未知异常时间，寻找首次或下一次条件命中。
- `verify.conditions`：在单个时间点验证多项条件。
- `window.verify`：在 clock-edge 窗口内证明条件持续 pass、fail 或 unknown。

推荐顺序：`signal.statistics/changes` → `event.find` → `value.batch_at` → `verify.conditions/window.verify`。

### 3. 解释异常、采样和握手

- `detect_abnormal`：X/Z、glitch、异常短脉冲、stuck 等 raw waveform smoke。
- `sampled_pulse.inspect`：判断 raw valid pulse 是否被 clock edge 采样，并保留 payload 现场。
- `handshake.inspect`：解释 valid/ready、backpressure 和 stall。
- 合法 idle/backpressure 不能仅凭 stuck finding 判为 bug。

### 4. 从信号追到 RTL 根因

- `trace.driver`：静态查潜在驱动。
- `trace.load`：静态查消费位置和影响范围。
- `source.context`：取得候选 file:line 周围源码。
- `trace.active_driver`：结合 signal、time、daidir 和 fsdb，查当前生效 driver。
- `trace.active_driver_chain`：继续递归当前生效链；深度使用顶层 `limits.max_depth`。

标准因果链：`scope.list` → `trace.driver/load` → `source.context` → `event.find` → `value.batch_at` → `trace.active_driver` → 必要时 `trace.active_driver_chain` → 回查控制条件。必须区分 `resolved`、`control_only` 和 `unresolved`。

### 5. Stream 通用协议分析

`stream.*` 不局限于标准总线。凡是可表示为 `clock + vld + data + 可选 rdy/bp/sop/eop/channel_id`，均优先考虑 stream，包括 pipeline、FIFO、command/response、descriptor、packet、credit/backpressure 和自定义 valid-ready。

标准流程：`stream.config.load` → `stream.config.list` → `stream.query` → `value.batch_at` → `trace.active_driver` → `window.verify`。APB/AXI action 只在需要协议专属 transaction、channel 或 violation 语义时使用。

### 6. 宏观波形与多模态观察

需要观察长时间趋势、多信号关系、burst、stall 分布或状态阶段时：`list.create/list.add` → `list.export` → `xwaveform render` → 查看 JPG 和 stats JSON → 使用多模态观察宏观模式 → 回到确定性 action 验证。

图片用于提出假设，不作为唯一证据。`rc.generate` 用于交付可在 nWave 中复查的视图。

### 7. 保存和复用 Config

- `stream/event/APB/AXI config.load` 的稳定映射必须保存。
- 优先使用项目已有目录；无约定时建议使用 `xdebug/configs/` 和 `xdebug/signals.md`。
- 不保存临时 session id、临时 finding 或一次性输出路径。
- 保存后使用对应 `*.config.list` 验证。
- 当前任务未授权写项目文件时必须先询问，不得静默写到其他位置。
- xwiki 仅在获得授权时保存稳定项目知识。

## 第一阶段：公开合同与 Skill 迁移

- 修复 README 中已删除 aliases、raw tools、旧 session tools 和错误 `cov.holes`。
- 删除“按需 include”等模糊措辞。
- 缩短 MCP `INSTRUCTIONS`，详细教程迁入 skill。
- 建立五个目标 skill 和新的 xdebug debug 流程。
- 吸纳、去重现有 overview、recipes、examples、response fields、troubleshooting、transport 和 RC 内容。
- 建立覆盖全部 xdebug action 的生成索引。
- 补齐 xwaveform、多模态观察和 config 保存路由。
- 更新 README、Makefile、`agents/openai.yaml` 和测试 catalog。
- 安装时清理 Codex/Claude 中旧 skill，再安装新 skill。
- 新增 repo-wide public contract gate。

## 第二阶段：Canonical 生成与 MCP 接口统一

- `routing.yaml` 保存 capability/workflow 路由案例。
- `examples.yaml` 保存 surface 无关的 action、args 和证据意图。
- 生成全量 xdebug action reference、MCP tool index及三种 surface 示例。
- 生成器提供 `--check`，禁止 generated drift。
- 新增 routing golden、capability inventory、trigger collision、公开合同和禁用词测试。
- `xverif_cov_query(session, ...)` 改为 `session_id`；coverage 精确会话操作统一使用 `session_id`，不接受或映射旧 `session`。
- xdebug/xcov query 统一为 `session_id/action/args/limits/output_format`。

## 测试与验收

- 用 `skills.xverif`、`skills.xverif_admin`、`skills.xeda_runner` 替换旧 suites，保留并调整 `skills.x_npi`、`skills.xwiki`。
- 验证 xdebug 主文件覆盖 scope、driver、load、active driver、active chain、value/event/verify、诊断闭环、stream 泛用性、多模态观察和 config 保存。
- 确保全量索引与 runtime registry action 集合完全一致。
- 运行 focused skill suites、`pytest --xverif-gate fast --xverif-plan` 和 `pytest --xverif-gate fast`。
- 运行 MCP registration、schema、batch、session guard 和 SDK-free contract tests。
- 对 Codex/Claude 安装镜像逐 skill 执行 `diff -qr`，确认旧 skill 已删除。
- 真实 FSDB/NPI、MCP stdio-loop、LSF、VCS 或 license 验证整体在沙箱外执行。

## 已确定的假设

- 允许 breaking migration，不保留旧 skill 或旧 MCP `session`。
- xdebug 主文件提供高频决策闭环，全量 action reference 保证所有能力可发现。
- 主文件额外包含 `signal.changes`、`signal.statistics`、`detect_abnormal`、`sampled_pulse.inspect`、`handshake.inspect`、`source.context` 和 `rc.generate`。
- 图片只辅助宏观观察，确定性 action 结果仍是最终证据。
