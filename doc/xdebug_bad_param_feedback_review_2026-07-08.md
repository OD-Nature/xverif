# xdebug Action 错误参数反馈记录

日期：2026-07-08

目的：并行调用多个子 agent，逐个覆盖当前 live catalog 中 70 个公开 xdebug action，记录每个 action 在输入错误参数时的反馈质量。此轮只做记录，不做源码修复。

## 执行方式

- 入口：主要使用 `tools/xdebug --json -` 原生 JSON action 入口。
- 覆盖：70/70 个公开 action，removed action `signal.search` 不纳入。
- 用例：每个 action 至少 2 类错误参数，覆盖缺 required、未知字段、旧字段名、错误层级、类型错误、非法 enum、非法 time/time_range、错误 one-of/anyOf 等。
- 分工：
  - builtin/session/design：子 agent `019f4252-87cc-7db0-8624-8ce1a29c0cbb`
  - waveform basic：子 agent `019f4252-aae6-7a12-8ff7-ef639fbdaaa6`
  - cursor/list/event/handshake：子 agent `019f4252-ce4d-7272-a18a-6e3882822805`
  - APB/AXI/stream/combined/rc：子 agent `019f4252-ffb8-7931-afdf-2377d93f7285`
- 临时 evidence：
  - `<repo>/tmp/xdebug_bad_param_review_design_builtin.md`
  - `<repo>/tmp/xdebug_bad_param_review_waveform_basic.md`
  - `<repo>/tmp/xdebug_bad_param_review_waveform_basic.jsonl`
  - `<repo>/tmp/xdebug_bad_param_review_stateful_event.md`
  - `<repo>/tmp/xdebug_bad_param_review_raw.json`
  - `<repo>/tmp/xdebug_bad_param_review_protocol_stream_combined.md`
  - `<repo>/tmp/xdebug_bad_param_review_protocol_stream_combined.raw.jsonl`

## 总览

| 分组 | action 数 | 错误请求数 | 错误请求被接受 | 主要 error code | 主要发现 |
| --- | ---: | ---: | ---: | --- | --- |
| builtin/session/design | 15 | 30 | 1 | `INVALID_REQUEST` 28, `INTERNAL_ERROR` 1, `OK_UNEXPECTED` 1 | required 缺失较可恢复；类型错误和 additional property message 泛化；`session.doctor` 类型错变 internal；`session.list` 错类型被接受 |
| waveform basic | 13 | 39 | 2 | `INVALID_REQUEST` 34, `ACTION_FAILED` 3, `OK` 2 | required 缺失较可恢复；类型错误和 oneOf 泛化；`counter.statistics`/`window.verify` 反向 `time_range` 返回 OK |
| cursor/list/event/handshake | 18 | 53 | 0 | 以 `INVALID_REQUEST` 为主，少量 runtime `TIME_SPEC_INVALID`/`ACTION_FAILED` | 大多数有 `invalid_arg=args.<field>`；`event.find/export` 的 one-of 失败只说 anyOf，不提示 `name` 或 `clock+signals` |
| APB/AXI/stream/combined/rc | 24 | 48 | 0 | `INVALID_REQUEST` 47, `SESSION_REQUIRED` 1 | 结构化 data 有恢复线索，但 message 太泛；旧字段迁移提示不足；`axi.channel_stall` 非法 channel 被 session 错误遮蔽 |
| 合计 | 70 | 170 | 3 | 以 `INVALID_REQUEST` 为主 | 主要问题不是“没有拒绝”，而是“message 不足以让 AI 直接改对” |

## 总体结论

1. 大多数坏参能被 schema 或 runtime 拦截，基础 fail-fast 边界有效。
2. 缺 required 的反馈通常能点名字段，但常缺少完整层级，例如应提示 `args.signal` 而不是只说 `signal`。
3. 类型错误、unknown field、additional property、oneOf/anyOf 失败的 message 过于 JSON schema 化，AI 需要再查 schema 才能恢复。
4. 很多有用线索在 `data.invalid_arg`、`data.expected`、`data.allowed_values`、`data.example` 中，但 `message` 本身没有把正确写法说清楚。
5. 旧字段迁移提示不足，例如 `args.num` -> `args.query.index`、`args.limit` -> `args.query.limit`、`args.name` -> `args.stream`、`args.depth` -> top-level `limits.max_depth`。
6. 少数 action 对错误参数接受或被别的错误遮蔽，最值得后续优先修复。

## 高风险记录

| action | 错误输入 | 实际反馈 | 风险 |
| --- | --- | --- | --- |
| `session.doctor` | `target.session_id` 为 number | `INTERNAL_ERROR: [json.exception.type_error.302] type must be string, but is number` | 参数错误暴露为 internal error，AI 会误判为产品异常 |
| `session.list` | `target.session_id` 为 number | 请求成功，未反馈坏参 | 错误 target 被忽略或未校验，AI 会误以为字段生效 |
| `window.verify` | `time_range.end < time_range.begin` | `OK` | 反向窗口被接受，AI 难以发现查询无效 |
| `counter.statistics` | `time_range.end < time_range.begin` | `OK` | 反向窗口被接受，统计结果可能被误读 |
| `event.find` | 缺 `name` 或 `clock+signals` | 泛化 anyOf 失败 | 不直接告诉正确组合，AI 需回查 schema |
| `event.export` | 缺 `name` 或 `clock+signals` | 泛化 anyOf 失败 | 同上 |
| `apb.config.load` | 只有 `name`，缺 `config/config_path` | 泛化 anyOf 失败 | 不直接列出可选配置来源 |
| `axi.config.load` | 只有 `name`，缺 `config/config_path` | 泛化 anyOf 失败 | 同上 |
| `stream.config.load` | 缺 `streams/config/config_path/file` | 泛化 anyOf 失败 | 不直接列出四种合法来源 |
| `axi.export` | 缺 `time_range` | 泛化 anyOf 失败 | 不直接提示 export 的条件 required |
| `axi.channel_stall` | 非法 `args.channel=zz` | `SESSION_REQUIRED: target.session_id is required` | 参数错误被 session/resource 错误遮蔽 |
| `apb.query` | 旧 `args.limit` | additional property，未提示 `args.query.limit` | AI 不能直接迁移到正确字段 |
| `axi.query` | 旧 `args.limit` | additional property，未提示 `args.query.limit` | 同上 |
| `trace.active_driver_chain` | 旧 `args.depth` | additional property，未提示 `limits.max_depth` | AI 不能直接迁移到正确层级 |
| `stream.query` | 旧 `args.name` | 缺 `stream`，未直接说 stream action 不用 name | 容易从 AXI/APB/list action 复制旧习惯 |

## 分组明细

### Builtin / Session / Design

| action | 测试到的错误参数 | 实际反馈摘要 | 可恢复性记录 |
| --- | --- | --- | --- |
| `actions` | 未知顶层字段；`args` 类型错误 | `INVALID_REQUEST`，additional property 或 `args must be an object` | 低；未给可用字段和完整层级 |
| `batch` | 缺 `args.requests`；`requests` 错写到顶层 | `INVALID_REQUEST`，点名 `requests` 或缺 `args` | 中高；能知道缺字段，但层级提示仍可更明确 |
| `schema` | `kind` 非法；`action` 类型错误 | `kind` 非法时提示 request/response；类型错为 `unexpected instance type` | 中；enum 较好，类型错较差 |
| `session.close` | 缺 `target.session_id`；错写到 `args.session_id` | `INVALID_REQUEST: target.session_id is required` | 高；直接提示正确层级 |
| `session.doctor` | 未知 args；`target.session_id` 类型错误 | unknown 为 `INVALID_REQUEST`；类型错为 `INTERNAL_ERROR` | 低；类型错不应变 internal |
| `session.gc` | 未知 args；`args` 类型错误 | `INVALID_REQUEST`，message 泛化 | 低；无参数 action 应提示“不接受 args”或列空合同 |
| `session.kill` | 缺 `target.session_id`；错写到 `args.session_id` | `INVALID_REQUEST: target.session_id is required` | 高；直接提示正确层级 |
| `session.list` | 未知 args；`target.session_id` 类型错误 | unknown 为 `INVALID_REQUEST`；错类型返回成功 | 低；错误 target 被接受或忽略 |
| `session.open` | 缺 `args.name`；`name` 类型错误 | 缺 required 可恢复；类型错为 `unexpected instance type` | 中；类型错应提示 `args.name` string |
| `expr.normalize` | 缺 `args.expr`；`expr` 类型错误 | 缺 required 可恢复；类型错泛化 | 中 |
| `signal.canonicalize` | 缺 `args.signal`；`signal` 错写顶层 | 点名缺 `signal` 或缺 `args` | 中；应说 `args.signal` |
| `signal.resolve` | 缺 `args.signal`；`signal` 类型错误 | 缺 required 可恢复；类型错泛化 | 中 |
| `source.context` | 缺 `args.line`；`line` 类型错误 | 缺 required 可恢复；类型错泛化 | 中 |
| `trace.driver` | 缺 `args.signal`；`time_unit` 非法 enum | 缺 required 可恢复；enum 提示不带完整层级 | 中 |
| `trace.load` | 缺 `args.signal`；`signal` 类型错误 | 缺 required 可恢复；类型错泛化 | 中 |

### Waveform Basic

| action | 测试到的错误参数 | 实际反馈摘要 | 可恢复性记录 |
| --- | --- | --- | --- |
| `value.at` | 缺 `signal`；旧 `at`；`signal` 数组 | 缺 `signal/time` 可恢复；类型错 `unexpected instance type` | 中；类型错应提示 `args.signal` string |
| `value.batch_at` | 缺 `signals`；旧 `signal`；`signals` string | 缺 required 可恢复；string 触发 oneOf 泛化 | 中低 |
| `expr.eval_at` | 缺 `signals`；旧 `at`；`expr` 数组 | 缺 required 可恢复；类型错泛化 | 中 |
| `verify.conditions` | 缺 `conditions`；旧 `checks`；`time` 放 condition 内 | 缺 required 可恢复 | 中；应提示 `args.conditions/time/clock` 最小例子 |
| `window.verify` | 缺 `clock`；顶层 `begin/end`；反向 `time_range` | 前两类拒绝；反向窗口返回 OK | 低；反向窗口需拒绝或 warning |
| `signal.changes` | 缺 `signal`；旧 `start/end`；`signal` object | required 可恢复；unknown/type 泛化 | 中低 |
| `signal.statistics` | 缺 `signal`；`signal` 数组；非法 clock | required 可恢复；类型错泛化；非法 clock 可定位 | 中 |
| `signal.stability` | 缺 `signal`；`time_range` 放 `limits`；非法 begin | wrong-level/invalid time 提示不完整 | 中低 |
| `detect_abnormal` | 缺 `signals`；旧 `signal`；`signals` string | required 可恢复；oneOf 泛化 | 中低 |
| `sampled_pulse.inspect` | 缺 `valid`；旧 `signal`；非法 clock | required 可恢复；非法 clock 可定位 | 中 |
| `counter.statistics` | 缺 `cnt`；旧 `valid/count`；反向 `time_range` | required 可恢复；反向窗口返回 OK | 低；需校验窗口顺序 |
| `scope.list` | 未知 `foo`；旧 `scope`；`recursive` string | additional/type 泛化 | 低；应列可用字段 `path/recursive/max_depth` |
| `scope.roots` | 未知 `foo`；误用 `path/recursive`；`source` object | additional/type 泛化 | 低；应说明 roots 不接受 scope.list 字段 |

### Cursor / List / Event / Handshake

| action | 测试到的错误参数 | 实际反馈摘要 | 可恢复性记录 |
| --- | --- | --- | --- |
| `cursor.set` | 缺 `name`；未知 `old_name`；`time` 类型错；旧 `at` | 多数返回 `invalid_arg=args.<field>` | 高 |
| `cursor.get` | 缺 `name`；未知 `old_name` | `invalid_arg=args.name/old_name` | 高 |
| `cursor.use` | 缺 `name`；未知 `old_name` | `invalid_arg=args.name/old_name` | 高 |
| `cursor.delete` | 缺 `name`；未知 `old_name` | `invalid_arg=args.name/old_name` | 高 |
| `cursor.list` | `args` 类型错；未知 `name` | 可拒绝并给 `invalid_arg` | 高 |
| `list.create` | 缺 `name`；未知 `list_name` | `invalid_arg=args.name/list_name` | 高 |
| `list.add` | 缺 `name`；未知 `list_name`；缺 `signal`；`signal` 类型错 | 多数有 `invalid_arg` | 高 |
| `list.delete` | 缺 `signal/index`；误用 `signals` | anyOf 缺组合时提示弱；unknown 较好 | 中 |
| `list.show` | `args` 类型错；未知 `list_name` | 可拒绝 | 高 |
| `list.validate` | 缺 `name`；未知 `list_name` | 可拒绝 | 高 |
| `list.diff` | 缺 `name`；未知 `list_name`；`begin/end` 错层级；非法 begin | schema 错误较好；runtime time 错误缺完整层级 | 中 |
| `list.value_at` | 缺 `name`；未知 `list_name`；缺 `clock`；旧 `at` | 可恢复 | 高 |
| `list.export` | 缺 `name`；未知 `list_name`；非法 `format`；`path` 错层级 | schema 拒绝并给 `invalid_arg` | 高 |
| `event.config.load` | 缺 `name`；误传 inline `clock/signals/expr`；`config_path` 类型错 | 可拒绝并定位字段 | 高 |
| `event.config.list` | `args` 类型错；未知 `config_name` | 可拒绝 | 高 |
| `event.find` | 缺 `expr`；缺 `name` 或 `clock+signals`；非法 edge；`begin/end` 错层级 | required/enum 较好；one-of 失败差 | 中低 |
| `event.export` | 缺 `expr`；缺 `name` 或 `clock+signals`；非法 edge；`begin/end` 错层级 | 同 `event.find` | 中低 |
| `handshake.inspect` | 缺 `ready`；`valid` 类型错；非法 `sample_point`；非法 time | schema 错误较好；runtime time 错误缺完整层级 | 中高 |

### APB / AXI / Stream / Combined / RC

| action | 测试到的错误参数 | 实际反馈摘要 | 可恢复性记录 |
| --- | --- | --- | --- |
| `apb.config.load` | 缺 `name`；缺 `config/config_path` | 缺 name 可恢复；one-of 泛化 | 中 |
| `apb.config.list` | 缺 `name`；未知 `interface` | `invalid_arg` 有字段，message 不列可用字段 | 中高 |
| `apb.query` | 缺 `name`；旧 `args.limit` | 缺 name 好；旧字段不提示 `args.query.limit` | 中 |
| `apb.cursor` | 缺 `op`；非法 `op` | 有 allowed values | 高 |
| `apb.transfer_window` | 缺 `name`；旧 `args.num` | 旧字段不提示正确字段 | 中 |
| `axi.config.load` | 缺 `name`；缺 `config/config_path` | one-of 泛化 | 中 |
| `axi.config.list` | 缺 `name`；未知 `interface` | 可拒绝 | 中高 |
| `axi.query` | 缺 `name`；旧 `args.limit` | 旧字段不提示 `args.query.limit` | 中 |
| `axi.cursor` | 缺 `op`；非法 `op` | 有 allowed values | 高 |
| `axi.analysis` | 缺 `name`；非法 `direction` | enum 有 allowed values | 高 |
| `axi.export` | 缺 `time_range`；`output` 为 string | one-of/类型错不直接说 `args.output.path` | 中 |
| `axi.channel_stall` | 缺 `name`；非法 `channel` | 非法 channel 被 `SESSION_REQUIRED` 遮蔽 | 低 |
| `axi.latency_outlier` | 缺 `name`；未知 `threshold` | unknown 不说明可用字段 | 中 |
| `axi.outstanding_timeline` | 缺 `name`；误用 `direction` | additional property，不说明此 action 不接受 direction | 中 |
| `axi.request_response_pair` | 缺 `name`；误用 `direction` | additional property，不说明此 action 不接受 direction | 中 |
| `stream.config.load` | 缺 `streams/config/config_path/file`；误用 `name` | one-of 泛化；旧字段不提示 stream config 正确来源 | 中低 |
| `stream.config.list` | 误用 `name`；`args` 非 object | unknown 可拒绝；args 类型错缺 `invalid_arg` | 中 |
| `stream.show` | 缺 `stream`；`stream` 数组 | 有 `invalid_arg=args.stream` | 高 |
| `stream.validate` | 缺 `stream`；`stream` object | 有 `invalid_arg=args.stream` | 高 |
| `stream.query` | 缺 `query`；误用 `name` | 缺 query 好；旧 name 未提示 `stream` 统一字段 | 中高 |
| `stream.export` | 缺 `stream`；非法 `kind` | 有 allowed values `transfer/packet/packet_beats` | 高 |
| `trace.active_driver` | 缺 `signal`；`time` object | 有 `invalid_arg=args.signal/time` | 高 |
| `trace.active_driver_chain` | 缺 `time`；旧 `args.depth` | 缺 time 好；旧 depth 不提示 `limits.max_depth` | 中 |
| `rc.generate` | 缺 `output`；`output` string | 指出 `args.output`，但不直接说 `args.output.path` | 中 |

## 错误反馈模式记录

| 模式 | 典型 message | 问题 | 建议记录 |
| --- | --- | --- | --- |
| 缺 required | `required property 'signal' not found in object` | 常只给字段名，不给 `args.signal` | message 加完整路径 |
| 类型错误 | `unexpected instance type` | 不说哪个字段、期望类型、实际类型 | message 合并 `invalid_arg/expected/received_type` |
| unknown field | `additional property 'foo'` | 不列可用字段，也不提示迁移字段 | data/message 加 `allowed_args` 或 `did_you_mean` |
| oneOf/anyOf | `no subschema has succeeded` | 不列合法组合 | data/message 加 `required_any_of` |
| 旧字段名 | `additional property 'limit'` | 不告诉新字段 | 加 action-specific migration hints |
| runtime time parse | `Invalid time 'abc'` | 不稳定带出 `args.time_range.begin` | runtime error 带 `invalid_arg` |
| resource/session 遮蔽 | `SESSION_REQUIRED` | 参数问题被掩盖 | schema 参数校验应早于 session/resource 检查，或同时返回参数问题 |
| 坏参返回 OK | `ok=true` | AI 误以为请求有效 | 校验语义边界或在 summary warning 中提示 ignored/invalid |

## 后续可作为修复计划输入的问题清单

本报告只记录，不实施修复。后续如果进入修复阶段，建议按以下顺序拆分：

1. 硬错误：`session.doctor` 类型错 internal、`session.list` 错 target 返回 OK、`window.verify`/`counter.statistics` 反向窗口返回 OK。
2. one-of/anyOf 友好提示：`event.find/export`、`apb/axi.config.load`、`stream.config.load`、`axi.export`、`list.delete`。
3. 旧字段迁移提示：`args.num`、`args.limit`、`args.name`、`args.depth`、`at`、`begin/end`。
4. message/data 对齐：把 `invalid_arg`、`expected`、`received_type`、`allowed_values`、`example` 摘要并入用户可见 message 或 xout。
5. runtime 错误路径：time parser、clock/signal lookup、session/resource 前置检查统一返回可恢复字段路径。

## 2026-07-08 修复实施摘要

本轮按 `doc/xdebug_bad_param_feedback_fix_plan_2026-07-08.md` 实施，保留旧字段拒绝策略，不做兼容执行。

已修复：

- Schema 层错误现在会向 JSON error 和 xout 透出 `invalid_arg`、`expected`、`received_type`、`allowed_values`、`did_you_mean`、`required_any_of`、`correct_example`。
- `apb.query` / `axi.query` 的旧 `args.limit`、`args.num` 提示到 `args.query.limit` / `args.query.index`。
- `stream.query` 误用 `args.name` 时提示到 `args.stream`，并保留拒绝旧字段。
- `trace.active_driver_chain.args.depth` 提示到 top-level `limits.max_depth`。
- `event.find/export`、`apb/axi.config.load`、`stream.config.load`、`axi.export`、`list.delete` 的条件必填错误补充 `required_any_of`。
- `session.doctor` / `session.list` 对非字符串 `target.session_id` 返回 `INVALID_REQUEST`，不再进入 handler 或返回 OK。
- `session.close` / `session.kill` 缺 `target.session_id` 时补充 `correct_example`。
- `window.verify` / `counter.statistics` 等共享 time_range 解析路径现在拒绝 `end < begin`，返回 `TIME_RANGE_INVALID` 并指向 `args.time_range.end`。
- `axi.channel_stall.args.channel` 收紧为 `aw/w/b/ar/r`，runtime 不再把非法 channel 静默当成 `ar`。
- `TextResponseBuilder` 在默认 xout 中显示结构化坏参恢复字段和 `correct_example`。
- xverif skill 与 xdebug 架构文档已补充坏参恢复规则，并强调默认优先 xout。

验证记录：

- `make -C xdebug xdebug` 通过，未出现编译 warning。
- `make -C xdebug internal-engines` 通过，未出现编译 warning。
- `make -C xdebug unit-test` 通过。
- `make -C xdebug test-fast` 在沙箱外通过。
- `make -C xdebug test-regression` 在沙箱外通过。
- `make -C xdebug contract-test` 通过。
- `python3 -m pytest xdebug/tests/contract/test_action_contract.py -q` 在沙箱外通过，`19 passed`。
- `PYTHONPATH=<repo>/xverif_mcp/src python3 -m pytest xverif_mcp/tests/test_direct_output_formats.py -q` 通过，`9 passed`。
- `python3 xdebug/tools/sync_runtime_request_schemas.py --check` 通过。
- `python3 xdebug/tools/sync_action_schema_hints.py --check` 通过。

待后续继续扩大覆盖：

- 本轮新增 contract 覆盖“所有 action 至少能在未知参数时返回 `correct_example`”，以及重点坏参路径；尚未把审计报告中每个 action 的每一种错误输入全部固化为单独 pytest 参数化用例。
- MCP 默认 xout 的坏参 smoke 仍需在完整 MCP 回归中覆盖；本轮 backend xout 已覆盖，MCP 文档已同步。
