# xdebug 响应字段完全手册

本文是 `xdebug.v1` CLI JSON API 的响应字段手册，覆盖当前 action catalog 中的所有命令。`tools/xdebug --json -` 可输出 JSON 或 xout；JSON 用于脚本字段读取，xout 用于 AI 阅读的结构化摘要。它面向 AI agent 和脚本作者，目标是说明每个 action 成功响应里可能出现的 `summary`、`data`、`findings`、`meta`、`error` 字段，以及 compact/verbose 下字段是否会被省略。

机器可校验契约以 action-specific response schema 为准：`xdebug/schemas/v1/actions/<action>.response.schema.json`。本文负责解释字段含义；schema 和 `xdebug/examples/responses/<action>.basic.json` 负责约束 compact 主路径。

规则优先级：

1. 永远先检查顶层 `ok`。
2. `ok=false` 时优先读取 `error.code`、`error.message`、`error.recoverable`。
3. `ok=true` 时优先读取 `summary` 和 compact `data`。
4. `meta.truncated=true` 时，不要把结果当作完整全集。
5. compact 成功响应可能省略空 `session`、空 `warnings`、空 `findings`、空 `suggested_next_actions`、`tool` 和 elapsed 细节。
6. 如果设置了 `XDEBUG_COMMON_BLOCKS` 且 trace 相关 action 的返回 payload 中有 `file` 精确命中配置，响应会在原有 `data` 末尾追加 `data.common_blocks`；未命中时不新增字段，原输出不变。

## 1. 顶层 Envelope

所有 action 最终都归一化到 `xdebug.v1` envelope。

| 字段 | 类型 | 出现条件 | 含义 |
| --- | --- | --- | --- |
| `api_version` | string | 总是 | 固定为 `xdebug.v1` |
| `request_id` | any | 请求带 `request_id` 时 | 调用方透传 ID |
| `ok` | boolean | 总是 | action 是否成功 |
| `action` | string | 总是 | 实际响应 action |
| `tool.name` | string | verbose 常见 | 工具名，归一化为 `xdebug` |
| `tool.version` | string | verbose 常见 | 工具版本 |
| `session` | object/null | verbose、session action、combined action 或失败诊断 | 当前 session 或资源信息 |
| `summary` | object | 成功通常非空 | action 摘要 |
| `data` | object/array/null | 成功通常非空；失败通常 null | action 业务 payload |
| `findings` | array | 非空时，或 verbose | 异常/风险/诊断发现 |
| `suggested_next_actions` | array | 失败默认可出现；成功响应按 action-specific summary/warnings 判断 | 工具建议的后续动作 |
| `warnings` | array | 非空时，或 verbose | 非致命告警 |
| `error` | object/null | 失败时 object | 结构化错误 |
| `meta.truncated` | boolean | 总是或截断时 | 当前 payload 是否被限制截断 |
| `meta.elapsed_ms` | number | verbose 或内部响应 | action 耗时 |

### `data.common_blocks`

`trace.driver`、`trace.load`、`trace.active_driver` 和 `trace.active_driver_chain` 支持可选 common block 提示。通过环境变量指定配置：

```text
XDEBUG_COMMON_BLOCKS=/path/to/common_blocks.json
```

这些 trace action 的 XOUT 源码窗口默认显示有效行上下 3 行，可用 `XDEBUG_TRACE_SOURCE_CONTEXT_LINES` 调整；同文件有效行号差值小于 10 时默认合并显示，可用 `XDEBUG_TRACE_SOURCE_MERGE_THRESHOLD_LINES` 调整。JSON 字段仍以 `source_context[]` 和 `signal_path[]` 为机器合同。

配置文件示例：

```json
{
  "schema_version": "xdebug.common_blocks.v1",
  "common_blocks": [
    {
      "file": "rtl/common/fifo_async.sv",
      "card": "docs/common_blocks/fifo_async.md"
    }
  ]
}
```

匹配只使用响应 payload 中已有 `file` 字段做精确字符串匹配；没有 `file` 字段时不推断。命中时只在原有 `data` 的最后追加：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `message` | string | 提示 AI 这是已验证 common block，除非必要不要继续追内部逻辑 |
| `file` | string | 命中的代码文件路径 |
| `card` | string | 对应摘要卡 Markdown 路径 |

xout 中该信息追加在所有原有内容之后：

```text
common_blocks:
  This is a verified common block. Unless necessary, do not chase internal logic; use the summary card to continue reasoning.
  file: rtl/common/fifo_async.sv
  card: docs/common_blocks/fifo_async.md
```

### `error` 对象

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `code` | string | 机器可读错误码 |
| `message` | string | 人类可读错误说明 |
| `recoverable` | boolean | 修改请求或恢复 session 后是否可重试 |
| `candidates` | array | 可选候选项，通常用于 resolve 失败 |
| `suggested_actions` | array | 可选恢复动作 |
| `invalid_arg` | string | 参数错误时指出错误字段路径，例如 `args.time_range.end` |
| `expected` | string | 参数错误时期望的类型、范围或语义 |
| `received_type` | string | 参数类型错误时的实际 JSON 类型 |
| `allowed_values` | array | enum 或有限取值列表 |
| `did_you_mean` | string | 常见错字段对应的正确字段路径 |
| `required_any_of` | array | `anyOf` 必填组说明 |
| `correct_example` | object | 最小正确请求模板，可用于直接修正下一次调用 |

参数错误要先读 `invalid_arg`、`did_you_mean`、`required_any_of` 和 `correct_example`。schema 层错误和 action handler 层语义错误都会尽量给出这些字段；默认 xout 也会显示同名信息，便于 AI 不请求 JSON 时修正下一次调用。

常见 `error.code`：

```text
MISSING_FIELD
INVALID_ARGUMENT
INVALID_ENUM
INVALID_TIME
INVALID_TARGET
RESOURCE_REQUIRED
SESSION_NOT_FOUND
SESSION_ID_EXISTS
SESSION_UNHEALTHY
SIGNAL_NOT_FOUND
SOURCE_NOT_FOUND
TIME_RANGE_INVALID
TIME_OUT_OF_RANGE
CONFIG_NOT_FOUND
LIST_NOT_FOUND
PRECONDITION_FAILED
CURSOR_NOT_FOUND
CLOCK_OFFSET_UNSUPPORTED
EXPR_PARSE_FAILED
WAVE_QUERY_FAILED
INTERNAL_ENGINE_FAILED
INTERNAL_ERROR
UNKNOWN_ACTION
UNSUPPORTED_API_VERSION
```

### `session` / session record

顶层 xdebug session record 常见字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | string | session id |
| `mode` | string | `design`、`waveform`、`combined` |
| `daidir` | string | 设计数据库路径，存在于 design/combined |
| `fsdb` | string | FSDB 路径，存在于 waveform/combined |

波形内部 session info 在 verbose 或 waveform session action 中可能更详细：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` / `session_id` | string | 波形 session id |
| `fsdb` / `fsdb_file` | string | FSDB 文件 |
| `pid` | number | daemon pid |
| `transport` | string | `uds`、`tcp` 或 `file` |
| `socket` / `socket_path` | string | UDS socket 路径；TCP session 中可能为空或仅作内部路径记录 |
| `file_dir` | string | file transport v2 交换目录，内部含 `requests/`、`claims/`、`responses/`、`done/`、`failed/`、`tmp/`、`heartbeat/` |
| `bind_host` | string | TCP daemon listen 地址 |
| `host` | string | TCP client 连接地址 |
| `port` | number | TCP port；`0` 请求自动分配，响应里通常是实际端口 |
| `created_at` / `last_active` | string/number | 生命周期信息 |
| `fingerprint` | object | FSDB mtime/size/inode/dev 等健康检查信息 |

`transport/host/bind_host/port/socket_path` 通常只在 `session.open/list/doctor`、`args.output.verbose:true` 或后端日志中出现。compact action 响应不会反复携带 endpoint 信息；连接问题优先读 `~/.xdebug/{design,waveform}/sessions/<hashed-session>/logs/transport.ndjson`。

`fingerprint.dev` / `fingerprint.inode` 是路径所在挂载位置的 identity 诊断字段，不是内容 freshness contract。跨登录机、计算节点或容器访问同一共享路径时它们可能不同；xdebug 判定资源是否变化只依赖 `mtime + size`。日志里的 `identity_changed:true` 表示位置身份变化，不等同于 FSDB/daidir 内容变化。

### `value` 对象

verbose 或 raw value 常见形态：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `value` | string | 带格式前缀或显示格式的值 |
| `known` | boolean | 是否不含 X/Z |

compact `value.at` 直接使用 `data.value` 字符串和 `data.known` boolean；verbose 或 JSON 详情 使用对象。

### `resolved_time` / `resolved_time_range`

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `source` | string | 原始 TimeSpec，例如 `@deadlock-20ns` |
| `time` | string | 格式化时间 |
| `time_value` | number | 内部数值时间 |
| `begin` | object | range begin resolved_time |
| `end` | object | range end resolved_time |
| `source: "around_window"` | string | range 来自 `around/before/after` |

### `graph.node`

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | string | 图内节点 id，如 `n0` |
| `signal` | string | RTL 信号名 |
| `kind` | string | 节点类型，当前多为 `signal` |
| `role` | string | `root` 或 `dependency` |

### `graph.edge`

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `from` | string | 图内 from node id |
| `to` | string | 图内 to node id |
| `from_signal` | string | from 真实信号 |
| `to_signal` | string | to 真实信号 |
| `type` | string | `data_dependency`、`control_dependency`、`load_dependency`、`statement_only` 等 |
| `role` | string | trace record role |
| `file` | string | evidence 文件 |
| `line` | number | evidence 行号 |
| `source` | string | verbose 或源码上下文响应中源码行 |
| `resolution` | string | resolve 类型 |
| `confidence` | string | `high`、`medium`、`low`、`unknown` |
| `relation` | string | 聚合关系，如 `controls_assignment` |
| `evidence` | array | 聚合 edge 的 evidence 样本 |
| `evidence_count` | number | 聚合前证据数量 |
| `evidence_truncated` | boolean | evidence 样本是否截断 |
| `omitted_evidence_count` | number | 被省略 evidence 数 |

## 2. Catalog 和 Batch

### `schema`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.api_version` | string | 当前 API 版本 |
| `data.request.required` | array | 必需请求字段 |
| `data.request.target_resources` | array | 支持资源：`daidir`、`fsdb`、`session_id` |
| `data.request.modes` | array | `design`、`waveform`、`combined` |
| `data.combined_action.action` | string | `trace.active_driver` |
| `data.combined_action.required_target` | array | `daidir`、`fsdb` |
| `data.combined_action.required_args` | array | `signal`、`time` |

### `actions`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.actions[]` | string array | 默认 compact catalog，包含所有公开 action name |
| `summary.verbose` | boolean | `false` 表示 compact names；`true` 表示 descriptor catalog |
| `data.actions[].name` | string | 仅 `args.output.verbose=true` 时存在的 descriptor name |
| `data.removed` | array | 已移除 action，当前包含 `signal.search` |
| `data.modes.design` | array | 设计侧 action |
| `data.modes.waveform` | array | 波形侧 action |
| `data.modes.combined` | string | combined action 描述 |

### `batch`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.count` | number | 实际执行 child 请求数 |
| `summary.all_ok` | boolean | 所有 child 是否成功 |
| `summary.failed_count` | number | 失败 child 数量 |
| `summary.failed_indexes[]` | integer array | 失败 child 的 0-based indexes |
| `summary.failed_codes[]` | string array | 与 failed_indexes 对齐的 error codes |
| `summary.failed_layers[]` | string array | 与 failed_indexes 对齐的 error layers |
| `data.results[]` | array | 每个 child 的完整 xdebug response |
| `error.code` | string | 任一 child 失败时为 `BATCH_PARTIAL_FAILURE` |
| `args.mode` | string | 请求侧可用 `continue_on_error` 或 `stop_on_error` |

## 3. Session 命令

### `session.open`

顶层 xdebug session open：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `session.id` | string | 新 session id |
| `session.mode` | string | `design`、`waveform`、`combined` |
| `session.daidir` | string | design/combined 存在 |
| `session.fsdb` | string | waveform/combined 存在 |
| `summary.session_id` | string | session id |
| `summary.mode` | string | session mode |
| `summary.session_id` | string | 新建 session 名 |
| `data.session` | object | 同顶层 `session` |
| `data.session.transport` | string | 后端 transport，通常为 `uds`，显式 TCP/file 时为 `tcp` 或 `file` |
| `data.session.host` / `data.session.port` | string/number | TCP endpoint；只在 TCP/verbose/后端响应中稳定有意义 |
| `data.session.file_dir` | string | file transport endpoint；只在 file/verbose/后端响应中稳定有意义 |

波形内部直接响应：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.session_id` | string | 波形 session id |
| `summary.fsdb` | string | FSDB 文件 |
| `data.session` | object | 波形 session info |

### `session.list`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.session_count` | number | 顶层 xdebug session 数 |
| `data.sessions[]` | array | session record 列表 |
| `data.sessions[].id` | string | session id |
| `data.sessions[].mode` | string | mode |
| `data.sessions[].daidir` | string | 可选 |
| `data.sessions[].fsdb` | string | 可选 |

设计内部 session list 可能使用：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.count` | number | design session 数 |
| `data.sessions[]` | array | design session info |

### `session.doctor`

顶层 xdebug doctor：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.session_id` | string | session id |
| `summary.mode` | string | mode |
| `summary.healthy` | boolean | 所有相关 engine 是否健康 |
| `data.health.design` | object | unified engine design health payload，design/combined 存在 |
| `data.health.waveform` | object | unified engine waveform health payload，waveform/combined 存在 |
| `error.code` | string | 不健康时 `SESSION_UNHEALTHY` |

内部 doctor：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.healthy` | boolean | 单 engine 健康状态 |
| `summary.status` | string | 健康状态名 |
| `summary.message` | string | 诊断说明 |
| `data.health` | object | 同 summary |

### `session.gc`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.status` | string | `completed` |

### `session.kill` / `session.close`

`session.close` / `session.kill` 的公开合同都要求传 `target.session_id`；不要把 session 选择写到 `args.session_id`。

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.session_id` | string | 被关闭 session id，单个 session 时 |
| `summary.removed` | boolean | 顶层关闭是否成功 |
| `summary.status` | string | waveform 内部或 `all` 关闭时为 `removed` |
| `summary.target` | string | `all` 关闭时为 `all` |

## 4. Combined 命令

### `trace.active_driver`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `session.mode` | string | 固定 `combined` |
| `session.daidir` | string | 设计数据库 |
| `session.fsdb` | string | 波形数据库 |
| `summary.signal` | string | 查询信号 |
| `summary.requested_time` | string | 请求时间 |
| `summary.active_time` | string | NPI active trace 判定的生效时间 |
| `summary.path_count` | number | 输出路径数 |
| `summary.truncated` | boolean | 是否截断 |
| `data.paths[]` | array | 源码窗口 + 信号路径 |

`data.paths[]` item：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `file` | string | 源文件 |
| `line` | number | 有效源行 |
| `source_context[]` | array | 有效行上下 3 行源码窗口 |
| `source_context[].line` | number | 源码行号 |
| `source_context[].text` | string | 源码文本 |
| `source_context[].active` | boolean | 是否为有效行 |
| `signal_path[]` | array | 相关信号路径，顺序表示追踪方向 |

### `trace.active_driver_chain`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.signal` | string | 起点信号 |
| `summary.start_time` | string | 起点时间 |
| `summary.hop_count` | number | hop 数 |
| `summary.termination` | string | 结束原因 |
| `summary.truncated` | boolean | 是否截断 |
| `data.hops[]` | array | 每一跳的源码窗口 + 信号路径 |

`data.hops[]` 使用和 `data.paths[]` 相同的字段，并额外包含 `index`。

## 5. Design 命令

### `trace.driver` / `trace.load`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.signal` | string | 查询信号 |
| `summary.mode` | string | `driver` 或 `load` |
| `summary.path_count` | number | 输出路径数 |
| `summary.truncated` | boolean | 是否截断 |
| `data.paths[]` | array | 源码窗口 + 信号路径 |

`data.paths[]` item：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `file` | string | 源文件 |
| `line` | number | 有效源行 |
| `source_context[]` | array | 有效行上下 3 行源码窗口 |
| `source_context[].line` | number | 源码行号 |
| `source_context[].text` | string | 源码文本 |
| `source_context[].active` | boolean | 是否为有效行 |
| `signal_path[]` | array | 相关信号路径，顺序表示追踪方向 |

### `signal.resolve`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.query` | string | 查询字符串 |
| `summary.count` | number | 匹配数 |
| `summary.truncated` | boolean | 是否截断 |
| `data.query` | string | 查询字符串 |
| `data.count` | number | 匹配数 |
| `data.matches[]` | array | 匹配项 |
| `data.truncated` | boolean | 是否截断 |
| `error.code` | string | 找不到时 `SIGNAL_NOT_FOUND` |

`data.matches[]` 字段由 unified engine design handler 返回，常见为 `signal`、`kind`、`file`、`line`、`scope`、`width`。

### `signal.canonicalize`

继承 `signal.resolve` 字段，并额外添加：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.canonical` | string | 选中的 canonical path |
| `summary.ambiguous` | boolean | 是否多候选 |
| `data.canonical` | string | canonical path |
| `data.rtl_path` | string | 同 canonical |
| `data.query` | string | 原始查询 |
| `data.leaf` | string | leaf signal |
| `data.scope` | string | 父 scope |
| `data.base_signal` | string | 去掉 select 的 base |
| `data.select` | string | bit/part select |
| `data.ambiguous` | boolean | 是否多候选 |
| `data.aliases[]` | array | query/canonical alias |
| `data.fsdb_candidates[]` | array | 可能对应 FSDB path |
| `data.port_mappings[]` | array | 当前为空数组 |

### `source.context`

compact：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.file` | string | 文件 |
| `summary.line` | number | 行号 |
| `data.file` | string | 文件 |
| `data.line` | number | 行号 |
| `data.symbol` | string | 请求 symbol |
| `data.context_kind` | string | 推断上下文类型 |
| `data.enclosing` | object | enclosing block |

`data.enclosing`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `type` | string | `module`、`always_ff`、`always_comb`、`always`、`case`、`if`、`begin`、`unknown` |
| `name` | string | module 名等 |
| `begin_line` | number | block 起始 |
| `end_line` | number | block 结束 |

verbose 或源码上下文响应：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.context[]` | array | 源码上下文行 |
| `data.context[].line` | number | 行号 |
| `data.context[].text` | string | 源码文本 |
| `data.context[].hit` | boolean | 是否命中行 |

### `expr.normalize`

表达式字符串模式：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.expr` | string | 原始表达式 |
| `summary.source` | string | `string_fallback` |
| `summary.confidence` | string | `low` |
| `data.expr` | object | AST |
| `data.confidence` | string | `low` |
| `data.confidence_reason` | string | 原因 |

signal 模式：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.signal` | string | 查询信号 |
| `summary.source` | string | `npi_trace_assignment` |
| `summary.confidence` | string | trace confidence |
| `data.expr` | object | RHS AST |
| `data.assignment` | object | assignment |
| `data.rhs_signals[]` | array | RHS signals |
| `data.confidence` | string | 置信度 |

AST node 常见字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `op` | string | `and`、`or`、`not`、`eq`、`neq`、`add`、`sub`、`ternary` 等 |
| `args[]` | array | 子表达式 |
| `type` | string | `signal`、`const`、`unknown` |
| `name` | string | signal node 名 |
| `value` | string | const 值 |
| `text` | string | unknown/text fallback |

## 6. Waveform 基础命令

### `cursor.set`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.status` | string | server data 有 status 时，通常 `set` |
| `summary.known` | boolean | wrapper 从 status 分支填充，通常 false |
| `data.cursor` | object | cursor |
| `data.resolved_time` | object | 解析后的时间 |
| `data.status` | string | `set` |

cursor 对象字段：`name`、`time`、`time_text`、`note`、`origin`、`clock`、`created_at`、`updated_at`。

### `cursor.get`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.cursor` | object | cursor 对象 |

### `cursor.list`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.cursors[]` | array | cursor 列表 |
| `data.active_cursor` | string | active cursor 名 |
| `data.cursor_count` | number | cursor 数 |

### `cursor.delete`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.status` | string | `deleted` |
| `data.status` | string | `deleted` |
| `data.name` | string | 删除的 cursor |

### `cursor.use`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.status` | string | `active` |
| `data.status` | string | `active` |
| `data.active_cursor` | string | active cursor |
| `data.cursor` | object | cursor |

### `scope.list`

compact：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.path` | string | scope |
| `summary.recursive` | boolean | 是否递归 |
| `summary.signal_count` | number | 返回/限制后条目数 |
| `summary.truncated` | boolean | 是否截断 |
| `data.signals_preview[]` | array | preview 字符串 |
| `meta.truncated` | boolean | 是否截断 |

verbose 或 export：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.signals[]` | array | scope dump 字符串全集或限集 |

### `scope.roots`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.source` | string | root 来源选择，例如 `auto` |
| `summary.root_count` | number | 合并 root 数 |
| `summary.wave_count` | number | waveform root 数 |
| `summary.design_count` | number | design root 数 |
| `summary.matched_count` | number | design/wave 匹配 root 数 |
| `summary.recommended_root` | string/null | 推荐 root |
| `summary.recommended_reason` | string | 推荐原因 |
| `data.roots[]` | array | 合并后的 root 列表 |
| `data.wave_roots[]` | array | waveform root 列表 |
| `data.design_roots[]` | array | design root 列表 |
| `data.limitations[]` | array | 可选限制说明 |

`data.roots[]` item 常见字段：`path`、`sources[]`、`status`、`wave`、`design`。

### `rc.generate`

成功：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.config_path` | string | 输入 JSON 配置路径 |
| `summary.rc_path` | string | 输出 rc 路径 |
| `summary.group_count` | number | group/subgroup 总数 |
| `summary.signal_count` | number | 普通 `addSignal` 数量 |
| `summary.expr_signal_count` | number | `addExprSig` 数量 |
| `summary.marker_count` | number | `userMarker` 数量 |
| `summary.written` | boolean | 是否已写 rc |
| `summary.valid` | boolean | 信号和时间校验是否全部通过 |
| `summary.missing_signal_count` | number | runtime diagnostic optional：缺失信号数；当前 response schema 未显式列为稳定 property |
| `summary.invalid_time_count` | number | runtime diagnostic optional：非法时间数；当前 response schema 未显式列为稳定 property |
| `data.validation.signals[]` | array | 每个普通信号和 expr alias 信号的校验结果 |
| `data.validation.times[]` | array | cursor/main_marker/zoom/user_marker 时间校验结果 |
| `data.rc_preview[]` | array | preview 模式或 verbose 下的 rc 前若干行 |

`data.validation.signals[]` item：`kind`、`owner`、`input_path`、`rc_path`、`exists`、可选 `error`。

`data.validation.times[]` item：`kind`、`owner`、`spec`、`valid`、可选 `resolved_time` 或 `error`。

失败：

| 错误码 | 含义 |
| --- | --- |
| `RC_CONFIG_INVALID` | 配置文件不是 JSON、字段非法、信号路径不是点分格式、expr alias 不存在等 |
| `RC_VALIDATION_FAILED` | FSDB 信号或时间校验失败，默认不写 rc |
| `RC_WRITE_FAILED` | 输出路径无法创建或写入 |

注意：`rc.generate` 不写 `openDirFile` / `activeDirFile`；它只生成 nWave signal list/view rc。

### `value.at`

compact：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.signal` | string | 信号 |
| `summary.time` | string | 请求时间 |
| `summary.known` | boolean | 是否无 X/Z |
| `data.signal` | string | 信号 |
| `data.time` | string | 请求时间 |
| `data.value` | string | 值字符串 |
| `data.known` | boolean | 是否无 X/Z |

verbose 或 JSON 详情：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.resolved_time` | object | TimeSpec 解析结果 |
| `data.value.value` | string | 值字符串 |
| `data.value.known` | boolean | 是否无 X/Z |

### `value.batch_at`

compact：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.time` | string | 请求时间 |
| `summary.signal_count` | number | 请求信号数 |
| `summary.x_or_z_count` | number | X/Z 信号数 |
| `summary.unknown_count` | number | 兼容字段，同 X/Z 数 |
| `summary.missing_count` | number | 查询失败信号数 |
| `summary.missing_by_reason` | object | `status -> count`，例如 `signal_not_found` |
| `data.values` | object | `signal -> value/null` map |

verbose 或 JSON 详情：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.resolved_time` | object | TimeSpec 解析 |
| `data.values[]` | array | per-signal item |
| `data.values[].signal` | string | 信号 |
| `data.values[].time` | string | 时间 |
| `data.values[].status` | string | `ok`、`signal_not_found`、`not_dumped_or_unreadable`、`time_out_of_range` 或 `unsupported_format` |
| `data.values[].reason` | string | 失败或 unsupported 的可读原因 |
| `data.values[].suggested_next_actions` | array | 下一步建议 |
| `data.values[].value` | object/null | value object |
| `data.values[].error` | string | 失败原因 |
| `data.values[].xbit_hints` | object | 传 `slice_hint` 时生成的 xbit 命令 |

## 7. Waveform List 命令

### `list.create`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.status` | string | `created` |

### `list.add`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.signal` | string | 添加信号 |
| `summary.status` | string | `added` |

### `list.delete`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.removed` | string | 被删除 signal 或 index |

### `list.show`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.signal_count` | number | 信号数 |
| `data.signals[]` | array | 信号列表 |
| `data.signals[].index` | number | 1-based index |
| `data.signals[].signal` | string | 信号 path |

### `list.value_at`

compact：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.time` | string | 请求时间 |
| `data.values` | object | `signal -> value/null` |

verbose 或 JSON 详情：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.values` | object | `signal -> value object` |
| `data.resolved_time` | object | TimeSpec 解析 |
| `error.code` | string | 部分缺失时 `SIGNAL_NOT_FOUND` |

### `list.validate`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.all_found` | boolean | 是否全部存在 |
| `data.signals[]` | array | 校验结果 |
| `data.signals[].signal` | string | 信号 |
| `data.signals[].status` | string | `ok` 或 `not_found` |
| `error.code` | string | 缺失时 `SIGNAL_NOT_FOUND` |

### `list.diff`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.diff_time` | string | 第一个不同时间或 `(no diff found)` |
| `data.time` | string | 同 diff_time |
| `data.resolved_time_range` | object | begin/end 解析 |

### `list.export`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | list 名 |
| `summary.signal_count` | number | 导出信号数 |
| `summary.row_count` | number | 导出总行数 |
| `summary.format` | string | 导出格式 |
| `data.output_dir` | string | 输出目录 |
| `data.manifest_file` | string | manifest JSON 路径 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.signals[]` | array | 每个导出信号的文件和统计 |

`data.signals[]` item 常见字段：`index`、`signal`、`file`、`row_count`、`width`、`word_count`、`columns`。

## 8. Event 命令

### `event.config.load`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | config 名 |
| `summary.status` | string | `loaded` |
| `data.config` | object | event config |

event config 字段：`name`、`clock`、`rst_n`、`edge`、`sample_point`、`signals`、`fields`。`sample_point` 仅在 `edge:"posedge"` 或 `edge:"dual"` 时出现；`fields.<field>` 包含 `signal`、`left`、`right`。

### `event.config.list`

不传 `args.name`：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.count` | number | event config 数 |
| `data.events[]` | array | event config 列表 |

传 `args.name`：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | config 名 |
| `data.config` | object | event config |

### `event.find`

表达式支持 `!`、`&&`、`||`、`==`、`!=`、`<`、`<=`、`>`、`>=`；比较任一侧含 X/Z 时结果为 unknown，不作为命中事件。

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | config 名 |
| `summary.begin` | string | begin TimeSpec |
| `summary.end` | string | end TimeSpec |
| `summary.event_count` | number | 返回事件数，最多 1 |
| `summary.first` | string | 第一条事件时间 |
| `summary.last` | string | 最后一条事件时间 |
| `data.examples[]` | array | compact 下事件样本 |
| `data.events[]` | array | preview 或 verbose |

### `event.export`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | config 名 |
| `summary.begin` | string | begin |
| `summary.end` | string | end |
| `summary.event_count` | number | 返回/限制后事件数 |
| `summary.first` | string | 第一条时间 |
| `summary.last` | string | 最后一条时间 |
| `summary.aggregate_count` | number | aggregate count |
| `summary.group_count` | number | group_by 组数 |
| `summary.limited` | boolean | aggregate 是否受 `line_limit` 影响 |
| `data.examples[]` | array | compact 默认 |
| `data.events[]` | array | preview 或 verbose |
| `data.aggregate` | object | aggregate 请求时存在 |
| `data.resolved_time_range` | object | verbose |

event item 常见字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `time` | string | 事件时间 |
| `time_ps` | number | 数值时间 |
| `signals` | object | alias -> value |
| `fields` | object | field -> value |
| `context` | object | context window 请求时的上下文 |

## 9. APB 命令

### `apb.config.load` / `apb.config.list`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | APB config 名 |
| `summary.status` | string | load 时为 `loaded` |
| `data.config` | object | APB config |

APB config 字段：`name`、`paddr`、`pwdata`、`prdata`、`pwrite`、`penable`、`psel`、`clock`、`rst_n`、`edge`、`sample_point`。`sample_point` 仅在 `edge:"posedge"` 或 `edge:"dual"` 时出现。

### `apb.query`

计数查询时底层 data 可能只有：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | APB config 名 |
| `data.count` | number | read/write transaction 数 |

具体 transaction 查询时：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | APB config 名 |
| `data.time` | string | transaction 时间 |
| `data.type` | string | `WR` 或 `RD`，cursor 风格查询时常见 |
| `data.addr` | string | 地址，`'h...` |
| `data.data` | string | 数据，`'h...` |

### `apb.cursor`

`apb.cursor` 使用 `args.op` 选择 `begin`、`next`、`pre`、`last`，返回字段同具体 transaction：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | APB config 名 |
| `data.time` | string | 当前 transaction 时间 |
| `data.type` | string | `WR` 或 `RD` |
| `data.addr` | string | 地址 |
| `data.data` | string | 数据 |

### `apb.transfer_window`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.transaction_count` | number | wrapper 从 data 提取 |
| `data.name` | string | config 名 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.transaction_count` | number | 返回 transaction 数 |
| `data.truncated` | boolean | 是否截断 |
| `data.transactions[]` | array | APB transaction |

`transactions[]` item：`time`、`time_ps`、`type`、`addr`、`data`。

## 10. AXI 命令

### `axi.config.load` / `axi.config.list`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | AXI config 名 |
| `summary.status` | string | load 时为 `loaded` |
| `data.config` | object | AXI config |

AXI config 字段：`name`、`awaddr`、`awid`、`awlen`、`awsize`、`awburst`、`awvalid`、`awready`、`wdata`、`wstrb`、`wlast`、`wvalid`、`wready`、`bid`、`bresp`、`bvalid`、`bready`、`araddr`、`arid`、`arlen`、`arsize`、`arburst`、`arvalid`、`arready`、`rid`、`rdata`、`rresp`、`rlast`、`rvalid`、`rready`、`clock`、`rst_n`、`edge`、`sample_point`。`sample_point` 仅在 `edge:"posedge"` 或 `edge:"dual"` 时出现。

### `axi.query`

计数查询可能返回：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | AXI config 名 |
| `data.count` | number | transaction 数 |

具体 transaction：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | AXI config 名 |
| `data.addr_time` | string | address phase 时间 |
| `data.type` | string | `WR` 或 `RD` |
| `data.id` | string | AXI id |
| `data.addr` | string | 地址 |
| `data.len` | string | len |
| `data.size` | string | size |
| `data.burst` | string | burst |
| `data.beats` | number | beat 数 |
| `data.first_data_time` | string | 首个 data beat 时间 |
| `data.last_data_time` | string | 最后 data beat 时间 |
| `data.resp_time` | string | response 时间 |
| `data.resp` | string | response |
| `data.data[]` | array | data beats |
| `data.wstrb[]` | array | write strobes |

### `axi.cursor`

`axi.cursor` 使用 `args.op` 选择 `begin`、`next`、`pre`、`last`，返回字段同具体 transaction。

### `axi.analysis`

latency/osd 由底层 analyzer 返回，常见字段：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | AXI config 名 |
| `data` | object | latency 或 outstanding 统计 |
| `data.count` | number | 样本/事务数 |
| `data.min` / `data.max` / `data.avg` | number | latency 类统计可能出现 |
| `data.samples[]` | array | osd/latency 样本可能出现 |

### `axi.export`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.name` | string | AXI config 名 |
| `summary.write_count` | number | 导出 write transaction 数 |
| `summary.read_count` | number | 导出 read transaction 数 |
| `summary.total_count` | number | 总 transaction 数 |
| `summary.format` | string | 导出格式 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.scan_begin` | string | 实际扫描 begin |
| `data.scan_end` | string | 实际扫描 end |
| `data.write_file` | string | write 导出文件 |
| `data.read_file` | string | read 导出文件 |
| `data.meta_file` | string | meta JSON 路径 |

### `axi.request_response_pair`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.transaction_count` | number | transaction 数 |
| `data.name` | string | config 名 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.transaction_count` | number | 返回 transaction 数 |
| `data.truncated` | boolean | 是否截断 |
| `data.transactions[]` | array | AXI transaction |

`transactions[]` item 扩展 `axi.query` transaction，并额外包含：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `match_time` | string | range 匹配时间 |
| `match_time_ps` | number | 数值匹配时间 |
| `latency_ps` | number | response - address |

### `axi.latency_outlier`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.transaction_count` | number | 输入窗口 transaction 数 |
| `data.name` | string | config 名 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.transaction_count` | number | transaction 数 |
| `data.truncated` | boolean | 是否截断 |
| `data.outlier_count` | number | outlier 数 |
| `data.outliers[]` | array | latency_ps 降序 top N transaction |

### `axi.outstanding_timeline`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.sample_count` | number | sample 数 |
| `data.name` | string | config 名 |
| `data.sample_count` | number | sample 数 |
| `data.truncated` | boolean | 是否截断 |
| `data.samples[]` | array | outstanding 样本 |
| `data.samples[].time` | string | 时间 |
| `data.samples[].time_ps` | number | 数值时间 |
| `data.samples[].read` | number | read outstanding |
| `data.samples[].write` | number | write outstanding |

### `axi.channel_stall`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.sample_count` | number | 因 data 有 sample_count 而提取 |
| `data.name` | string | AXI config 名 |
| `data.channel` | string | `aw`、`w`、`b`、`ar`、`r` |
| `data.sample_count` | number | clock sample 数 |
| `data.transfer_count` | number | transfer 数 |
| `data.max_stall_cycles` | number | 最大 stall cycles |
| `data.ready_without_valid_cycles` | number | ready-only cycles |
| `data.data_stability_violations` | number | 当前固定 0 |
| `data.truncated` | boolean | 是否截断 |
| `data.findings[]` | array | long stall findings |

## 11. Verify / Expr / Window / Signal 命令

### `verify.conditions`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.verdict` | string | `pass` 或 `fail` |
| `summary.condition_count` | number | 条件数 |
| `summary.all_passed` | boolean | 是否全过 |
| `summary.passed` | number | pass 数 |
| `summary.failed` | number | fail 数 |
| `summary.unknown` | number | unknown 数 |
| `data.checks[]` | array | compact 下仅 failed/unknown；verbose 下全部 |
| `data.resolved_time` | object | verbose |

check item：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `signal` | string | 信号 |
| `time` | string | 时间 |
| `op` | string | `==` 或 `!=` |
| `expected` | string | 期望值 |
| `observed` | object | 观测 value |
| `status` | string | `pass`、`fail`、`unknown` |
| `known` | boolean | 是否可判定 |
| `pass` | boolean/null | 判定结果 |
| `error` | string | 读取失败原因 |

### `expr.eval_at`

wrapper 直接实现或 server 实现时字段略有差异，统一读取：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.expr` | string | 表达式 |
| `summary.expr_value` | boolean/null | 结果 |
| `summary.status` | string | `true`、`false`、`unknown` |
| `summary.known` | boolean | 是否已知 |
| `data.expr` | string | server 实现存在 |
| `data.time` | string | server 实现存在 |
| `data.time_ps` | number | server 实现存在 |
| `data.resolved_time` | object | wrapper 实现存在 |
| `data.status` | string | server 实现存在 |
| `data.known` | boolean | server 实现存在 |
| `data.expr_value` | boolean/null | server 实现存在 |
| `data.operands[]` | array | 操作数 |
| `data.unknown_count` | number | wrapper 实现存在 |

operand item：`alias`、`signal`、`value`、`error`。

### `window.verify`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.all_passed` | boolean | 窗口是否全过 |
| `summary.sample_count` | number | sample 数 |
| `summary.failed_samples` | number | fail samples |
| `summary.unknown_samples` | number | unknown samples |
| `data.all_passed` | boolean | 同 summary |
| `data.sample_count` | number | sample 数 |
| `data.failed_samples` | number | fail samples |
| `data.unknown_samples` | number | unknown samples |
| `data.truncated` | boolean | 是否截断 |
| `data.conditions[]` | array | 条件统计 |
| `data.resolved_time_range` | object | range 解析 |

condition item：`expr`、`mode`、`passed`、`pass_samples`、`failed_samples`、`unknown_samples`。

### `signal.changes`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.transition_count` | number | 兼容字段，等同 actual transition 数 |
| `summary.returned_change_rows` | number | 实际匹配到的 value-change rows；可能包含 initial value |
| `summary.includes_initial_value` | boolean | rows 是否包含窗口起点 initial value |
| `summary.actual_transition_count` | number | 不含 initial value 的真实跳变数 |
| `summary.semantic_note` | string | 解释 row count 与周期统计的语义差异 |
| `data.signal` | string | 信号 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.changes[]` | array | changes；compact 默认不返回，使用 `line_limit` 控制 preview，更多内容使用 export |
| `data.transition_count` | number | 兼容字段，等同 actual transition 数 |
| `data.returned_change_rows` | number | 匹配到的 rows 数 |
| `data.includes_initial_value` | boolean | 是否包含 initial value |
| `data.actual_transition_count` | number | 真实跳变数 |
| `data.semantic_note` | string | 语义提示 |
| `data.truncated` | boolean | 是否截断 |
| `data.initial_value` | object | 初始值 |
| `data.final_value` | object | 最终值 |
| `data.first_change` | string | 第一变化 |
| `data.last_change` | string | 最后变化 |
| `data.resolved_time_range` | object | range 解析 |

change item：`time`、`time_ps`、`value`。

### `signal.stability`

继承 `signal.changes` 的多数 data 字段，并额外：

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `data.stable` | boolean | 是否稳定 |
| `data.value` | object | 稳定时的值 |
| `data.first_change_time` | string | 首次非初始值变化时间 |

### `signal.statistics`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.sampling_mode` | string | `clock_edge` 或 `raw_value_changes` |
| `summary.sample_count` | number | sample 数 |
| `summary.transition_count` | number | transition 数 |
| `summary.high_cycles` | number/null | clock-sampled 高周期；raw 模式可能为空 |
| `summary.low_cycles` | number/null | clock-sampled 低周期；raw 模式可能为空 |
| `data.signal` | string | 信号 |
| `data.clock` | string | clock |
| `data.sampling_mode` | string | `clock_edge` 或 `raw_value_changes` |
| `data.edge` | string | `posedge`、`negedge` 或 `dual`；默认 `negedge` |
| `data.sample_point` | string | `before` 或 `after`；仅 posedge/dual 需要，posedge 默认推荐 `before` |
| `data.sample_time_semantics` | string | 返回的时间为真实采样时间 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.sample_count` | number | sample 数 |
| `data.known_count` | number | known 样本 |
| `data.unknown_count` | number | unknown 样本 |
| `data.transition_count` | number | transition 数 |
| `data.truncated` | boolean | 是否截断 |
| `data.first` | number | 第一个已知值 |
| `data.final` | number | 最后已知值 |
| `data.min` | number | 最小值 |
| `data.max` | number | 最大值 |
| `data.low_cycles` | number | 0 cycles |
| `data.high_cycles` | number | 单 bit 高 cycles |
| `data.high_ratio` | number | high_cycles / known_count |
| `data.first_change_time` | string | 首次变化 |
| `data.last_change_time` | string | 最后变化 |
| `data.activity.high_burst_count` | number | 高电平 burst 数 |
| `data.activity.first_high_time` | string/null | 第一次 high 时间 |
| `data.activity.last_high_time` | string/null | 最后一次 high 时间 |
| `data.activity.last_fall_time` | string/null | 最后一次 fall 时间 |
| `data.activity.max_high_cycles` | number/null | clock 模式下最大连续 high cycles |

### `counter.statistics`

`counter.statistics` response schema 当前对 `summary/data` 较宽松；以下字段来自当前 basic response 与 runtime 输出。

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.sample_count` | number | clock sample 数 |
| `summary.valid_count` | number | valid sample 数 |
| `summary.min_value` | string | 最小计数值 |
| `summary.max_value` | string | 最大计数值 |
| `summary.average_value` | string | 平均值 |
| `data.clock` | string | clock |
| `data.edge` | string | sampling edge |
| `data.sample_point` | string | posedge/dual 的 before/after 采样点 |
| `data.sampling_mode` | string | 固定为 `clock_edge` |
| `data.sample_time_semantics` | string | 时间字段表示真实采样时间 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.valid_false_count` | number | valid 为 false 的 sample 数 |
| `data.unknown_count` | number | unknown sample 数 |
| `meta.truncated` | boolean | 仅在因 `line_limit` 截断时出现，值为 `true` |
| `data.cnt` | string/object | counter 表达式或信号 |
| `data.vld` | string/object | valid 表达式或信号 |
| `data.min_count` | number | 最小值出现次数 |
| `data.max_count` | number | 最大值出现次数 |
| `data.min_first_time` | string | 最小值首次时间 |
| `data.max_first_time` | string | 最大值首次时间 |

### `sampled_pulse.inspect`

`sampled_pulse.inspect` 用于解释 valid raw pulse 是否被 clock edge 采到，以及 payload 在未采样窗口附近是否变化。通用 X/Z、glitch、stuck 扫描使用 `detect_abnormal`。

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.sample_count` | number | clock sample 数 |
| `summary.sampled_high_cycles` | number | valid sampled high cycles |
| `summary.raw_valid_transition_count` | number | raw valid transitions |
| `summary.payload_transition_count` | number | payload transitions |
| `summary.risk_count` | number | risk 数 |
| `data.clock` | string | clock |
| `data.valid` | string | valid signal |
| `data.payloads[]` | array | payload alias/signal |
| `data.edge` | string | `posedge`、`negedge` 或 `dual`；默认 `negedge` |
| `data.sample_point` | string | `before` 或 `after`；仅 posedge/dual 需要，posedge 默认推荐 `before` |
| `data.sample_time_semantics` | string | 返回的时间为真实采样时间 |
| `data.begin` | string | begin |
| `data.end` | string | end |
| `data.sample_count` | number | sample 数 |
| `data.sampled_high_cycles` | number | sampled high |
| `data.sampled_low_cycles` | number | sampled low |
| `data.sampled_unknown_cycles` | number | sampled unknown |
| `data.raw_valid_transition_count` | number | raw valid changes |
| `data.payload_transition_count` | number | payload changes |
| `data.risk_count` | number | findings 数加截断哨兵 |
| `data.first_sampled_high_time` | string/null | first high |
| `data.last_sampled_high_time` | string/null | last high |
| `data.first_risk` | object/null | 第一条风险 |
| `data.findings[]` | array | risk findings |
| `data.truncated` | boolean | 是否截断 |

finding type：

| type | 字段 |
| --- | --- |
| `unsampled_valid_pulse` | `severity`、`raw_begin`、`raw_end`、`previous_sample_edge`、`next_sample_edge`、`nearest_sample_edge`、`raw_valid`、`sampled_valid`、`sampled_payloads`、`reason` |
| `payload_changed_without_sampled_valid` | `severity`、`raw_time`、`previous_sample_edge`、`next_sample_edge`、`nearest_sample_edge`、`payload`、`sampled_valid`、`sampled_payloads`、`reason` |

### `detect_abnormal`

`detect_abnormal` 是 raw waveform abnormal smoke 扫描，负责 `unknown_xz`、周期内异常短脉冲/毛刺 `glitch`、长时间不变 `stuck`。它支持 `args.signals` 传多个信号。valid/ready 协议里的合法 idle/backpressure 不应只凭 `stuck` finding 判为 bug；packed struct / aggregate payload 的 knownness 结论必须优先检查最终 leaf signal path，例如 `top.u.payload.opcode`，不要期待 xdebug 自动展开 struct。

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.finding_count` | number | finding 数 |
| `data.finding_count` | number | finding 数 |
| `data.findings[]` | array | findings |
| `data.truncated` | boolean | 是否达到 `line_limit` |

finding types：

| type | 字段 |
| --- | --- |
| `unknown_xz` | `signal`、`severity`、`time`、`value` |
| `glitch` | `signal`、`severity`、`time`、`pulse_width` |
| `stuck` | `signal`、`severity`、`begin`、`end`、`duration`、`value` |

### `handshake.inspect`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.transfer_count` | number | transfer 数 |
| `summary.max_stall_cycles` | number | 最大 stall |
| `data.sample_count` | number | sample 数 |
| `data.transfer_count` | number | transfer 数 |
| `data.max_stall_cycles` | number | 最大 stall |
| `data.ready_without_valid_cycles` | number | ready without valid cycles |
| `data.data_stability_violations` | number | stalled data 变化数 |
| `data.truncated` | boolean | 是否截断 |
| `data.findings[]` | array | long stall findings |

long stall finding：`type:"long_stall"`、`severity`、`begin`、`end`、`cycles`。

## 12. Stream 命令

stream response schema 当前主要约束 envelope，具体字段以 runtime 和 response example 为准。

### `stream.config.load`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.loaded` | number | 加载 stream 数 |
| `summary.mode` | string | load 模式 |
| `data.streams[]` | array | 已加载 stream 名 |
| `data.issues[]` | array | 配置问题 |

### `stream.config.list`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.count` | number | stream 配置数量 |
| `data.streams[]` | array | stream 摘要列表 |

`data.streams[]` item 常见字段：`name`、`clock`、`edge`、`handshake`、`packet`、`field_count`。

### `stream.show`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.stream` | string | stream 名 |
| `summary.handshake` | string | 握手类型 |
| `summary.packet_enabled` | boolean | 是否启用 packet 语义 |
| `data.config` | object | stream 配置 |
| `data.issues[]` | array | 配置问题 |

### `stream.validate`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.stream` | string | stream 名 |
| `summary.ok` | boolean | 静态/动态校验是否通过 |
| `data.issues[]` | array | 校验问题 |
| `data.dynamic` | object | 可选动态统计，例如 `transfer_count` |

### `stream.query`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.stream` | string | stream 名 |
| `summary.transfer_count` | number | transfer 数 |
| `summary.stall_cycles` | number | stall cycles |
| `summary.packet_count` | number | packet 数 |
| `summary.match_count` | number | `match_field` 命中数 |
| `summary.field_scope` | string | `beat`、`stable` 或 `any` |
| `summary.truncated` | boolean | 是否截断 |
| `data.query` | string | query 类型 |
| `data.rows[]` | array | transfer/match rows |
| `data.row` | object | first/last 类 query 的单行 |
| `data.packets[]` | array | packet window |
| `data.packet` | object | 单个 packet |

`match_field` 的 request 写法固定为 `match.field/op/value`，不要写成 `match: {"opcode": "8'h5a"}`。

### `stream.export`

| 路径 | 类型 | 含义 |
| --- | --- | --- |
| `summary.stream` | string | stream 名 |
| `summary.transfer_count` | number | 导出 transfer 数 |
| `summary.truncated` | boolean | 是否截断 |
| `data.output_file` | string | 导出文件 |
| `data.meta_file` | string | meta JSON 路径 |
| `data.kind` | string | 导出 kind |
| `data.format` | string | 导出格式 |
| `data.row_count` | number | 导出行数 |

## 13. Compact/Full 差异速查

| action | compact 默认保留 | 需要 include/full 的字段 |
| --- | --- | --- |
| `trace.driver/load` | summary + paths/source_context/signal_path | 不恢复旧内部 trace/AST 字段 |
| `source.context` | file/line/symbol/context_kind/enclosing | context 源码行 |
| `value.at` | string value + known | resolved_time、raw value object |
| `value.batch_at/list.value_at` | values map | per-signal raw objects、resolved_time |
| `scope.list` | signals_preview | signals 全量 |
| `event.export` | examples + aggregate | events rows |
| `verify.conditions` | failed/unknown checks；pass 可极简 | passed checks、resolved_time |
| `signal.changes` | bounded changes | 全量 changes |
| `axi/apb` | summary + returned query payload | 全量 transactions/beats/accesses 需 include 或 full |
| `stream.*` | summary + query/export/load payload | stream schema 较宽松，字段以 runtime/example 为准 |

## 14. 已实现 Action 总表

顶层/通用：

```text
actions
batch
schema
```

session：

```text
session.close
session.doctor
session.gc
session.kill
session.list
session.open
```

设计侧：

```text
expr.normalize
signal.canonicalize
signal.resolve
source.context
trace.driver
trace.load
```

波形侧：

```text
apb.config.list
apb.config.load
apb.cursor
apb.query
apb.transfer_window
axi.analysis
axi.export
axi.channel_stall
axi.config.list
axi.config.load
axi.cursor
axi.latency_outlier
axi.outstanding_timeline
axi.query
axi.request_response_pair
counter.statistics
cursor.delete
cursor.get
cursor.list
cursor.set
cursor.use
detect_abnormal
event.config.list
event.config.load
event.export
event.find
expr.eval_at
handshake.inspect
list.add
list.create
list.delete
list.diff
list.export
list.show
list.validate
list.value_at
sampled_pulse.inspect
scope.list
scope.roots
signal.changes
signal.stability
signal.statistics
rc.generate
value.at
value.batch_at
verify.conditions
window.verify
stream.config.load
stream.config.list
stream.show
stream.validate
stream.query
stream.export
```

联合侧：

```text
trace.active_driver
trace.active_driver_chain
```
