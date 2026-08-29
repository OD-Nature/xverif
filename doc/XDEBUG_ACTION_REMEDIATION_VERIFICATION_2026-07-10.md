# xdebug 全 action 修复后验收报告（2026-07-10）

## 1. 验收口径

本报告对应 `XDEBUG_ACTION_REMEDIATION_PLAN_2026-07-10_10-54-25.md`。验收不调用仓库的 70-action replay runner，也不把 schema-only 或 fake backend 冒充真实 runtime。

每个 public action 必须同时满足：

- ActionRegistry、action spec、request/response schema 和 request/response example 均存在且一致。
- 原始逐 action 审计已经覆盖 CLI 与 MCP 的正确请求、schema 失败和 handler 失败；无法自然构造 handler 失败的只读 list action 在原报告中明确标注。
- 修复后由 contract、unit、synthetic existing、VIP、active semantics 或 session/MCP 回归覆盖相应公共 helper 和真实 handler。
- public frontend 不再修改 backend JSON 来按值删除 summary/data；各 handler 从事实源构造投影。XOUT renderer 只负责展示选择，错误保留 code/layer/invalid_arg/expected/correct_example 等可调试字段。

公共门禁结果：70 个 non-removed action、70 份 request schema、70 份 response schema、70 份基本 request example 和至少 70 份 response example 全部存在；本轮识别出的通用占位 response 已全部替换为 action-specific 证据形状。

## 2. 逐 action 结论

下表中的“通过”表示该 action 已满足上述静态合同与所属 runtime 回归门禁；不是只检查文件存在。

| Action | 类别 | 结论 | 主要修复后证据 |
| --- | --- | --- | --- |
| `actions` | builtin | 通过 | compact names/verbose descriptors、无 implemented 重复、contract |
| `apb.config.list` | waveform | 通过 | protocol 手工 CLI/MCP 三场景、schema/example、synthetic |
| `apb.config.load` | waveform | 通过 | effective config、protocol 手工 CLI/MCP、APB fixture |
| `apb.cursor` | waveform | 通过 | 标准 time/transaction、protocol 手工 CLI/MCP、APB fixture |
| `apb.query` | waveform | 通过 | effective direction/address、protocol 手工 CLI/MCP、APB fixture |
| `apb.transfer_window` | waveform | 通过 | scan/window/count、protocol 手工 CLI/MCP、APB fixture |
| `axi.analysis` | waveform | 通过 | latency min/avg/max/p50/p95/p99/slowest、synthetic existing |
| `axi.export` | waveform | 通过 | protocol 手工 CLI/MCP、export schema/example |
| `axi.channel_stall` | waveform | 通过 | effective config/sample semantics、protocol 与 synthetic |
| `axi.config.list` | waveform | 通过 | protocol 手工 CLI/MCP 三场景、schema/example |
| `axi.config.load` | waveform | 通过 | effective config、protocol 手工 CLI/MCP、AXI fixture |
| `axi.cursor` | waveform | 通过 | 1-based index/标准 time/latency、protocol 与 synthetic |
| `axi.latency_outlier` | waveform | 通过 | compact transaction anchor、protocol 与 synthetic |
| `axi.outstanding_timeline` | waveform | 通过 | analyzer 全量聚合、peak/change points、synthetic |
| `axi.query` | waveform | 通过 | compact 默认无 beat data、verbose 展开、synthetic |
| `axi.request_response_pair` | waveform | 通过 | compact 配对根因字段、protocol 与 synthetic |
| `batch` | builtin | 通过 | failed count/index/code/layer JSON/XOUT parity、contract |
| `counter.statistics` | waveform | 通过 | 手工 CLI/MCP 三场景、clock sampling/static/synthetic |
| `cursor.delete` | waveform | 通过 | 手工 CLI/MCP 三场景、cursor 状态与 response example |
| `cursor.get` | waveform | 通过 | 手工 CLI/MCP 三场景、cursor 状态与 response example |
| `cursor.list` | waveform | 通过 | 手工 CLI/MCP 正确/schema 场景、compact list contract |
| `cursor.set` | waveform | 通过 | 有效 TimeSpec example、手工 CLI/MCP、synthetic |
| `cursor.use` | waveform | 通过 | 手工 CLI/MCP 三场景、active cursor contract |
| `detect_abnormal` | waveform | 通过 | X/Z evidence、手工 CLI/MCP 三场景、synthetic |
| `event.config.list` | waveform | 通过 | 手工 CLI/MCP 三场景、sampling config response |
| `event.config.load` | waveform | 通过 | effective sampling config、手工 CLI/MCP、synthetic |
| `event.export` | waveform | 通过 | rows/aggregate/output、手工 CLI/MCP、synthetic |
| `event.find` | waveform | 通过 | standard time/match evidence、手工 CLI/MCP、synthetic |
| `expr.eval_at` | waveform | 通过 | operand/bracket/sample context、手工 CLI/MCP、synthetic |
| `expr.normalize` | design | 通过 | syntax validation、手工 CLI/MCP 三场景、contract |
| `handshake.inspect` | waveform | 通过 | scan range/count/stall evidence、手工 CLI/MCP、synthetic |
| `list.add` | waveform | 通过 | one-based list semantics、手工 CLI/MCP、synthetic |
| `list.create` | waveform | 通过 | resolved signals/status、手工 CLI/MCP、synthetic |
| `list.delete` | waveform | 通过 | index/name evidence、手工 CLI/MCP、synthetic |
| `list.diff` | waveform | 通过 | point-sampled delta contract、手工 CLI/MCP、synthetic |
| `list.export` | waveform | 通过 | manifest/files/scan metadata、手工 CLI/MCP、synthetic |
| `list.show` | waveform | 通过 | compact list/index contract、手工 CLI/MCP、synthetic |
| `list.validate` | waveform | 通过 | missing/invalid path evidence、手工 CLI/MCP、synthetic |
| `list.value_at` | waveform | 通过 | point sampling/no config echo、手工 CLI/MCP、synthetic |
| `sampled_pulse.inspect` | waveform | 通过 | full analysis independent of response limit、synthetic |
| `schema` | builtin | 通过 | checked-in exact schema、unknown action nearby suggestions |
| `scope.list` | waveform | 通过 | shared resolver/resource errors、手工 CLI/MCP、synthetic |
| `scope.roots` | waveform | 通过 | resource/not-found distinction、手工 CLI/MCP、synthetic |
| `session.close` | session | 通过 | native 单 session backend cleanup、失败保留 registry record、session fixture |
| `session.doctor` | session | 通过 | native health/resource-change 诊断、session fixture |
| `session.gc` | session | 通过 | native expiry/unhealthy 扫描与清理结果、session fixture |
| `session.kill` | session | 通过 | native 单 session 与显式 `all` cleanup 合同、session fixture |
| `session.list` | session | 通过 | native registry records 与 expired cleanup summary、session fixture |
| `session.open` | session | 通过 | native engine open/record/resource ownership、session fixture |
| `signal.canonicalize` | design | 通过 | shared design resolver、手工 CLI/MCP 三场景、contract |
| `signal.changes` | waveform | 通过 | actual transition semantics/rows/scan metadata、synthetic |
| `signal.resolve` | design | 通过 | not-found/ambiguous distinction、shared resolver tests |
| `signal.stability` | waveform | 通过 | initial/final/transition/stable evidence、synthetic |
| `signal.statistics` | waveform | 通过 | clock/raw mode、full-width values、synthetic |
| `source.context` | design | 通过 | compact/verbose schema、source window/error contract |
| `trace.active_driver` | combined | 通过 | internal fire/driver evidence、active semantics fixture |
| `trace.active_driver_chain` | combined | 通过 | chain evidence/limits、active semantics fixture |
| `trace.driver` | design | 通过 | signal existence vs no-driver、source evidence、contract |
| `trace.load` | design | 通过 | signal existence vs no-load、path evidence、contract |
| `rc.generate` | waveform | 通过 | resolved signal/marker/export evidence、synthetic |
| `value.at` | waveform | 通过 | compact point value/requested edge fields、synthetic |
| `value.batch_at` | waveform | 通过 | per-signal status/missing reasons/bracket evidence、synthetic |
| `verify.conditions` | waveform | 通过 | standard time/condition evidence、synthetic |
| `window.verify` | waveform | 通过 | sampled count/failure/unknown/condition evidence、synthetic |
| `stream.config.load` | waveform | 通过 | effective config/issues、protocol 手工 CLI/MCP |
| `stream.config.list` | waveform | 通过 | compact config discovery、protocol 手工 CLI/MCP |
| `stream.show` | waveform | 通过 | config/semantics/issues、protocol 手工 CLI/MCP |
| `stream.validate` | waveform | 通过 | scanned range/dynamic issues、protocol 手工 CLI/MCP |
| `stream.query` | waveform | 通过 | scan count/truncation/row evidence、protocol 手工 CLI/MCP |
| `stream.export` | waveform | 通过 | output status/row count/scan metadata、protocol 手工 CLI/MCP |

## 3. MCP 生命周期附加验收

- MCP SDK 和 SDK-free wrapper 均提供 debug/cov open/list/doctor/close/kill/gc。
- coverage query 拒绝 native `session.open/status/close` 及其它 lifecycle action，并给出 coverage 专用正确示例。
- xdebug 与 xcov public tool 语义对称，native capability 不对称：xdebug 支持 fixed admin doctor/kill/gc；xcov kill 仅终止 managed loop/process/job。
- direct、fake LSF、SDK、SDK-free、dead loop、native close failure、partial cleanup、tombstone 和 gc 定向回归通过；最终全仓库门禁见第 4 节。
- 用户确认前曾调用 real-LSF test target，但在 launcher 查找/执行 `bsub` 阶段即失败，未提交任何真实 LSF job。用户随后明确本机无 LSF、不得运行 real LSF；最终门禁因此把 real LSF 记录为 NOT RUN，未再调用该 target，未切换 fake LSF，也未把 fake LSF 记作 real LSF 通过。

## 4. 最终门禁

最终门禁在 commit `9eeb2bf` 后的当前 HEAD 执行，结果如下：

- `env -u XDEBUG_ENABLE_REAL_LSF make full-test`：PASS。`regression/run_full_regression.sh` 的 `build_all` 阶段执行 `make clean all`，因此该结果来自 clean rebuild；汇总为 PASS 9、SKIP 1、FAIL 0，日志位于 `<repo>/tmp/xdebug_full_regression_20260710_222407/summary.txt`。
- `realdata_system_wave`：SKIP。原因是可选的 `<optional-wave-fixture>/waves.fsdb` fixture 不存在；其它 build、unit、active-driver、API/combined、design semantics、waveform complex/event 和 realdata AXI 阶段均通过。
- `env -u XDEBUG_ENABLE_REAL_LSF make test`：PASS。覆盖 152 个 schema、145 个 examples、71 个 action spec/runtime 合同、C++ unit、MCP action 163/163、xbit 19、xentry 14、xloc 13、xcov 45、xwaveform 5，以及 VCS active-driver 回归。
- `env -u XDEBUG_ENABLE_REAL_LSF make -C xdebug test-nightly`：PASS。infra 13、contract 65、synthetic existing 3、counter 1、active semantics 1、session 27、MCP direct 4、fake LSF 3、realdata 1、AXI VIP 1、APB VIP 1 全部通过。
- real LSF：NOT RUN。用户确认本机无 LSF，并明确不得执行；`full-test`、`make test` 与 nightly 三个最终门禁命令均显式移除 `XDEBUG_ENABLE_REAL_LSF`，nightly 输出可选 real LSF skip。没有 fallback。
- APB VIP 定向复验：`make -C xdebug pytest-apb-vip`，1 passed。测试消费者已按公开合同读取 `data.config`，并使用 `direction=write|read`。

## 5. 提交与范围核对

本计划的实现提交从 `0796074` 到 `9eeb2bf`，按公共 error、信号/波形语义、protocol 响应、MCP 生命周期、文档/skill、回归消费者和公共截断投影分层提交。所有提交 subject/body 均为中文；测试修正没有改变产品 handler/schema，也没有加入兼容 fallback。

最终独立复审见第 6 节；复审通过后执行最终文档提交、工作树检查与 push。

## 6. 最终独立复审

### 6.1 总体结论

独立 agent 完成只读复审后，有条件同意交付：产品实现与测试证据支持核心结论，未发现需要修改产品代码或重跑 required 测试的阻断。复审要求修正的计划首页状态、cleanup/tombstone 示例和 real-LSF 历史/最终边界均已在本次文档收口中落实。

### 6.2 逐项核对

1. 验收表包含 70 个唯一 action，与 `xdebug/specs/actions/actions.yaml` 中 70 个 non-removed action 完全一致；request/response schema 与 basic request/response example 各 70 份，无缺项或多项。逐 action 的“通过”含义是静态合同加所属 runtime 回归通过，不夸大为最终门禁重新手工 replay；本任务始终未使用仓库 70-action replay runner。
2. `capabilities.py` 定义了 xdebug native doctor/kill/gc、fixed admin path 与 backend-survives-loop 能力，以及 xcov native status、无 native kill/gc、backend 随 loop 退出的差异；server 与 SDK-free wrapper 对称暴露 debug/cov open/list/doctor/close/kill/gc。coverage query guard 在 adapter 前禁止 native lifecycle action，并返回 coverage 专用示例。报告的“public 对称、backend capability 差异化、禁止绕过 manager”结论正确。
3. `LoopSession.close()` 同时检查 transport envelope 与 backend payload 的 `ok`；partial failure 返回 `SESSION_CLEANUP_PARTIAL_FAILURE`，manager 增加 `error_layer=session_manager` 并保留 unresolved tombstone。成功 close 的公开 cleanup 为 `backend_close`、`stdio_quit`、`terminate`、`manager_record=evicted`、`tombstone=retained_closed`，计划示例现已与实现一致。
4. `<repo>/tmp/xdebug_full_regression_20260710_222407/summary.txt` 明确为 PASS 9、SKIP 1、FAIL 0；`regression/run_full_regression.sh` 的 `build_all` 入口为 `make clean all`。唯一 SKIP 对应可选 system FSDB fixture。make test、nightly 与 APB 定向计数和实际 Makefile target/提交验证一致。
5. 复审时 HEAD 为 `9eeb2bf`，相对 `origin/master` ahead 14，工作树仅有两份本轮计划/验收文档；`git diff --check` 通过，范围符合文档收口阶段。

### 6.3 发现问题与处理

- 已修正计划首页“尚未开始源码实现”的过期状态。
- 已把 cleanup 成功示例改为真实字段，并明确成功 close 保留 closed tombstone、等待显式 gc。
- 已明确用户确认前 real-LSF target 在缺少 `bsub` 时即失败且未提交真实 job；用户确认后的最终门禁未再调用，状态为 NOT RUN、无 fallback。
- `<repo>/tmp` full-test 日志不是长期唯一证据；本报告已版本化保存关键阶段、计数、SKIP 原因和执行边界。

### 6.4 是否同意交付

上述三项文档问题修正后，独立 reviewer 同意完成文档提交、最终 clean status 检查并 push；没有产品级阻断。

## 7. 远端交付

- 分支：`master`
- 远端：`origin/master`
- 首轮交付推送：`0b4d649..25628ce`，成功
- 推送方式：普通 fast-forward push；未强推、未切换 remote 或 transport
- 本节与计划最终状态由后续文档状态提交记录，并在提交后再次推送与核对本地/远端一致性。
