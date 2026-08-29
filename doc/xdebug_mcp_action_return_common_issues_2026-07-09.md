# xdebug MCP Action 返回通病与修改建议（2026-07-09）

本文件汇总逐项评审中反复出现的问题。每发现一类通病就追加记录，并给出修改建议。

## 当前通病

### 1. MCP raw_request 失败时结构化错误被包进 `stdout_tail`

证据：`actions` action 传入非法 `args.filter` 时，backend 生成了可恢复错误：

```text
invalid_arg: args.filter
expected: no additional properties allowed
correct_example: {"api_version":"xdebug.v1","action":"actions","args":{}}
```

但 MCP `xverif_debug_raw_request` 顶层返回：

```text
code: XVERIF_CLI_FAILED
message: xdebug exit 1
stdout_tail: <backend xout error>
```

影响：

- AI 不能直接读取顶层 `invalid_arg`、`expected`、`correct_example`。
- 需要解析 `stdout_tail` 文本，违背“参数错误直接给结构化修复提示”的目标。

修改建议：

- raw_request wrapper 捕获 backend `ok:false` 或 xout error 时，解析并提升为结构化 `backend_error`。
- 顶层保留 transport/CLI 失败信息，但把参数修复字段复制到顶层或 `backend_error`：
  - `backend_error.code`
  - `backend_error.invalid_arg`
  - `backend_error.expected`
  - `backend_error.allowed_values`
  - `backend_error.did_you_mean`
  - `backend_error.correct_example`
- 对 wrapper 自身失败和 backend 参数失败做区分，例如 `WRAPPER_CLI_FAILED` vs `BACKEND_INVALID_REQUEST`。

### 2. handler 层参数错误缺少 `invalid_arg`、`allowed_values`、`correct_example`

证据：`schema` action 的 `args.kind:"bad_kind"` 返回：

```text
message: schema args.kind must be request or response
recoverable: true
```

但没有：

```text
invalid_arg: args.kind
allowed_values: ["request", "response"]
correct_example: {"api_version":"xdebug.v1","action":"schema","args":{"action":"value.batch_at","kind":"request"}}
```

影响：

- 人能读懂，但 AI 难以统一按字段修复。
- 和 schema 层错误返回风格不一致。

修改建议：

- 所有 handler 语义校验失败统一补齐：
  - `invalid_arg`
  - `expected`
  - `allowed_values`（如适用）
  - `did_you_mean`（如适用）
  - `correct_example`
- handler 层错误示例不要保留错误值，应给可复制的修正值。

### 3. schema xout 对复杂 JSON schema 的层级表达不够清晰

证据：`schema(value.batch_at, request)` 的 xout 中，`signals` 字段以 `oneOf` 表格形式显示，但字段名不明显；`additionalProperties:false` 的归属也容易误读。

影响：

- AI 可能漏读字段名或误判约束归属。
- 对复杂 action，默认 xout 不适合做严格 schema source-of-truth。

修改建议：

- schema action 的 xout 对每个 property 使用固定格式：
  - `property: args.signals`
  - `type: array|string-map`
  - `required: yes/no`
  - `allowed_values: ...`
  - `additional_properties: false` 明确标注归属对象。
- MCP skill 中继续强调：严格字段生成优先用 `xverif_debug_get_schema` 结构化返回。

### 4. batch child failure 缺少 child 定位信息

证据：`batch` 中第一个 child request 失败时，默认返回只包含：

```text
code: BATCH_PARTIAL_FAILURE
message: one or more child requests failed
```

缺少：

```text
failed_index
failed_action
child_error.code
child_error.invalid_arg
child_error.message
child_error.correct_example
```

影响：

- AI 无法直接知道哪条 child request 需要修。
- 用户必须切换 JSON 或逐条重放，违背 batch 减少多轮调用的目的。

修改建议：

- `BATCH_PARTIAL_FAILURE` 默认 xout/error 至少展示前 N 个失败 child 的 index、action、error code、invalid_arg 和 correct_example。
- JSON response 保留完整 child error；xout 可以 compact，但不能只给总失败。

### 5. 资源路径错误返回 CLI usage，缺少具体 path 诊断

证据：`session.open` 使用不存在的 FSDB 路径时返回：

```text
code: INVALID_REQUEST
message: Usage: open [-dbdir <simv.daidir>] [-fsdb <waves.fsdb>] ...
recoverable: true
```

缺少：

```text
invalid_arg: fsdb 或 target.fsdb
expected: existing FSDB file path
received: <具体路径>
suggestion: check path, working directory, or use absolute path
```

影响：

- 用户和 AI 只能看到 usage，无法确定是 fsdb 路径不存在、权限问题、格式问题还是 target 位置问题。
- 容易误判为 CLI 参数格式错误，而不是资源不可访问。

修改建议：

- open/resource resolver 在路径不存在、不可读、类型不匹配时返回专门错误码：
  - `FSDB_NOT_FOUND`
  - `DAIDIR_NOT_FOUND`
  - `RESOURCE_NOT_READABLE`
- 错误字段包含 `invalid_arg`、`path`、`cwd`、`expected` 和 `correct_example`。

### 6. MCP query 可调用 native `session.open`，容易混淆两套 session 生命周期

证据：`xverif_debug_query(session_id=<mcp-session>, action="session.open", args={"name":"nested_open"})` 会成功打开一个 native backend session，并返回 native `session.open` xout。

影响：

- MCP 用户可能误以为这是推荐的 session open 方式。
- native session 不等同于 MCP wrapper session，生命周期和清理入口不同，容易产生残留。

修改建议：

- MCP `xverif_debug_query` 对 session lifecycle action 增加 warning：
  - `session.open` 推荐改用 `xverif_debug_session_open`
  - `session.close/kill/list/gc/doctor` 推荐先使用 MCP session tools 或明确 raw/native 意图
- 或在 MCP query 层默认拒绝 `session.open`，除非显式 `allow_native_session_action:true`。

### 6b. MCP query 可调用 native `session.close`，会误伤当前 backend session

证据：`xverif_debug_query(session_id="session_open_review_20260709", action="session.close", args={})` 实测关闭了当前 query 绑定的 native backend session。

影响：

- MCP wrapper session manager 可能仍持有这个 session alias，但 backend native session 已被关闭。
- 后续 query 可能出现 SESSION_LOST/SESSION_NOT_FOUND。
- AI 可能误以为 `session.close` 是 MCP 推荐关闭方式，而不是 `xverif_debug_session_close`。

修改建议：

- `xverif_debug_query` 默认拒绝 native lifecycle action：`session.open`、`session.close`、`session.kill`，除非显式 opt-in。
- 返回错误时提供正确 MCP 示例：

```json
{"tool":"xverif_debug_session_close","args":{"name":"case_a"}}
```

- 如果保留 native lifecycle action，应返回 warning 并同步 MCP manager 状态，或明确说明未同步。

### 7. MCP query 的 `correct_example` 仍是 native envelope

证据：通过 `xverif_debug_query(action="session.list", args={"filter":"alive"})` 触发 schema 错误时，返回的 `correct_example` 是：

```json
{"api_version":"xdebug.v1","action":"session.list","target":{"session_id":"case_a"},"args":{}}
```

但 MCP query 用户真正需要的是：

```json
{"session_id":"case_a","action":"session.list","args":{}}
```

影响：

- AI 可能把 `api_version/target` 误写进 MCP query 的 inner `args`。
- 与拆分后的 `xverif-mcp` skill 参数壳要求不一致。

修改建议：

- MCP wrapper 在返回 backend `correct_example` 时追加 `mcp_correct_example`。
- 对 `xverif_debug_query`，形态为：
  - `session_id`
  - `action`
  - `args`
  - `limits`
  - `output`
- 保留 native `correct_example`，但明确标为 `native_correct_example`。

### 7b. `correct_example` 可能包含已不推荐或冲突字段

证据：`session.kill` 对非法 `args.force` 的 schema 错误返回中，`correct_example` 同时包含：

```json
{
  "target": {"session_id": "case_a"},
  "args": {"session_id": "case_a"}
}
```

问题：

- `target.session_id` 和 `args.session_id` 同时出现，容易让 AI 误以为两者都需要。
- 这与当前“session 选择不写入 action args”的设计方向冲突。

修改建议：

- `correct_example` 必须由 action-specific schema/current contract 生成或校验。
- 对 session lifecycle action，native 示例只保留 `target.session_id`；MCP 示例只保留 MCP tool 参数 `session_id` 或 `name`。
- 增加测试：所有 error `correct_example` 必须能通过当前 schema，并且不得包含 deprecated alias。

### 8. MCP session list 与 native `session.list` 范围不同但名称相似

证据：

- `xverif_debug_session_list(include_native=true)` 只返回 MCP manager 当前托管 session。
- `xverif_debug_query(action="session.list")` 返回 xdebug native registry，包含历史 native session 和底层 transport 字段。

影响：

- 用户可能以为两者等价。
- AI 可能用 native list 结果去关闭 MCP session，或反过来遗漏 native 残留。

修改建议：

- MCP tool help 明确：
  - `xverif_debug_session_list`：MCP wrapper session manager。
  - `session.list`：xdebug native session registry。
- native `session.list` xout 增加标题或 warning：`scope: native xdebug registry, not MCP manager`。

### 9. compact xout 中重复 summary/health 信息

证据：`session.doctor` 成功返回中出现：

- 顶部 `summary.session_id/mode/healthy`
- `health.api_version/request_id/ok/action`
- 后部 `summary.id/session_id/healthy/status/message`
- 后部 `health.id/session_id/healthy/status/message`

影响：

- compact 输出变长，AI 需要过滤重复字段。
- 关键信息 `healthy/status/message` 被重复展示，反而降低扫描效率。

修改建议：

- compact xout 只保留：
  - `summary.session_id`
  - `summary.healthy`
  - `summary.status`
  - `summary.message`
  - 关键 resource path 和 pid/transport
- `api_version/request_id/raw session metadata/dev/inode` 移到 full/debug verbosity。

### 10. handler 层 `correct_example` 可能回显错误输入

证据：`cursor.set` 使用 `args.time:"not_a_time"` 时，handler 返回：

```text
code: ACTION_FAILED
message: Invalid time 'not_a_time'
invalid_arg: args.time
expected: time string such as 10ns, 100ps, or max for end
correct_example.args.time: "not_a_time"
```

影响：

- AI 会把 `correct_example` 当成可执行修复模板，但模板仍包含错误时间。
- 这比没有 `correct_example` 更危险，因为它会强化错误调用。

修改建议：

- handler 层生成 `correct_example` 前必须做 schema 校验和语义 sanity check。
- 对解析类错误，示例必须替换为一个已知合法值，例如 `100ns`、`10ns`、`max`。
- 增加测试：所有错误返回中的 `correct_example` 不得包含触发本次错误的非法值，除非字段是用户自定义名称且本身合法。

### 11. MCP query 传空 `args:{}` 时可能退化成 native envelope 缺少 `args`

证据：`cursor.get` 通过 MCP query 传 `args:{}`，后端返回：

```text
invalid_arg: args
message: required property 'args' not found in object
```

但传 `args:{"time_unit":"ns"}` 时才返回更准确的：

```text
invalid_arg: args.name
message: required property 'name' not found in object
```

影响：

- AI 明明传了 `args:{}`，却被告知缺少整个 `args`，会误判 MCP 壳层参数位置。
- required 子字段错误不稳定，降低自动修复能力。

修改建议：

- MCP wrapper 构造 native envelope 时保留空 dict，不要把空 `args:{}` 当作未提供。
- 对 action schema required 包含 `args` 的情况，MCP 层可以在本地预检空 args，并返回 `invalid_arg` 指向第一个缺失 required 子字段。
- 增加 MCP wrapper 单测：`xverif_debug_query(action="cursor.get", args={})` 必须报 `args.name` 缺失，而不是 `args` 缺失。

### 12. 资源/状态类 compact xout 默认暴露过多本机路径和文件系统字段

证据：`session.gc` 成功 xout 的 `before` 表格包含 `fsdb/socket_path/file_dir/server_host/server_pid/fsdb_mtime/fsdb_size/fsdb_dev/fsdb_inode` 等字段。

影响：

- 默认 compact 输出过宽，核心 cleanup 结论不突出。
- 用户可见回答中容易带出本机绝对路径。
- dev/inode/mtime 通常只对底层 transport 排障有用，不适合默认成功路径。

修改建议：

- compact 默认只显示 `session_id/mode/summary counts/reason/kill_ok`。
- 路径、inode、mtime、socket/file transport 细节放入 JSON full 或 `output.verbose:true`。
- 对 MCP 输出增加 `redacted_path` 或相对路径展示策略，报告/skill 中也避免传播本机绝对路径。

### 13. schema 允许的参数形态可能到 handler 层被拒绝

证据：`value.batch_at` request schema 允许：

```json
{"signals":{"a":"ai_complex_top.sig_a","b":"ai_complex_top.sig_b"}}
```

但通过 MCP query 调用时 handler 返回：

```text
code: MISSING_FIELD
message: args.signals[] and args.time are required
```

影响：

- AI 按 schema 构造的合法请求会在 handler 层失败。
- 错误 message 还暗示只接受 array，和 schema `oneOf(array, object)` 冲突。
- 这种问题无法只靠文档修复，必须 schema/runtime 收敛。

修改建议：

- 所有 action 增加 contract test：schema pass 的最小示例必须 handler accept，至少覆盖 `oneOf/anyOf` 每个分支。
- 对 `value.batch_at` 明确二选一：
  - runtime 支持 alias object，并在 response 中返回 alias/path。
  - 或 schema 移除 object 分支，只保留 array。
- handler 层 `MISSING_FIELD` 必须附 `invalid_arg`、`expected`、`schema_path`、`correct_example`。

### 14. 不存在 signal/clock 的 handler 错误缺少发现路径建议

证据：

- `value.at(clock:"top.clk")` 返回 `Clock signal not found: top.clk`，但 `correct_example` 回显同一个坏 clock。
- `value.at(signal:"ai_complex_top.no_such")` 返回 `SIGNAL_NOT_FOUND`，但没有 `invalid_arg`、候选 signal 或下一步 action。

影响：

- AI 知道路径错了，但不知道该调用 `scope.roots`、`scope.list`、`signal.resolve` 还是换 fixture。
- `correct_example` 回显坏路径会导致重复失败。

修改建议：

- path-not-found 类错误统一返回：
  - `invalid_arg`
  - `missing_path`
  - `suggestion`
  - `next_actions:["scope.roots","scope.list","signal.resolve"]`
  - 可选 `near_matches`
- `correct_example` 不得使用本次不存在的路径；若不知道真实路径，用占位符 `<existing_clock>` 并明确不是可直接执行值。

### 15. batch 类成功返回缺少 partial failure 汇总

证据：`value.batch_at` 中一个 signal 不存在时 action 仍成功，表格中该行显示 `signal_not_found`，但 summary 只有 `signal_count`。

影响：

- 这种设计对批量 debug 有价值，但 AI 必须扫完整表才能知道有部分失败。
- 自动化判断 `ok:true` 时可能误以为所有 signals 都成功。

修改建议：

- batch 类 response 增加统一 summary：

```text
summary:
  requested_count: 2
  ok_count: 1
  missing_count: 1
  partial_failure: true
```

- 对 missing 行保留表内标记，同时在 `warnings[]` 或 `findings[]` 中列出缺失 signal。

### 16. 额外字段错误缺少 `did_you_mean`

证据：`scope.list` 误传旧习惯字段 `args.depth` 时，返回：

```text
invalid_arg: args.depth
expected: no additional properties allowed
correct_example.args.path: ""
```

但 schema 真实字段是 `args.max_depth`。

影响：

- AI 知道 `depth` 不允许，但不知道应改成 `max_depth`。
- correct_example 没展示 `max_depth`，恢复路径不够直接。

修改建议：

- 对 additionalProperties 错误做字段名相似度匹配，返回 `did_you_mean`。
- `correct_example` 应覆盖同类常见误用，例如：

```json
{"session_id":"case_a","action":"scope.list","args":{"path":"top","max_depth":1}}
```

### 17. 查询类 action 的空成功结果缺少“空原因”语义

证据：`scope.list(path:"no_such_scope")` 返回 `ok` 且 `signals/scopes` 均为空，但没有说明 scope 是否存在。

影响：

- AI 无法区分：
  - scope 不存在
  - scope 存在但没有下级
  - 查询被截断或权限/数据源缺失
- 后续可能基于错误路径继续构造查询。

修改建议：

- 查询类 action 返回空结果时增加统一字段：

```text
summary:
  status: empty
  empty_reason: path_not_found | no_children | filtered_out | source_unavailable
```

- 对路径类 action 增加 `path_exists` 或 `resolved_path`。

### 18. 资源前置条件错误仍使用 CLI 语言，而不是 MCP 语言

证据：`signal.resolve` / `signal.canonicalize` 在 waveform-only MCP session 下返回：

```text
code: DESIGN_NOT_LOADED
message: design not loaded; open session with -dbdir
```

影响：

- MCP 用户不会直接传 `-dbdir`，而是调用 `xverif_debug_session_open(daidir=...)`。
- AI 可能把 CLI 参数混进 MCP query 的 inner args。

修改建议：

- resource prerequisite 错误同时返回 native 和 MCP 两种修复示例：

```json
{
  "missing_resource": "daidir",
  "native_hint": "open session with -dbdir <simv.daidir>",
  "mcp_correct_example": {
    "tool": "xverif_debug_session_open",
    "args": {"name": "case_a", "daidir": "<simv.daidir>"}
  }
}
```

### 19. MCP/tool-level success 与 domain-level success 没有统一标记

证据：`signal.resolve(signal:"no_such_signal")` 的 MCP tool 调用成功返回 xout，但 xout summary 内部显示：

```text
ok: false
status: not_found
count: 0
```

影响：

- AI 如果只看 MCP tool 是否报错，会把 domain not_found 当成成功解析。
- 不同 action 对“无结果”有时用 error，有时用 `ok:true + empty`，有时在 domain summary 里放 `ok:false`，语义不一致。

修改建议：

- 统一 response summary 字段：

```text
summary:
  status: ok | not_found | partial | empty | failed
  domain_ok: true | false
```

- MCP wrapper 对 xout 不必把 domain not_found 升级为 tool error，但应在 xout 第一屏显式展示 `status:not_found`。
- 文档明确每类 action 的 no-result 语义：错误、空成功、partial 成功或 domain not_found。

### 20. 已废弃/非推荐字段仍被 runtime 接受但没有 warning

证据：`signal.changes` schema 推荐 `time_range.begin/end`，顶层 `args.begin/end` 会正确报错并提示 `did_you_mean`。但 `time_range.from/to` 被 runtime 接受，并归一化为 `begin/end`，没有 warning。

影响：

- AI 会继续传播 `from/to` 旧写法。
- schema/source-of-truth 与 runtime 实际兼容面不一致，后续文档和测试难收敛。

修改建议：

- 如果保留兼容，所有 deprecated alias 必须返回 `warnings[]`：

```text
deprecated_args:
  time_range.from -> time_range.begin
  time_range.to -> time_range.end
```

- 如果不保留兼容，schema 和 runtime 都拒绝，并返回 `did_you_mean`。
- 增加 contract test：非推荐 alias 的行为必须是“拒绝”或“接受但 warning”，不能静默接受。

### 21. xout summary 层不统一，部分 action 把统计字段混在表格块里

证据：`signal.stability` 成功 xout 没有 `summary`，而是在 `changes` 块下混入：

```text
transition_count
truncated
stable
value
```

影响：

- AI 很难用统一方式读取 action 结论。
- `changes` 同时表示 row table 和统计字段，层级不清。

修改建议：

- 所有 action compact xout 第一屏必须有 `summary`。
- `summary` 至少包含 `status` 和该 action 的核心结论，例如 `stable/value/actual_transition_count`。
- 表格块只放 rows；统计字段放 summary 或 data。

### 22. 可疑但可执行的配置缺少 warning

证据：`counter.statistics` 使用同一个 signal 作为 `vld` 和 `cnt` 可以成功执行，返回统计结果，但没有 warning。

影响：

- AI 为了让 action 跑通可能构造语义不合理的请求，并把结果当成有效 debug 结论。
- 用户难以区分“工具成功执行”和“配置有实际分析意义”。

修改建议：

- 对明显可疑配置增加 semantic warnings，例如：
  - `vld_equals_cnt_may_be_unintended`
  - `clock_equals_data_may_be_unintended`
  - `empty_time_range`
  - `zero_valid_samples`
- warnings 不阻止执行，但必须在 compact xout 的 summary 附近展示。

### 23. schema 中的 object 类型缺少内部结构约束

证据：`counter.statistics.args.vld` 允许 string 或 object，但 object 分支没有要求 `expr/signals` 等内部字段；`correct_example` 却展示了复杂 object：

```json
{"vld":{"expr":"valid && ready","signals":{"valid":"top.valid","ready":"top.ready"}}}
```

影响：

- AI 按 schema 可能传任意 object，schema 通过后到 handler 层才失败。
- 错误反馈会晚一层，且更难知道 object 应该长什么样。

修改建议：

- 对所有允许 object 的 action 参数补全内部 schema：
  - required 字段
  - additionalProperties:false
  - 类型和示例
- 增加 schema-test：文档/错误示例中的 object 分支必须可通过 schema，明显非法 object 必须被 schema 拒绝。

### 24. 状态对象不存在时的 handler 错误不够可恢复

证据：

- `list.add(name:"no_such_list")` 返回 `code: ADD_FAILED`，`message` 只是 signal 名。
- `list.show/list.validate(name:"no_such_list")` 返回 `LIST_NOT_FOUND`，但只有 name 字符串。

影响：

- AI 无法判断应该先 `list.create`，还是拼错 list 名，还是 session 状态丢失。
- 同一类错误在不同 action 中 code 不一致：`ADD_FAILED` vs `LIST_NOT_FOUND`。

修改建议：

- 统一状态对象 not found 错误：

```json
{
  "code": "LIST_NOT_FOUND",
  "invalid_arg": "args.name",
  "missing_name": "no_such_list",
  "available_values": ["review_list"],
  "next_actions": ["list.show", "list.create"]
}
```

- `ADD_FAILED` 这类泛化 code 只用于真正 append 失败；list 不存在应返回 `LIST_NOT_FOUND`。

### 25. 状态变更类成功返回缺少变更后的完整摘要

证据：

- `list.create` 成功只返回 `name/status/created`，不返回初始 `signal_count`。
- `list.add` 成功只返回本次 signal，不返回追加后的 `signal_count` 或 `already_exists`。

影响：

- AI 需要额外调用 `list.show` 才能确认最终状态。
- 对重复 add/create 的语义不清楚。

修改建议：

- 状态变更类 action 成功返回统一包含：
  - `name`
  - `status`
  - `created/added/deleted`
  - `count_after`
  - `already_exists` 或 `was_present`

### 26. list index 语义没有显式说明

证据：`list.show` 表格 index 从 1 开始；`list.delete` 支持 `index`，但当前输出和 schema 没有明确 index base。

影响：

- AI 可能按 0-based index 删除错误 signal。

修改建议：

- `list.show` summary 增加 `index_base: 1`。
- `list.delete` schema description 明确 index 是 1-based 还是 0-based。
- index 越界错误返回 `valid_index_range`。

### 27. 同类旧字段错误在不同 action 中提示不一致

证据：

- `signal.changes(args.begin)` 返回 `did_you_mean: args.time_range.begin`。
- `list.diff(args.begin,args.end)` 返回缺少 `args.time_range`，没有指出 `begin/end` 应放进 `time_range`。

影响：

- AI 对同一类错误的恢复策略不能复用。
- 有的 action 能一次修正，有的 action 还需要猜。

修改建议：

- validator 对 additionalProperties + missing required 的组合做统一错误选择：
  - 如果额外字段有已知迁移目标，优先返回 `invalid_arg` 指向额外字段和 `did_you_mean`。
  - 同时可以保留 `missing_required`，但不要只报 missing object。
- 增加跨 action contract test：所有 `begin/end/from/to/output_file` 等迁移字段的错误提示格式一致。

### 28. list export index 与 list show/delete index 语义冲突

证据：

- `list.show` 显示 index 从 1 开始。
- `list.delete(index:3)` 删除第 3 个 signal 后返回 `removed:3`。
- `list.export` 的 signals 表 index 从 0 开始。

影响：

- AI 可能把 export 表中的 index 直接传给 `list.delete`，导致删错 signal。
- `removed:3` 容易被理解为删除了 3 个 item，而不是删除 index 3。

修改建议：

- list 管理 index 统一明确为 1-based 或 0-based。
- export 文件序号字段改名为 `file_index`，不要叫 `index`。
- delete 成功返回使用 `removed_index/removed_signal/count_after`，不要只用 `removed`。

### 29. output path 合同和 response 字段命名不一致

证据：`list.export` 入参为 `args.output.path`，成功返回是 `data.output_dir` 和 `manifest_file`。

影响：

- AI 可能困惑 `output.path` 期望文件还是目录。
- 旧字段 `output_file` 的错误没有 `did_you_mean:"args.output.path"`。

修改建议：

- 如果 `output.path` 实际是目录，schema description 写明 `output.path is an output directory`。
- response 同步输出 `output.path` 或 `output_dir` 与 schema 统一。
- 对 `output_file/output_dir/output_prefix` 类旧字段统一返回 `did_you_mean:"args.output.path"`。

### 30. config.load 类 action 对“配置内容字段误放 request args”的解释不足

证据：`event.config.load(args.clock)` 返回 additional property 错误，只说明 `args.clock` 不允许。

影响：

- AI 知道不能这么传，但不知道 clock/signals/rst_n 应该写进配置文件内容。
- 对需要 `*.config.load` 的 action，这类错误很常见。

修改建议：

- config.load 类 action 对配置内容字段误放 args 时，返回：

```json
{
  "invalid_arg": "args.clock",
  "suggestion": "clock/signals/rst_n belong in the config file content; request args only accept name/config_path/time_unit",
  "mcp_correct_example": {"session_id":"case_a","action":"event.config.load","args":{"name":"evt0","config_path":"xdebug/configs/event0.json"}}
}
```

- skill 文档中的 config.load workflow 和错误提示保持一致。

### 31. 表达式 alias 错误缺少可用 alias 列表

证据：`event.find(expr:"bad_alias")` 返回：

```text
code: EVENT_FAILED
message: Unknown alias in expression: bad_alias
```

影响：

- AI 知道表达式错了，但不知道当前 config/inline signals 中有哪些合法 alias。
- 容易继续猜字段名。

修改建议：

- expression action 的 unknown alias 错误统一返回：

```json
{
  "invalid_arg": "args.expr",
  "unknown_alias": "bad_alias",
  "available_aliases": ["vld", "rdy", "payload", "xz", "payload_lo"]
}
```

- 如果 alias 来自 config，附 `config_name`；如果来自 inline signals，附 `inline:true`。

### 32. action 名称含 export 但不接受 output path，容易误导

证据：`event.export` 不接受 `args.output.path`，错误只说 `args.output` 是 additional property。相比之下 `list.export` 使用 `args.output.path` 写文件。

影响：

- AI 会把所有 `*.export` action 统一理解为“写到 output.path”。
- 同名语义不一致：`list.export` 写文件，`event.export` 返回 response。

修改建议：

- 明确分类：
  - file export action：接受 `args.output.path`，写文件。
  - response export action：不写文件，必须在 xout/docs/error 中说明。
- 对 `event.export(args.output)` 返回专门 suggestion：`event.export returns events in the response; it does not write output.path`。
- 长期建议统一 `*.export` 命名语义，或为 response-only action 改名。

### 33. events/xout 表格块混入 summary 字段

证据：`event.find` / `event.export` 的 `events:` 表后面混入 `first/last/begin/end/sampling_mode/clock/edge` 等字段。

影响：

- 表格 rows 和 summary metadata 混在同一块，机器和人都难稳定解析。
- 与 `signal.stability` 的 changes 块混杂问题类似，是 xout renderer 的横向一致性问题。

修改建议：

- xout 约定：
  - `summary:` 放结论。
  - `data:` 放 metadata。
  - `events:` / `changes:` / `signals:` 只放 rows。
- 增加 renderer 测试，避免 row section 后追加非 row 字段。

### 34. `did_you_mean` 可能给出当前 action 不接受的字段

证据：`stream.config.load(args.name)` 返回 `did_you_mean: args.stream`，但 `stream.config.load` schema 不接受 `stream` 字段。

影响：

- AI 会按提示把 `name` 改成 `stream`，继续失败。
- 这类错误比没有建议更危险。

修改建议：

- `did_you_mean` 候选必须限制在当前 action schema 允许字段内。
- 对 config.load 的 `name`，建议应是“删除 args.name；stream 名写在每个 stream 定义内部”。
- 增加测试：所有 error `did_you_mean` 指向的字段必须能通过当前 action schema 的 properties 路径检查。

### 35. 字符串 query 类型未枚举导致 AI 自然猜错

证据：`stream.query(query:"transfer")` 返回 `unsupported stream.query type: transfer`；但 schema 只说 `query` 是 string/object，没有列出合法 query 值。

影响：

- `transfer` 是非常自然的猜法，但实际要用 `first_transfer`、`last_transfer` 或 `transfer_window`。
- AI 无法仅靠 schema 构造正确 query。

修改建议：

- 对 query string 增加 enum，或在 handler 错误中返回 `allowed_values`。
- 对近似值返回 `did_you_mean`，例如 `transfer -> transfer_window`。
- `stream.show` 可返回 `valid_query_values`，帮助下一步 query。

### 36. verbose union table 过宽，降低 AI 可读性

证据：`stream.config.list(verbose:true)` 把所有 stream 的字段做 union 展开，形成超宽表，大量空列。

影响：

- AI 很难稳定提取某个 stream 的有效字段。
- 人工终端阅读也困难。

修改建议：

- verbose 输出改为每个 stream 一个分块。
- 或分组列：core、handshake、packet、fields、metadata。
- 默认列表保持窄表；详细信息引导使用 `stream.show(stream=...)`。

### 37. conditional required 错误的 correct_example 与触发场景不匹配

证据：`stream.export(kind:"packet_beats")` 缺 `output` 时，错误 correct_example 使用 `kind:"transfer"`。

影响：

- AI 想修 packet_beats，却被示例带到 transfer。
- 条件 required 的语义没有被解释。

修改建议：

- 条件 required 错误示例必须保持用户触发条件，例如 `kind:"packet_beats"`。
- 错误中增加 `condition:"when args.kind == packet_beats, args.output is required"`。
- 增加 contract test 覆盖 `if/then/allOf` 错误示例。

### 38. 同名字段在同协议 action 中 enum 不一致

证据：

- `apb.query.direction` 只允许 `read/write`。
- `apb.cursor.direction` 允许 `read/write/all`。

影响：

- AI 会把一个 APB action 的 direction 值迁移到另一个 action，导致错误。
- 用户直觉上 query 也可能想查 all，但 schema 不允许。

修改建议：

- 对同一协议族字段统一 enum，或在错误中明确替代路径。
- 如果 `apb.query` 不支持 all，错误返回 suggestion：`query read and write separately, or use apb.transfer_window`。
- 增加协议族 schema lint：同名字段 enum 差异必须有显式说明。

### 39. protocol config not found 错误的 correct_example 回显坏 name

证据：`apb.query(name:"no_such_apb")` 和 `apb.transfer_window(name:"no_such_apb")` 都返回 `correct_example.args.name:"no_such_apb"`。

影响：

- AI 可能继续使用不存在配置名。
- 缺少发现可用配置的下一步。

修改建议：

- config not found 错误统一返回：

```json
{
  "invalid_arg": "args.name",
  "missing_name": "no_such_apb",
  "available_values": ["apb0"],
  "next_actions": ["apb.config.list", "apb.config.load"]
}
```

- `correct_example` 必须使用 available config，或使用占位 `<loaded_apb_config>` 并明确不可直接执行。

### 40. 协议事务时间字段单位不一致

证据：

- `apb.query` / `apb.cursor` transaction 返回 `time: 255000`。
- `apb.transfer_window` transactions 返回 `225ns` / `255ns`。

影响：

- AI 难以把 transaction time 直接传给其它 action。
- 用户不知道裸数字单位是 ps、fs 还是内部 tick。

修改建议：

- 所有 user-facing xout time 统一带单位字符串。
- 如果需要原始 tick，另给 `time_ticks` 或 JSON 字段。
- 增加 response contract test：compact xout 中 `time` 字段不得裸数字，除非字段名明确为 `_ticks`。

### 41. config.list 语义不一致：有的列全部，有的要求 name

证据：

- `event.config.list` / `stream.config.list` 可无 name 列出全部。
- `apb.config.list` schema 要求 `name`。

影响：

- AI 会自然调用 `apb.config.list(args:{})`，但得到错误。
- action 名称相同，语义不一致。

修改建议：

- `*.config.list` 统一支持无 name 列全部，带 name 显示详情。
- 或把只显示单个配置的 action 改名为 `*.config.show`。
- skill/reference 中明确各协议族差异，直到 runtime 统一。

### 42. MCP 默认 xout 下，错误路径实际返回 JSON/dict

证据：

- `xverif_debug_query(..., output_format:"xout")` 在 action 返回 `ok:false` 时，MCP session 层直接返回 JSON/dict error，而不是 xout 文本。
- 多个参数错误均表现为 JSON：`axi.config.load(args.clock)`、`axi.query(direction:"both")`、`axi.export(format:"json")`。
- 直接 CLI xout 有错误渲染能力，问题主要在 MCP wrapper/session 层。

影响：

- AI 看到成功路径是 xout、失败路径是 JSON，入口心智不一致。
- 用户要求默认 xout 时，参数错误不能直接以同一格式呈现 `invalid_arg/expected/correct_example`。

修改建议：

- MCP `output_format:"xout"` 下，`ok:false` 也应渲染为 xout error，保留 `invalid_arg/expected/did_you_mean/correct_example`。
- 如果保留 JSON/dict，至少在 MCP tool 文档明确“错误路径总是结构化 JSON”，并让字段形态稳定。
- 增加 MCP contract test：同一个错误在 query xout 入口下必须包含可读 correct example。

### 43. handler 层错误没有统一补全 invalid_arg/allowed_values/correct_example

证据：

- `axi.config.load(config_path不存在)` 只返回 `message: config file not found`。
- `axi.export(format:"json")` 只返回 `message: format must be tsv or csv`。
- `axi.config.list(name不存在)` 只返回 `code: CONFIG_NOT_FOUND, message: action failed`。

影响：

- schema 层能直接告诉 AI 如何改参数，但 handler 层错误经常只能人工推理。
- 同一个 action 的两层错误质量差异明显，用户说的“两层提示”没有统一。

修改建议：

- 为 handler 层引入统一 error builder，至少支持 `invalid_arg`、`expected`、`allowed_values`、`did_you_mean`、`correct_example`、`next_actions`。
- handler 层所有 `CONFIG_NOT_FOUND`、file not found、enum-like semantic check 都走统一 builder。
- 增加测试：故意触发 handler 层错误，断言返回可执行 correct example 或 next action。

### 44. correct_example 过于泛化或回显坏值

证据：

- `axi.analysis(analysis:"throughput")` 的 correct_example 没包含 `analysis`。
- `axi.request_response_pair(args.begin)`、`axi.latency_outlier(max_items)`、`axi.channel_stall(channel:"x")` 的 correct_example 没包含触发错误相关字段。
- 多个 config not found 错误的 correct_example 回显 `missing_axi`。

影响：

- AI 不能直接从 correct_example 改出成功请求。
- 回显坏 name 会诱导继续使用不存在配置。

修改建议：

- correct_example 必须满足当前 action 的核心成功路径，并包含与错误字段相关的推荐写法。
- config not found 示例不要回显坏 name；改用 available config 或 `<loaded_config_name>` 占位并配合 `available_values`。
- 增加 contract test：correct_example 重新提交应通过 schema；对 handler 错误，示例不能包含已知坏值。

### 45. AXI 查询类 action 容易触发 MCP 30s timeout，但错误不给缩窄方案

证据：

- `axi.query(name:"axi0", direction:"write")` 全量查询触发 `SESSION_TRANSPORT_FAILED: direct session socket timed out after 30000ms`。
- 改成 `query.index:1` 后成功，但仍耗时约 25s，接近 timeout。

影响：

- AI 首次自然调用全量 query 时容易超时。
- timeout 错误没有建议 `query.index`、`time_range`、`limit` 或替代 action。

修改建议：

- AXI/APB/stream 这类可能全量扫描的 action，在 schema/doc/help 中把“推荐先用 index/window/limit”写入参数说明。
- timeout error 补 `suggested_actions`：加 `query.index`、缩小 `time_range`、使用 `axi.request_response_pair` 或 `axi.export`。
- 对重型 action 增加 preflight estimate 或默认安全 limit。

### 46. 协议 action 的 limit 语义不一致或不控制可见返回行

证据：

- `axi.channel_stall(limit:5)` 成功返回约 20 条 findings。
- `axi.latency_outlier(limit:5)` 按预期返回 5 条 outliers。

影响：

- AI 不能可靠使用 `limit` 控制输出大小。
- 报告/对话中容易产生冗长返回，影响调试效率。

修改建议：

- 明确 `limit` 的统一语义：默认控制返回 item/finding/transaction 行数。
- 如果需要控制扫描样本，另设 `sample_limit` 或放到 `limits`。
- xout renderer 不应绕过 action 的返回限制；增加 regression 覆盖。

### 47. AXI 成功返回的时间单位和 payload 紧凑性不一致

证据：

- `axi.query` / `axi.cursor` transaction 返回 `time: 415000` 裸数字。
- `axi.request_response_pair` / `axi.latency_outlier` 返回 `415ns`、`23130ns` 等带单位字段。
- `axi.query` 的 `data` 可能输出整条超长 hex payload。

影响：

- AI 很难把一个 action 的 time 直接传给另一个 action。
- 超长 data 降低 xout 可读性，容易淹没关键字段。

修改建议：

- user-facing xout 时间统一带单位；裸 tick 改名为 `time_ticks`。
- AXI payload 默认按 beat/byte 或截断显示，提供 `slice_hint/max_bits/include_full_data` 控制。
- 增加 xout compact contract：核心字段必须先于长 payload，长 payload 必须可限制。

### 48. 表达式 alias 缺失属于 handler 层错误，但没有指向 args.signals

证据：

- `expr.eval_at(expr:"valid && missing", signals:{valid:...})` 返回 `ACTION_FAILED: Unknown alias in expression: missing`。
- `window.verify` 中同类错误也只返回同样 message。

影响：

- AI 知道表达式有 unknown alias，但不知道应该补 `args.signals.missing`。
- 多个表达式 action 重复实现同一类弱错误。

修改建议：

- 统一 expression error builder：返回 `invalid_arg:"args.signals.<alias>"` 或 `args.conditions[i].signals.<alias>`。
- 增加 `missing_alias`、`defined_aliases`、`expr`、`correct_example`。
- `expr.eval_at`、`window.verify`、`event.find/export` 共享这套诊断。

### 49. verify.conditions condition 子项约束过弱，错误输入会成功

证据：

- `verify.conditions` 中 `op:"contains"` 返回成功且 pass。
- condition 缺 `signal` 时仍返回 `unknown`，不是参数错误。

影响：

- AI 调错 condition 形态时不会收到错误，可能把无效检查当作真实验证结果。
- debug 风险高于普通错误提示不足。

修改建议：

- schema 要求每个 condition 至少包含 `signal/op/value`。
- `op` 增加 enum 或 runtime 白名单；未知 op 返回 `invalid_arg:"args.conditions[i].op"`。
- 如果存在 op alias，必须在 schema `allowed_values` 和 skill 文档中列出。

### 50. 同一错误概念的 invalid_arg 字段映射不准

证据：

- `sampled_pulse.inspect(valid:"no_such")` 返回 `invalid_arg:"args.signal"`，实际参数是 `args.valid`。
- config not found 一类错误的 correct_example 多次回显坏 name。

影响：

- AI 会按错误字段去修改不存在的 `args.signal`，无法直接修复。
- 影响所有 handler 层复用 generic signal lookup 的 action。

修改建议：

- handler 调用 signal resolver 时传入原始参数路径，例如 `args.valid`、`args.payload`、`args.clock`。
- correct_example 不得包含已知坏 path/name。
- 增加 handler-layer negative tests，断言 `invalid_arg` 精确到用户传入字段。

### 51. source/context 类 action 暴露绝对路径且参数 surface 反直觉

证据：

- `source.context` 成功 xout 显示完整 `<repo>/.../ai_complex_top.sv`。
- `source.context(args.context:2)` 被 schema 拒绝，但 action 名称和用户直觉都会诱导传 context 行数。

影响：

- 用户可见回答容易泄漏本机路径。
- AI 会自然猜测 `context/before/after` 参数，导致额外重试。

修改建议：

- xout 支持 root 映射或路径脱敏，例如 `<repo>/xdebug/...`。
- 支持 `context_lines` 或 `before/after`，或在 schema description 明确“上下文窗口自动选择，不接受 context 参数”。
- SOURCE_NOT_FOUND 补 `invalid_arg:"args.file"` 和 correct example。

### 52. 成功 xout 常把 metadata 混入 table 块尾部

证据：

- `detect_abnormal.findings` 末尾混入 `truncated:false`。
- `sampled_pulse.inspect.payloads/findings` 混入 edge/sample_point/time semantics 等 metadata。
- `axi.channel_stall.findings` 后也混入 name/channel/sampling metadata。

影响：

- 表格块不再是纯 rows，AI 解析和人工阅读都会受到干扰。
- metadata 重复出现在 summary/data/table 尾部，增加噪音。

修改建议：

- xout renderer 约定：表格 section 只放 rows；metadata 放 summary 或独立 `sampling:` section。
- 对每个 action 增加 xout golden test，禁止 table rows 后混入 scalar metadata。

### 53. trace 类 action 对 signal not found 的语义不一致

证据：

- `trace.driver(signal不存在)` 返回 `ok:true, path_count:0`。
- `trace.load(signal不存在)` 返回 `ok:true, path_count:0`。
- `trace.active_driver(signal不存在)` 返回 `SIGNAL_NOT_FOUND` 但 message 只有 `action failed`。
- `trace.active_driver_chain(signal不存在)` 返回 `SIGNAL_NOT_FOUND`，并带 `invalid_arg:"args.signal"`。

影响：

- AI 无法区分“信号不存在”“信号存在但没有 driver/load”“当前时间无 active evidence”。
- 同族 action 的错误质量差异大。

修改建议：

- trace action 统一空结果合同：`empty_reason: signal_not_found | no_path | no_active_evidence | filtered_by_limit`。
- signal not found 统一为结构化错误或统一为 ok+warning，但必须可机读。
- 所有 trace action 使用同一 signal resolver error builder。

### 54. active trace req/rsp 时间字段命名不统一

证据：

- `trace.active_driver` request 使用 `args.time`，response summary 使用 `requested_time` 和 `active_time`。
- `trace.active_driver_chain` request 使用 `args.time`，response summary 使用 `start_time`。
- 旧输入 `requested_time` 报缺 `args.time`，但没有 `did_you_mean`。

影响：

- AI 在 req/rsp 之间迁移字段时容易把 `requested_time/start_time` 写回 request。
- 用户难以判断这些时间字段的关系。

修改建议：

- request/response 统一词典：request time 始终叫 `time`，response 可额外给 `requested_time` 但标明 alias/deprecated。
- active chain summary 也给 `requested_time` 或 `time`，并保留 `active_time/start_time` 的明确定义。
- 旧字段错误加 `did_you_mean:"args.time"`。

### 55. 缩写字段 clk_period 不利于 AI 正确调用

证据：

- `trace.active_driver_chain` 要求 `clk_period`。
- 误传 `clock_period` 时只报 additional property，correct_example 里有 `clk_period`，但没有 `did_you_mean`。

影响：

- AI 和用户更自然会写 `clock_period`。
- 字段与其它 action 统一用 `clock` 的风格不一致。

修改建议：

- 支持 `clock_period` alias，或把 public contract 迁移到 `clock_period`。
- 至少在 schema additional property hint 中加入 `did_you_mean:"args.clk_period"`。

### 56. rc.generate 请求已迁移 output.path，但响应和文档仍残留 rc_path

证据：

- `rc.generate` request schema 要求 `args.output.path`。
- 成功 response summary/data 仍返回 `rc_path`。
- `xdebug/README.md` 中 rc.generate 请求示例仍出现旧 `rc_path` / `include_preview`。

影响：

- AI 会从 response 或 README 学到旧字段，再在 request 中误传 `rc_path`。
- req/rsp 用词不一致，不利于形成稳定 skill。

修改建议：

- response 增加 `output.path`，并逐步废弃 `rc_path`。
- 旧 `rc_path` 输入错误加 `did_you_mean:"args.output.path"`。
- 更新 README、skill、examples 中所有 rc.generate 示例。

### 57. 文件/配置不存在的 handler 错误普遍缺 invalid_arg

证据：

- `rc.generate(config_path不存在)` 返回 `CONFIG_NOT_FOUND` 和路径 message。
- `source.context(file不存在)` 返回 `SOURCE_NOT_FOUND` 和路径 message。
- `axi.config.load(config_path不存在)` 只返回 `config file not found`。

影响：

- AI 知道文件找不到，但不知道该改哪个参数字段。
- 无法统一生成修复示例。

修改建议：

- 所有 file/config path lookup 失败统一返回 `invalid_arg`，例如 `args.config_path`、`args.file`。
- 增加 `expected:"existing readable file"`、`received_path`、`cwd` 或 root mapping。
- correct_example 使用可读占位或已知有效路径，不回显坏路径。
