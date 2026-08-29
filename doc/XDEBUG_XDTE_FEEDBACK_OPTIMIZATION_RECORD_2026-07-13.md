# XDTE xdebug 使用反馈：待优化项记录

日期：2026-07-13
状态：待评审，尚未开始实现

## 1. 背景与问题来源

XDTE 项目在真实 RTL、UVM/RM、SVT AXI monitor 和 FSDB 联合调试中持续使用
xdebug。反馈原文位于
`<xdte-repo>/doc/xdebug_feedback.md`。

这不是一次仅基于 API 文档的假设性 review。该反馈覆盖了 COPY/FILL/XOR/CRC
集成回归、灰盒 RM checkpoint、AXI 五通道 monitor、Request/Completion/Credit
闭环以及多个 S0 模块冒烟。已确认 xdebug 的以下能力对定位问题有效：

- `scope.roots` / `scope.list` 能确认真实层次和 probe 是否进入 FSDB；
- `event.find`、`value.batch_at` 和 `handshake.inspect` 能把协议事件、状态现场和
  统计放到同一时间窗口；
- `trace.active_driver` / `trace.active_driver_chain` 能在可解析的 RTL net 上给出
  有效源码定位；
- 显式 `session.close`、`session.list`、`session.gc` 的生命周期合同工作正常，
  并避免了会话或进程残留；
- `session.doctor` 的资源变化诊断已经帮助使用者避免误用重编前数据库。

因此本记录不建议为了“功能更多”新增重叠 action，而聚焦把已使用能力的证据
可信度、参数合同和结果可读性提升到可以稳定支持 agent 自动判读的程度。

## 2. 已核验的当前实现边界

以下结论已对照当前 xdebug 源码、schema 和 skill，而不是只转述 XDTE 反馈：

1. `handshake.inspect` 会对每个 `ready=1 && valid=0` 的采样周期附加
   `ready_without_valid`、`info` finding；同时已经在 summary 中保留
   `ready_without_valid_cycles` 计数。
2. `value.at` 和 `value.batch_at` 的公开 schema 都接受 `d`、`dec`、`decimal`，
   但 XDTE 实测 `value.batch_at format=dec` 仍显示十六进制，需以 host FSDB 回归
   复现并修正或收紧合同。
3. 多个 clock-sampling action 的 schema 描述了 `sample_point` 只适用于
   `posedge/dual`，但 JSON Schema 目前没有表达该跨字段条件；错误要等 runtime
   才发现。
4. active trace 同时返回查询时刻 `time` 和 driver 最近生效/变化时刻
   `active_time`，但没有机器可读的字段语义说明；`unresolved` 和 `ambiguous`
   的限制文本也不足以区分 HDL 无证据、instance port alias、优化可见性和
   class/virtual-interface procedural write。
5. session 内部和 `session.open` 返回中已有 FSDB 的 `mtime`、`size`、`dev`、
   `inode`，并在会话运行中检测资源改变。它们能检测“打开后文件变化”，但不能
   证明一个路径下的波形就是刚结束的仿真 run，也不能从文件属性可靠判断 FSDB
   是否已完整写完。
6. `value.at` 对 `format:array_indexed` 明确返回 `unsupported_format`；XDTE 对
   unpacked array element 的 `value.batch_at` 则得到 `signal_not_found`。这说明
   聚合/数组能力尚未形成一致的公开合同。

## 3. 2026-07-13 本地 tmp 复现结果

复现包位于仓库本地、Git 忽略的
`tmp/xdebug_xdte_feedback_repro/`。它使用隔离 `HOME`，只读取已发布的
`xdebug.ai_complex_wave` 和 `xdebug.active_driver` fixture；所有 response、临时
FSDB 副本和 session 日志均保留在该 tmp 目录。真实 NPI/FSDB 请求已在沙箱外执行。

| 项目 | 观察结果 | 结论 |
| --- | --- | --- |
| `handshake.inspect` idle finding | 在 0--210ns 小窗口中出现 9 个 `ready_without_valid`，`line_limit=4` 仅返回 4 个；`analysis_complete=true` 且 `truncation_scope=response_findings`。 | 逐周期合法 idle 会消耗 finding 预算，P0 降噪成立。 |
| `format:dec` | `value.at` 和 `value.batch_at` 查询 `8'h22` 均返回 `'h22`。 | 公开 decimal 参数未反映在用户可见值，P0 合同问题已实测确认。 |
| `negedge + sample_point` | `event.find` request schema 验证通过；同一请求 runtime 返回 `INVALID_ARGUMENT`，说明 `sample_point` 只能用于 posedge/dual。 | 需把跨字段约束前置到 schema，P1 成立。 |
| active trace 时间 | 查询 `active_driver_tb.u_dut.q@20ns` 成功，summary 同时给出 `time=20ns`、`active_time=15ns`，无字段语义解释。 | `active_time` 的歧义可最小复现，P1 成立。 |
| FSDB 打开失败/资源快照 | `session.doctor` 返回 `fsdb_mtime/size/dev/inode`；对仅在 tmp 中截断的 FSDB，`session.open` 只返回 `SESSION_UNHEALTHY: child_exited`。 | 现有快照不等于 run provenance，且 native open 失败没有可诊断分类，P1 成立。 |
| aggregate/array | `format:array_indexed` 用在 scalar 时返回 `unsupported_format`；packed scalar 的 `sig_a[0]` 可读取。 | 已证明公开 aggregate format 的边界；本 fixture 不含 unpacked array，尚不能替代 XDTE 的 `done_bitmap[0]` 复现，必须新增专用 host fixture。 |

复现命令为：

```bash
python3 tmp/xdebug_xdte_feedback_repro/reproduce.py
```

该命令不是正式 catalog suite，不能替代未来实现后的回归；它用于保存当前缺口的
可重复观察证据。它不会自动重试、重开 session、切换 transport 或改用其它数据源。

## 4. 待优化项

### P0：`handshake.inspect` 的合法 idle 降噪

**触发背景**：在 XDTE 的 100-request COPY 回归中，Completion 和 Request Credit
分别产生 8993、9685 条 `ready_without_valid` info finding。完整扫描仍为
`analysis_complete=true`，但 finding 返回被截断，容易让 agent 错误地将
response 截断理解成分析未完成。

**现状问题**：合法的 downstream ready idle 不应与 stall 超阈值、data stability
violation 等需要处置的 finding 争用默认返回预算。

**建议合同**：

- 保留 `summary.ready_without_valid_cycles`；
- 增加显式的 reporting 模式，例如 `rules.ready_without_valid: "summary" |
  "intervals" | "all"`，默认 `summary`；
- `intervals` 只返回连续 idle 区间的 begin/end/cycle_count，`all` 才返回逐周期
  finding；
- `truncated` 必须继续精确说明是 response finding 截断，而非 scan/analysis
  截断。

**验收**：长 idle 的真实/合成波形下，transfer、stall、stability 和
`ready_without_valid_cycles` 不变；默认 response 不会因合法 idle 被截断；
`all` 模式保持与当前逐周期结果兼容。

### P0：value `format` 公开合同一致性

**触发背景**：XDTE 的 RM monitor 调试中使用 `value.batch_at format=dec`，得到的
显示仍为十六进制。参数已在 schema 和 runtime 允许值中公开，不能形成“接受但
看起来未生效”的接口。

**建议合同**：先在 host 上以最小 FSDB fixture 固化 `h/b/d` 的期望输出。若产品
继续承诺十进制，则 value object 的用户可见 `value`/rendered representation 必须
按请求 format 输出且保留 X/Z 的明确语义；若统一值输出只能是 canonical hex，
则应从公开 schema、registry 和 skill 中删除 `dec`，不要静默忽略。

**验收**：`value.at` 与 `value.batch_at` 对同一已知值的 format 行为一致；CLI、
MCP 和 SDK-free loop 的 response 字段一致；未知值的行为有明确测试。

### P1：把 sampling 跨字段约束前置到 schema

**触发背景**：XDTE 已多次遇到 `negedge + sample_point` 被拒绝，以及不同 action
将时间窗口、clock 参数和 limits 放在不同位置导致一次无效调用。

**建议合同**：

- 对所有使用统一 clock sampling 的 action，在 JSON Schema 加入条件：存在
  `sample_point` 时，`edge` 必须显式为 `posedge` 或 `dual`；
- 将相同约束同步到 runtime action schema、checked-in examples 和 skill；
- 对确实具有不同语义的 action（例如 active trace 的 `clk_period`、top-level
  `limits.max_depth`），在 action-specific schema 增加显眼的 contract note，而
  不是假装它们可以共用 waveform sampling 参数。

**验收**：纯 schema/contract 测试在不启动 NPI 的情况下拒绝非法组合；合法
`posedge/dual` 示例保持通过；runtime 错误继续提供 `correct_example`。

### P1：active trace 的时间语义、证据范围和不确定性分类

**触发背景**：XDTE 中 `active_time=0ns` 曾被误读为查询时刻；对 RTL 接口 net 能
定位源码，而 UVM class 经 virtual interface 写入的 debug mirror 得到
`unresolved`；某些 DUT instance port 在波形中为 X，但更上层接口和 SVT monitor
显示事务完整发生。

**建议合同**：

- 保持兼容地保留 `active_time`，同时新增语义明确的
  `driver_last_change_time` 和 `time_semantics`；
- 将 termination/limitation 细分为至少 `no_hdl_driver_evidence`、
  `port_alias_or_optimized_visibility`、`ambiguous_candidates`、`trace_limit`；
- 对 instance port、alias 或未知值增加 `evidence_scope`/`confidence` 提示，明确
  该 action 的证据不能覆盖 monitor、scoreboard 或结构化 RM 日志；
- 不承诺仅凭 NPI 就能追溯 class 到 virtual interface 的 procedural write。若底层
  数据库没有该证据，应明确报告“不可解析”，而不是伪造 driver 链。

**验收**：现有 active-driver fixture 回归保持；补充 port alias、unknown value 和
无 HDL driver evidence 的 deterministic response 测试。涉及真实 daidir/FSDB/NPI
的 case 在沙箱外运行。

### P1：FSDB provenance、完整性和打开失败诊断

**触发背景**：XDTE 曾在仿真命令返回后过早打开仍在增长的 FSDB；也曾因为 run 未
清理旧 `waves.fsdb*` 而读取旧波形。复制主 FSDB 未复制 sidecar 时仅得到
`child_exited`，无法判断问题属于缺 sidecar、NPI open 失败还是进程异常。

**边界澄清**：单靠 `mtime/size/inode` 或内容 fingerprint 不能证明 FSDB 与某一份
log/seed/run 对应，也不应靠固定 sleep、静默重试或自动改用其它数据源“修复”它。
完整性必须由仿真产物发布方提供明确合同，例如原子发布、completion manifest 或
run metadata。

**建议合同**：

- `session.open` 和 `session.doctor` 输出结构化 resource snapshot（canonical
  path、mtime、size、inode、open timestamp）；
- 若调用方提供 run manifest，xdebug 只做显式校验并报告匹配/不匹配，不自行猜测
  或 fallback；
- session open 失败时保留经过脱敏和长度限制的 NPI/native open 错误摘要，使
  `child_exited` 可区分为资源缺失、FSDB open 失败或 server 启动失败；
- sidecar 的存在与命名规则必须先通过 NPI/VCS 实机验证，不能根据 `.chain`、
  `.slist` 等个案硬编码通配规则。

**验收**：覆盖资源在 open 后变化、manifest 显式不匹配、NPI open 失败的错误形状；
真实 FSDB/NPI 用例及缺 sidecar 诊断均在沙箱外运行。

### P1：数组/aggregate 查询的明确能力边界

**触发背景**：XDTE 的 `done_bitmap[0]` 在 batch 查询中报告 `signal_not_found`，
而公开 schema 同时列出了 `array_indexed` format。使用者无法判断是路径语法、
FSDB 缺失、NPI 不支持，还是 xdebug 尚未实现。

**建议合同**：

- 在未实现前，让 `value.at` 与 `value.batch_at` 一致返回明确的
  `UNSUPPORTED_AGGREGATE_QUERY`（或从两者 schema 中移除该选项）；
- 用一个带 packed struct、unpacked array 和 indexed element 的真实 FSDB fixture
  调查 NPI 可枚举的 canonical path；
- 只有确认可稳定读取后，才实现 path normalization、`scope.list` 可查询路径提示
  与 `array_indexed` 输出。不得把错误路径静默改写成猜测路径。

**验收**：三类失败（不存在、存在但不支持、可读取）有可区分 error/status；若能力
落地，索引元素和 aggregate response 需有 host regression。

### P2：skill 的证据纪律补充

当前 xverif skill 已要求先 scope 发现、不要把 aggregate knownness 当最终结论，并
要求 response truncated 时缩小查询。仍建议追加：

- FSDB 结论前检查其 run provenance；有 log/monitor 冲突时，不以单一波形 port
  值覆盖独立事实；
- `handshake.inspect` 优先读 summary 的 transfer/stall/stability，只有需要逐点
  定位时才请求详细 idle finding；
- active trace 的 `unresolved`/`ambiguous` 是证据不足，不是“无驱动”或“功能未
  发生”；
- bind/interface probe 先用 `scope.list` 确认实例路径，不猜测 `global_if` 根层级。

这部分应与上述 API 行为同步提交，避免文档先承诺尚未实现的诊断。

## 5. 推荐实施顺序

1. P0：握手 idle 降噪、value format 合同，并补各自的最小回归。
2. P1：sampling schema 条件、active trace 结果语义/分类。
3. P1：FSDB resource snapshot、manifest 校验入口与 native open 错误诊断。
4. P1/P2：先完成 unpacked-array NPI 可行性 fixture，再决定公开 API 形状。
5. 最后同步 xdebug 架构说明、xverif skill、生成的 schema/action 文档和 MCP
   surface；按仓库 catalog 执行相关 suite。

## 6. 验证与环境约束

- JSON Schema、registry、文档链接和静态 contract 检查可以在沙箱内运行；
- 任何会启动 xdebug engine、访问真实 FSDB/NPI/Verdi 或 VCS fixture 的测试必须
  在沙箱外运行；
- 不以沙箱内的 engine/FSDB 失败判断产品回归；
- 不引入自动 reopen、自动 transport 切换、自动数据源切换或隐藏的 retry。

## 7. 本记录的非目标

- 不把 XDTE 的 RM、SVT monitor 或具体协议逻辑迁入 xdebug；
- 不将 monitor/log/scoreboard 的功能结论替换为单一波形观察；
- 不为已存在的 `event.find`、`value.batch_at`、`handshake.inspect`、active trace
  另建重叠 action；
- 不在尚未验证 NPI/FSDB 支持前承诺 class procedural write 或 unpacked-array
  trace 能力。
