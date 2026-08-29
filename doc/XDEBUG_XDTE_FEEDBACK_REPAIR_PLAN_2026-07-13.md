# xdebug XDTE 反馈修复计划

日期：2026-07-13
状态：已确认；实现必须以本文件为唯一执行基线

## 1. 目标与背景

XDTE 在真实 RTL、UVM/RM、SVT AXI monitor 与 FSDB 联合调试中验证了 xdebug 的
session、event、value、handshake 和 active trace 能力，同时暴露了六类公共合同
缺口：合法 idle finding 过量、信号值格式不一致、sampling 参数合同不统一、active
trace 证据语义不清、FSDB run 溯源与 native open 诊断不足、aggregate/unpacked-array
能力边界不明确。

本轮不新增重叠 action，不把 XDTE 的业务 checker 或 monitor 迁入 xdebug；目标是
增强现有 action 的可读性、证据边界和可验证公共合同。

## 2. 不影响现有 xdebug 使用者的硬门禁

另一个项目正在使用主检出 `<xverif-repo>` 的 xdebug。本修复只允许在：

```text
worktree: <repo>/tmp/xverif-xdebug-xdte-feedback
branch:   codex/xdebug-xdte-feedback
```

中执行。下列规则是每一阶段开始和结束时的门禁，不满足即停止该阶段：

1. 不修改主检出中的源码、Git 状态、`xdebug/xdebug`、`xdebug/build/`、
   `xdebug/libexec/`、`tools/xdebug` 或任何主检出 test output。
2. 不在主检出执行 build、`make clean`、fixture prepare、skill 安装、session kill/gc
   或会影响共享产物的命令。
3. worktree 自行编译，只调用其自身的 `tools/xdebug`；build、FSDB 副本、日志、UDS
   与 session 均放在该 worktree 的 `<repo>/tmp` 隔离目录。
4. 真实 host NPI/FSDB 查询使用隔离 `HOME`；不得读取、关闭或 GC 主用户
   `~/.xdebug` 下的任何 session。
5. fixture 只读消费已发布缓存。cache miss 直接报告阻塞，不自动编译、仿真、重试、
   切换 transport/backend/data source 或改写共享 fixture。
6. 不在未获额外授权时安装或替换全局 xdebug、Codex skill 或 Claude skill。

## 3. 计划书与 Goal 边界

本文件作为独立中文 Git commit 提交后创建实施 Goal。Goal 的完成条件是下列五个
原子修复提交均已完成、相应测试已通过、主检出仍未受影响，并给出每阶段的提交号和
host/sandbox 验证位置。

## 4. 五个原子修复提交

### 提交一：全局信号值格式组件

**公共合同**：

- 所有显示信号值的 action 新增 `args.value_format`，允许 `hex`、`bin`、`dec`。
- 仅影响信号值显示；不改变 export 的 `file_format`、协议分析格式、时间格式或任何
  数据处理逻辑。
- `value.at/value.batch_at` 已有的数值 `args.format` 保持兼容；若同时提供两个数值
  格式且归一化结果不同，返回明确参数错误。`array_indexed` 仍是 aggregate 专属选择，
  不与 `value_format` 混用。
- known value 按 `value_format` 显示。`dec` 遇到 X/Z 时必须返回 binary 保真值，并
  在 value object 中写明 `requested_value_format:"dec"`、
  `effective_value_format:"bin"` 与原因；不得静默转换。
- 通过一个共享渲染组件实现，避免 CLI、stdio-loop、engine handler、waveform、stream
  和 protocol action 各自转换。

**验证**：静态 schema/registry/example 检查；known hex/bin/dec、X/Z decimal、旧
`format` 兼容和冲突参数的 unit/contract 测试；真实 FSDB 的 CLI/MCP/loop 一致性测试。

### 提交二：握手降噪与 sampling 合同

**公共合同**：

- `handshake.inspect.rules.ready_without_valid` 固定为 `summary`、`intervals`、`all`，
  默认 `summary`。
- `summary` 只保留 `ready_without_valid_cycles`；`intervals` 返回连续合法 idle 的
  begin/end/cycle_count；`all` 保持逐周期 info finding 行为。
- 所有采用 clock sampling 的 action 与 config surface 都接受 `sample_point`。
- `edge:"negedge"` 与 `sample_point` 同时出现时请求成功、严格走原 negedge 采样路径。
  响应必须统一输出 requested/effective sampling：effective sampling 的
  `sample_point` 为 null、`sample_point_applied:false`，并标明该字段未参与采样。
- `truncated`/`truncation_scope` 继续区分 response finding 截断与扫描未完成。

**验证**：长 idle fixture 的 summary/interval/all 行为；transfer/stall/data stability
计数不变；所有 sampling action 的 schema/runtime requested-effective contract；真实
FSDB posedge/dual/negedge 回归。

### 提交三：active trace 时间与证据语义

**公共合同**：

- 保留 `active_time` 兼容字段，新增 `requested_time`、`driver_last_change_time`、
  `time_semantics`。
- 新增机器可读的 `evidence_scope` 与终止/限制分类，覆盖：无 HDL driver evidence、
  port alias 或优化可见性、候选歧义、循环、trace limit。
- 保留现有 `termination`、`driver_status`、`limitations`；新字段只增强解释，不改变
  当前证据选择算法。
- class/virtual-interface procedural write 没有底层 HDL/FSDB 证据时明确报告不可解析，
  不伪造 driver 链，也不以 trace 结果覆盖 monitor/scoreboard/RM 日志事实。

**验证**：现有 active-driver fixture；port alias、unknown value、无证据、歧义与
requested time/last-change time 的 deterministic response 测试；真实 combined
daidir+FSDB host 回归。

### 提交四：FSDB run manifest 与打开诊断

**公共合同**：

- `session.open.target.run_manifest` 为可选路径；CLI、MCP、loop session-open
  统一透传。
- 新增 `xdebug.run-manifest.v1`，最少包含：
  `schema_version`、`state:"published"`、相对 manifest 的 FSDB 路径、`size_bytes`、
  `sha256`；combined target 还包含 daidir 的同类声明。
- 未提供 manifest 时保持原 session.open 行为。提供 manifest 后，xdebug canonicalize
  资源路径并校验 published state、路径、size、SHA-256；任一不匹配返回
  `RESOURCE_PROVENANCE_MISMATCH`，不启动 engine。
- `session.open/session.doctor` 返回结构化 resource snapshot。native open 失败返回
  脱敏、长度受限的摘要，区分 manifest/resource/NPI open/server startup 错误；不采用
  固定 sleep、自动 reopen 或 fallback。
- fixture 生成增加 run manifest；旧 fixture manifest 不作为该新合同的隐式替代。

**验证**：无 manifest 兼容、有效 manifest、未发布状态、路径/size/hash 不匹配、
截断 FSDB、缺 sidecar 与 native open 错误形状；真实 NPI/FSDB cases 全部在 host。

### 提交五：aggregate 能力、skill 与收尾

**公共合同**：

- 新建隔离 host fixture，覆盖 packed struct、unpacked array、合法 indexed element、
  不存在 element 和 aggregate 根。
- 先以该 fixture 固化 NPI 的 canonical path 与可读性。只有全部目标 element 可稳定
  解析时，才实现受限的 path normalization 与 `array_indexed` 输出。
- 若 NPI 不满足稳定读取条件，`value.at/value.batch_at` 统一返回
  `UNSUPPORTED_AGGREGATE_QUERY`，区分路径不存在、aggregate 不支持和可读值；不得猜测
  或重写用户路径。
- 同步 xdebug 架构说明、schema/examples、xverif skill 与生成索引：全局 value format、
  effective sampling、trace evidence boundary、run manifest 与 aggregate 限制。

**验证**：NPI capability fixture、成功/失败路径、host waveform regression；各 skill
catalog 的 Markdown 链接、可复制 JSON、action/tool 覆盖检查。

## 5. 通用验证与交付规则

- 每个提交前运行相关静态 gate 和 diff check；源码变更的测试必须来自当前 catalog、
  pytest 配置或脚本。
- NPI、FSDB、VCS、VIP 和真实 daidir 用例在沙箱外执行；沙箱内失败不作为产品回归。
- 每个原子提交都同步受影响 schema、examples、README/架构说明和 skill，不把公共
  参数接受后静默忽略。
- Git commit 使用详细中文信息，写明动机、范围、隔离执行位置和验证结果；提交前只
  stage 本阶段文件并确认 worktree `git status --short`。
