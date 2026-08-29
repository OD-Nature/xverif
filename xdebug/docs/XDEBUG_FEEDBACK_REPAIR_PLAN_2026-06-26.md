# xdebug feedback 修正方案 2026-06-26

## 范围

本文基于 `<xring-repo>/dv/doc/feedback` 下全部 Markdown 文档，以及对
`2026-06-16-xdebug-full-xout-complete.md` 中真实 compact xout 输出的补充阅读。

这些反馈说明：xdebug 的核心 RTL 和波形事实总体是正确的。已核对通过的能力包括
`trace.active_driver`、`trace.driver`、`signal.resolve`、`source.context`、
`signal.statistics`、`signal.stability` 和 `event.find`。因此第一轮修正不应该重写
driver、BFS 或波形分析引擎，而应该优先修复输出呈现、交互契约和错误诊断质量。

## 反馈证据

已阅读的反馈文档：

- `2026-06-16-xdebug-final-assessment-report.md`
- `2026-06-16-xdebug-full-action-xout-dump.md`
- `2026-06-16-xdebug-full-coverage-report.md`
- `2026-06-16-xdebug-full-xout-complete.md`
- `2026-06-16-xdebug-xout-redundancy-review.md`

主要问题：

- compact xout 输出冗余严重：重复 `summary`、`data` 重复 `summary`、edge/event/check/rule
  块重复，以及大量低价值空字段。
- action 参数命名不一致：`signal`/`path`、`clock`/`clk`、`begin/end`/`from/to`、
  `requested_time`/`time`、`valid`/`vld`、`ready`/`rdy`。
- MCP xdebug 查询每次都要求显式传 `session`；反馈期望 `xverif_debug_session_open`
  后自动成为默认 session。
- APB/AXI/Stream 协议配置可用，但模板和缺字段诊断不够清晰。

从真实 xout dump 追加发现的问题：

- `trace.active_driver_chain` 把很长的多行解释文本同时放进 `summary.text` 和
  `data.text`，比普通标量重复更影响首屏阅读。
- `trace expansion view` 和 `trace graph view` 同时输出 graph `edges` 与 `trace.dependency_edges`，
  其中还包含很长的 `source` 表达式和绝对源码路径。
- `list.create`、`list.add`、`list.diff`、`list.validate`、`list.export`、`list.delete`
  也存在 summary/data 重复，短版冗余报告里没有充分强调。
- `session.doctor` 输出完整嵌套 health envelope，然后又重复输出第二份 summary/health；
  compact 模式应该像健康面板，而不是原始 envelope dump。
- `apb.cursor` 和协议窗口类 action 的 transaction 数据有价值，但当前通用 renderer
  把 summary 标量重复和 transaction 细节混在一起。
- `list.value_at` 输出两次 `target.time`，说明专用 renderer 也需要确定性的重复键抑制。

## 当前代码根因

冗余不是单个 action 的孤立问题，而是结构性问题。

- `xdebug/src/engine/server.cpp` 从 handler 返回的 `data` 构造 `xout_resp`，并把
  `data.summary` 额外提升成 response `summary` 后再渲染。
- `xdebug/src/engine/service/engine_action_handler.cpp` 的默认渲染逻辑会先输出
  `summary`，再递归输出整个 `data` 对象。
- `xdebug/src/api/xout_renderer.cpp` 对非 engine 或 fallback response 也有类似的
  `summary + data` 通用渲染模型。
- 多个 handler 为兼容 JSON 契约保留了同义字段，例如 `event.find/export` 同时保留
  `events` 和 `examples`，`verify.conditions` 同时保留 `checks` 和 `results`。
- MCP session manager 在缺少 `session` 时直接拒绝查询；`xverif_debug_query` 的
  Python 签名也把 `session` 设为必传。

## P0：源头消除冗余输出

目标：不新增渲染 helper，不靠后置屏蔽或 fallback，从 handler 和 envelope 源头停止生成已确认的冗余内容。

实现策略：

1. 不增加新的 compact 投影 helper。
2. 不把旧字段保留下来再让 renderer 隐藏。
3. handler 不再返回 `data.summary` 这类嵌套 summary。
4. handler 不再生成同义数组或重复别名，例如 `events/examples`、`checks/results`、
   `signals/signals_preview`。
5. 简单 list CRUD action 直接返回必要标量和结果对象，不再同时构造一份 summary object。
6. `trace.active_driver_chain` 不再把长链路文本塞进 JSON payload；链路事实保留结构化
   `chain`。
7. 错误响应 envelope 与成功响应使用同一源头规则：从 handler 顶层标量生成 public
   `summary`，不要求 handler 为错误路径额外生成嵌套 `summary`。

action 级源头规则：

| 范围 | 当前现象 | 修正规则 |
| --- | --- | --- |
| `event.find`、`event.export` | `events` 和 `examples` 内容相同 | handler 只生成 `events` |
| `verify.conditions` | `checks` 和 `results` 完全相同 | handler 只生成 `checks` |
| `scope.list` | `signals` 和 `signals_preview` 完全相同 | handler 只生成 `signals` |
| `trace expansion view`、`trace graph view`、`trace explanation view` | handler 返回嵌套 `summary` 后又被 envelope 提升 | handler 返回顶层标量，由 envelope 生成 public summary |
| `trace.active_driver_chain` | 长 `text` 同时出现在 summary 和 data | 删除 JSON 中的长文本副本，只保留结构化 chain |
| `list.*` | 简单 CRUD action 出现嵌套 `summary` 和同义字段 | handler 直接返回必要字段；删除 `data.summary`、重复 `time/count` |

验收标准：

- 真实输出中不能出现 `data.examples`、`data.results`、`data.signals_preview`。
- list action 真实输出中不能出现嵌套 `data.summary`，`list.diff` 不能同时返回 `time`
  和 `diff_time`。
- `trace.active_driver_chain` 真实输出中不能出现 `data.text` 或 `data.chain.text`。
- 错误路径仍然必须保留 public `summary`，例如 `trace expansion view` 的
  `failed_query_count`。

## P0：直接失败式测试

测试不做中间转换，不把输出映射成另一种格式再判断，而是直接读取真实 JSON 字段。

已落地或应保持的测试：

- `xdebug/tests/waveform/run_complex_wave.py` 对真实 `scope.list`、`event.find/export`、
  `verify.conditions`、`list.*` 输出做字段级断言。
- `xdebug/tests/combined/test_active_semantics.py` 和
  `xdebug/tests/combined/test_active_zero_evidence.py` 对真实
  `trace.active_driver_chain` 输出断言不存在 `text` 副本。
- `xdebug/tests/contract/test_action_contract.py` 对 checked-in response examples 做
  冗余字段禁用检查，防止文档合同把旧形态带回来。

第一层验证：

```bash
make -C xdebug schema-test
make -C xdebug contract-test
make -C xdebug unit-test
```

涉及 license、NPI、LSF、MCP 进程通信或真实 FSDB 的 smoke，按要求放到沙箱外执行。

## P1：参数别名归一

目标：统一推荐给用户和 agent 使用的 public 参数名，同时保持旧请求可用。

推荐 canonical 参数名：

- 目标信号：`signal`
- 时钟：`clock`
- 单点时间：`time`
- 时间范围：`time_range.begin` 和 `time_range.end`
- 通用 stream/handshake 场景下的 valid/ready：`valid`、`ready`

兼容别名：

- 当 action 语义确实是信号时，`path`、`root_signal`、`cnt` 可映射到 `signal`。
- `clk` 映射到 `clock`。
- `requested_time` 和 `at` 映射到 `time`。
- `from/to` 和 `start/end` 映射到 `time_range.begin/end`。
- stream 风格配置中，`vld/rdy` 映射到 `valid/ready`。

实现策略：

1. 为 C++ engine handler 增加参数读取 helper，例如 `ActionArgsView`。
2. 先在新改动和本轮触碰的 handler 中使用 helper，不要把参数归一和 xout 投影混成一个大改。
3. 更新 action schema：明确 canonical 字段，并把旧字段标为 deprecated alias。
4. 更新 examples：普通示例只展示 canonical 字段；兼容示例单独说明。

## P1：MCP 默认 session

目标：恢复 MCP 使用体验，但不削弱 raw xdebug JSON API 的显式 session 契约。

实现策略：

1. 在 MCP session manager 中增加 `_default_session_key`。
2. `xverif_debug_session_open` 成功后，把打开的 session 设为默认 session。
3. `xverif_debug_query` 的 `session` 参数改为可选；不传时使用当前默认 session。
4. 显式传 `session` 时仍然覆盖默认值。
5. `xverif_debug_session_list` 返回 `default_session` 字段。
6. 默认 session 被 close 或 evict 时，清空默认值；如果只剩一个 live session，也可以按文档规则切换到唯一剩余 session。
7. raw CLI/API 继续要求显式 `target.session_id`。默认 session 只是 MCP 便利层，不是 xdebug core 的全局隐式状态。

验收标准：

- 打开一个 MCP debug session 后，不传 `session` 调 `xverif_debug_query` 能使用该 session。
- 打开两个 session 后，显式 `session` 能选择指定 session。
- 关闭默认 session 后，再不传 `session` 查询，应返回清晰的 `SESSION_REQUIRED`，或按文档规则选择唯一剩余 live session。

## P1：协议 config 易用性

目标：让 APB/AXI/Stream config load 更容易发现、更容易一次性修正。

实现策略：

1. 缺字段时一次性返回全部缺失字段，而不是遇到第一个字段就失败。
2. 缺必填 config 字段时使用 `MISSING_FIELD`，不要用泛化的 `INVALID_REQUEST`。
3. 错误 payload 增加 `required_fields`、`missing_fields` 和最小 `example_config`。
4. 支持 `clock` 作为 `clk` 的别名，并在内部归一。
5. Stream 支持 `valid/ready` 作为 `vld/rdy` 的别名。
6. 在 xdebug 文档和 xverif skill reference 中补 APB、AXI、Stream 的完整模板。

event 专项：

- `event.export` 支持和 `event.find` 一致的 inline 调用方式。
- 如果 `event.export` 使用已注册 config，且 config 中已有表达式，就不应要求用户再次传 `expr`。
  如果确实没有表达式，错误消息要明确指出缺少哪个字段。

## P2：compact 细节预算

真实 dump 还暴露了一类问题：有些输出不完全重复，但对 compact 首屏来说仍然过重。

建议预算：

- graph edge 中的长源码表达式只输出短 preview，完整文本保留在 JSON/full 模式。
- 能识别项目根时，绝对源码路径压缩为 repo-relative 或 `basename:line`。
- `session.list` 默认隐藏 socket/file transport 路径，只在 full/debug 输出。
- `session.doctor` 优先展示健康状态、资源新鲜度、transport 和可行动 warning；原始嵌套 metadata 只在 full/debug 输出。
- export action 只展示一次输出目录和 manifest，再展示表格统计；不要在 summary 和表格 footer 重复路径。

这些优先级低于重复消除，因为它们需要更清晰的 compact/full 输出策略，且已有用户可能依赖路径信息。

## P2：反馈中的覆盖缺口

覆盖报告当时显示 83 个 stable action 中已测 71 个。P0/P1 修复后，应补以下聚焦 smoke：

- `list.add`、`list.diff`、`list.validate`、`list.export`
- 全部 `stream.*` action
- `session.close`、`session.gc`、`session.kill`
- `schema`
- `instance.map`、`interface.resolve`

## 建议补丁顺序

1. 从 handler 源头删除冗余字段和嵌套 summary。
2. 修正错误响应 envelope，让错误路径也从 handler 顶层标量生成 public summary。
3. event/verify/trace/list 的真实输出字段断言。
4. MCP 默认 session。
5. 参数 alias helper、schema 和 example 更新。
6. 协议 config 诊断和文档。
7. 长路径、长表达式、session metadata 的 compact 细节预算。

这个顺序把低风险、高收益的文本清理放在最前面，避免把用户可见输出策略和更深层 API 兼容性改动混在一起。
