# xdebug MCP Action 返回可用性逐项评审（2026-07-09）

本报告按用户要求通过 MCP 真实调用 xdebug action，逐个评审：

- 参数错误时失败返回是否清晰、可恢复、能否直接指导 AI 修正。
- 成功返回的信息是否对 debug 有用。
- 成功返回是否冗余、是否容易误导。
- 每个 action 评审完成后追加写入本文件。
- 最后会由独立 agent review 本报告，并把 review 意见插入每个 action 小节内，而不是统一追加到报告末尾。

## 执行约束

- 入口：MCP `xverif_debug_*` tools；每个 xdebug action 尽量同时覆盖 `xverif_debug_query` 和 raw/native 对照。session lifecycle action 使用 MCP 专用 session tool。
- 默认输出：除非为了脚本字段读取，否则使用默认 xout。
- 评审主体阶段不使用子 agent。
- 临时 session 使用仓库 testdata fixture，执行后关闭。
- 不把错误 response 当成功证据；错误 response 只用于评价失败反馈质量。
- 2026-07-09 goal 更新：不要仅用 raw_request，还要用 `xverif_debug_query`。因此已评审 action 若此前只有 raw 证据，需要补 query 入口证据。
- 2026-07-09 goal 更新：失败返回必须同时关注两类错误：
  - 输入参数/schema 层错误，例如缺字段、类型错、非法 enum、多余字段。
  - handler 层语义错误，例如资源不存在、时间非法、信号不存在、child request 失败等。

## Fixture

- waveform：`xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb`
- stream：`xdebug/testdata/waveform/stream_v1/out/waves.fsdb`
- design：`xdebug/testdata/design/uart/simv.daidir`
- combined：`xdebug/testdata/combined/active_driver/out/{simv.daidir,waves.fsdb}`
- design session：`xdebug/testdata/design/uart/simv.daidir`，用于设计数据库类 action。

## 总体进度

- Catalog：MCP `xverif_debug_list_actions` 返回 70 个 implemented action，removed action 为 `signal.search`。
- 已评审 action 数：70 / 70

## 独立 Agent 全局复核

- 主报告总体自洽，大多数结论能从本报告 evidence 或通病报告横向证据推出。最强问题集中在 handler 层错误缺结构化字段、`correct_example` 回显坏值、MCP query/raw/native 示例混杂。
- 少量小节使用同族行为作为推断证据，例如 `cursor.use` handler 错误、`list.value_at` list/clock 错误、`window.verify` 失败样本详情，后续整改计划应标注“按同族推断/待补覆盖”。
- 报告里“返回可用性”和“运行性能/入口安全”有时混在一起，例如 AXI timeout、session lifecycle native action 风险；后续计划应分成返回合同、MCP wrapper、性能/安全三类。
- 全局整改应统一处理 `output_format:"xout"` 错误路径实际返回 JSON/dict、绝对路径脱敏、table section 混入 metadata。
- 最高优先级建议聚焦：`verify.conditions` 弱约束导致假阳性、`value.batch_at` schema/runtime 冲突、错误示例回显坏值、session lifecycle query 误伤、trace/signal not_found 语义不一致。

## 1. `actions`

### MCP 调用方式

- query 成功调用：`xverif_debug_query(session_id="session_open_review_20260709", action="actions", args={})`
- query 失败调用：`xverif_debug_query(session_id="session_open_review_20260709", action="actions", args={"filter":"waveform"})`
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"actions"})`
- raw 失败调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"actions","args":{"filter":"waveform"}})`
- schema 查询：`xverif_debug_get_schema(action="actions", kind="request")`

### 失败返回评审

错误输入为多余字段 `args.filter`。`xverif_debug_query` 返回结构化 error：

```text
code: INVALID_REQUEST
invalid_arg: args.filter
expected: no additional properties allowed
received_type: string
schema_path: schemas/v1/actions/actions.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"actions","args":{}}
```

同样错误通过 `xverif_debug_raw_request` 返回时，不是直接的 xdebug error，而是 MCP wrapper error：

```text
code: XVERIF_CLI_FAILED
message: xdebug exit 1
tool: xdebug
exit_code: 1
stdout_tail: @xdebug.error.v1 ... invalid_arg: args.filter ... correct_example: {"api_version":"xdebug.v1","action":"actions","args":{}}
```

清晰度评价：

- xdebug backend 的错误信息本身清楚：指出 `args.filter` 是额外字段，说明 `expected: no additional properties allowed`，并给了最小正确示例。
- `xverif_debug_query` 入口保留结构化字段，AI 可直接按 `invalid_arg` 和 `correct_example` 修复。
- MCP raw_request 包装后不够理想：顶层只剩 `XVERIF_CLI_FAILED`，AI 必须解析 `stdout_tail` 才能看到 `invalid_arg` 和 `correct_example`。
- `correct_example` 是 native envelope，符合 raw_request 场景；但如果用户是在 MCP 常规 query 心智下调用，仍需要额外知道这是 raw_request 的 `request` 内层。

建议：

- `xverif_debug_raw_request` 对 backend 参数错误应尽量提升结构化字段：`backend_error.code`、`backend_error.invalid_arg`、`backend_error.expected`、`backend_error.correct_example`。query 入口当前已经较好。
- `stdout_tail` 可以保留作诊断，但不应是 AI 获取参数修复信息的唯一入口。

### 成功返回评审

默认 xout 成功返回包含：

- `summary.action_count: 70`
- `summary.removed_count: 1`
- `implemented` 列表的前若干项
- `actions` 表格，含 `name/category/status/requires/request_schema/response_schema/handler_kind`
- `removed`、`design`、`waveform`、`combined`、`builtin`、`session` 分组

对 debug 的价值：

- 对 action 发现非常有用，能立即看到 action 分类、requires 和 schema 路径。
- 对 AI 决策有帮助：知道哪些 action 需要 waveform/design/combined/session。
- 默认 xout 会截断长列表，只展示前 20 个左右 action；适合 quick scan，但不适合完整自动化覆盖。完整 action catalog 应改用 JSON 或 `xverif_debug_list_actions` 的结构化返回。

冗余/风险：

- xout 同时有 `implemented` 列表、`actions` 表和模式分组，信息有重复，但对人工扫描可接受。
- 默认截断没有在 visible 表格附近强提示“还有未显示 action”，容易让 AI 误以为只看到的 action 才存在；虽然 summary 里有 `action_count: 70`。

### 结论

- 成功返回：有 debug 价值，适合快速发现 action，但默认 xout 不适合作完整 catalog 数据源。
- 失败返回：query 入口清楚可用；raw_request 包装层削弱了结构化可恢复性。

### Agent Review

独立 agent 认为本节结论与证据匹配；建议补充默认截断是否有机器可读提示，避免把可见列表长度当成精确行为。

## 43. `apb.config.load`

### 调用覆盖

- MCP query 成功调用：`name + config_path`
- MCP query schema 错误：缺少 `config/config_path`
- MCP query schema 错误：误把 `clock` 直接写进 args
- MCP query handler 错误：`config_path` 不存在

### 能力与入口形态

`apb.config.load` 加载 APB interface 信号映射。MCP query 形态：

```json
{"session_id":"case_a","action":"apb.config.load","args":{"name":"apb0","config_path":"xdebug/configs/apb0.json"}}
```

### 失败返回评审

缺少 `config/config_path` 返回：

```text
code: INVALID_REQUEST
required_any_of: ["args.config","args.config_path"]
message: provide one of: args.config or args.config_path
```

这是好的 anyOf 错误。

误把 `clock` 直接写进 args 返回：

```text
invalid_arg: args.clock
expected: no additional properties allowed
correct_example.args.config_path: ...
```

缺少解释：APB 的 `clock/paddr/pwrite/...` 应放在 config 内容或 config 文件中，而不是 request args。

`config_path` 不存在返回：

```text
code: INVALID_REQUEST
message: config file not found: <repo>/tmp/no_such_apb.json
```

缺 `invalid_arg:"args.config_path"`。

### 成功返回评审

成功 xout：

```text
summary:
  name: apb0
  status: loaded

config:
  sampling_mode: clock_edge
  clock: ai_complex_top.clk
  edge: posedge
  sample_point: before
  rst_n: ai_complex_top.rst_n
```

对 debug 的价值：

- 能确认 config 已加载和采样语义。

不足：

- 不展示 APB 核心 signals：paddr/pwdata/prdata/pwrite/penable/psel，调试价值不完整。
- summary/data 重复 name/status。

### 结论

- 错误 anyOf 做得好。
- 成功返回应展示完整 APB signal mapping。

### 修改建议

- 成功 xout 增加 `signals:` 块，列出 APB 关键路径。
- 对 `args.clock/paddr/...` additional property 错误说明这些字段属于 config 内容。
- config file not found 补 `invalid_arg/expected/correct_example`。

### Agent Review

独立 agent 认为 anyOf 好、顶层 clock 解释不足、成功缺 APB mapping 均有证据。

## 44. `apb.config.list`

### 调用覆盖

- MCP query 成功调用：`name:"apb0"`
- MCP query schema/包装错误：传 `args:{}` 后后端报缺整个 `args`

### 能力与入口形态

`apb.config.list` 查看指定 APB 配置。与多数 `*.config.list` 不同，它的 schema 要求 `name` 必填：

```json
{"session_id":"case_a","action":"apb.config.list","args":{"name":"apb0"}}
```

### 失败返回评审

传 `args:{}` 时实际返回：

```text
invalid_arg: args
message: required property 'args' not found in object
```

这不是最理想的错误。用户明明传了空 args，理应报 `args.name` 缺失。这和前面 `cursor.get` 一样，是 MCP wrapper 对空 args 的序列化/转发语义问题。

### 成功返回评审

成功 xout：

```text
data:
  name: apb0
  sampling_mode: clock_edge
  clock: ai_complex_top.clk
  edge: posedge
  sample_point: before
  rst_n: ai_complex_top.rst_n
```

对 debug 的价值：

- 能确认 clock/edge/reset。

不足：

- 缺 summary 层。
- 不列 paddr/pwdata/prdata/pwrite/penable/psel。
- action 名叫 list，但必须 name，只能查看单个配置；这和 `stream.config.list/event.config.list` 的“列所有配置”语义不一致。

### 结论

- 成功返回信息偏少。
- `config.list` 命名和 required name 合同容易让 AI 误解。

### 修改建议

- 支持无 name 列全部 APB configs，或改名/文档强调这是 show。
- 成功返回加 summary 和 signal mapping。
- 修 MCP 空 args，报告 `args.name` 缺失。

### Agent Review

独立 agent 认可空 args 定位和 list/show 语义不一致问题；与其它 config.list 对比可放全局处理。

## 45. `apb.query`

### 调用覆盖

- MCP query 成功调用：`direction:"write"` count
- MCP query 成功调用：`direction:"read", query.index:1`
- MCP query schema 错误：`direction:"all"`
- MCP query schema 错误：旧字段 `num`
- MCP query handler 错误：APB config 不存在
- raw_request 成功调用
- raw_request schema 错误：`direction:"all"`

### 能力与入口形态

`apb.query` 查询 APB transfer。MCP query 形态：

```json
{"session_id":"case_a","action":"apb.query","args":{"name":"apb0","direction":"read","query":{"index":1}}}
```

### 失败返回评审

`direction:"all"` 返回：

```text
invalid_arg: args.direction
allowed_values: ["write","read"]
```

清晰，但和 `apb.cursor.direction` 支持 `all` 不一致，AI 容易迁移错误。

旧字段 `num` 返回：

```text
invalid_arg: args.num
did_you_mean: args.query.index
message: use args.query.index instead
```

这是好的迁移提示。

config 不存在返回：

```text
code: ANALYZE_FAILED
message: APB config not found: no_such_apb
invalid_arg: args.name
expected: name of a previously loaded config
correct_example.args.name: no_such_apb
```

问题：`correct_example` 回显了坏 name，缺 available configs 和 `apb.config.list/load` 下一步。

### 成功返回评审

count 查询：

```text
summary:
  name: apb0
  direction: write
  count: 2
```

index 查询：

```text
transaction:
  time: 255000
  addr: 0100
  data: cafef00d
  is_write: false
  has_error: false
```

对 debug 的价值：

- count 查询能快速看读写数量。
- index 查询给 addr/data/is_write/error，有用。

不足：

- `time:255000` 没单位，而其它 action 通常用 `255ns`。
- count 查询不展示 first/last transfer 时间。
- direction read/write 不含 all，用户要总数必须分别查两次或用 window。

### 结论

- 成功返回可用但偏简略。
- direction 合同和 cursor 不一致。
- handler config not found 错误示例错误。

### 修改建议

- transaction time 输出带单位。
- config not found 返回 `available_configs` 和有效示例。
- 考虑 `direction:"all"` 对 query 也支持，或错误中建议分别查 read/write。
- count summary 加 `first_time/last_time`。

### Agent Review

独立 agent 认为 direction enum 不一致、坏 name 回显、time 无单位均有证据；first/last time 属增强建议。

## 46. `apb.cursor`

### 调用覆盖

- MCP query 成功调用：`op:"begin", direction:"all"`
- MCP query schema 错误：非法 `op:"first"`
- raw_request schema 错误：非法 `op:"first"`

### 能力与入口形态

`apb.cursor` 在 APB transfer 间移动游标。MCP query 形态：

```json
{"session_id":"case_a","action":"apb.cursor","args":{"name":"apb0","op":"begin","direction":"all"}}
```

### 失败返回评审

`op:"first"` 返回：

```text
invalid_arg: args.op
allowed_values: ["begin","next","prev","pre","last"]
correct_example.args.op: begin
```

清晰度较好，但缺 `did_you_mean:"begin"`。`pre` 和 `prev` 同时存在，命名非常容易混淆。

### 成功返回评审

成功 xout：

```text
summary:
  name: apb0
  op: begin
  direction: all
  found: true
  addr: 0100

transaction:
  time: 225000
  addr: 0100
  data: deadbeef
  is_write: true
  has_error: false
```

对 debug 的价值：

- 可交互浏览事务，方向支持 all 很方便。
- 返回 transaction 字段够用。

不足：

- time 没单位。
- `pre` 操作含义不清，可能是 prev alias 或 pre-trigger。
- 如果 cursor 状态被保存，返回没有 cursor name/id 或 current index。

### 结论

- 成功返回有用。
- op 命名需要更清楚，尤其 `pre/prev`。
- direction 支持 all，而 query 不支持 all，跨 action 不一致。

### 修改建议

- `op:first` 错误加 `did_you_mean:"begin"`。
- 明确 `pre` 与 `prev` 的区别；若重复，删除一个或标 deprecated。
- transaction time 带单位，返回 current index。

### Agent Review

独立 agent 认可 time 无单位、pre/prev、direction all 不一致问题；did_you_mean begin 是合理建议但非已证实机制。

## 47. `apb.transfer_window`

### 调用覆盖

- MCP query 成功调用：`time_range/limit`
- MCP query schema 错误：旧顶层 `begin/end`
- MCP query handler 错误：config 不存在
- raw_request 成功调用

### 能力与入口形态

`apb.transfer_window` 返回时间窗口内 APB transfers。MCP query 形态：

```json
{"session_id":"case_a","action":"apb.transfer_window","args":{"name":"apb0","time_range":{"begin":"200ns","end":"400ns"},"limit":2}}
```

### 失败返回评审

旧顶层 `begin/end` 返回：

```text
invalid_arg: args.begin
did_you_mean: args.time_range.begin
correct_example.args: {name:"if0", include_accesses:false}
```

有 `did_you_mean`，但 correct_example 没包含 `time_range`，和触发错误不匹配。

config 不存在返回：

```text
code: ACTION_FAILED
message: APB config not found: no_such_apb
invalid_arg: args.name
correct_example.args.name: no_such_apb
```

同样回显坏 name。

### 成功返回评审

成功 xout：

```text
summary:
  name: apb0
  begin: 200ns
  end: 400ns
  transaction_count: 2
  truncated: true

transactions:
  time   type  addr    data        has_error
  225ns  WR    'h0100  'hdeadbeef  false
  255ns  RD    'h0100  'hcafef00d  false
  truncated: true
```

对 debug 的价值：

- 事务表非常有用，time/type/addr/data/error 一目了然。
- begin/end 带单位，优于 apb.query/cursor。

不足：

- `truncated:true` 同时在 summary 和 transactions 块出现，且混在表后。
- `limit:2` 导致 truncated true；应同时显示 `returned_count` 和 `total_count`，现在 transaction_count 可能被理解为 total。

### 结论

- 成功返回是 APB 组里最适合 debug 的输出。
- 错误提示里的 correct_example 需要与触发场景一致。

### 修改建议

- correct_example 包含 `time_range.begin/end`。
- summary 改为 `returned_count/total_count/truncated`。
- transactions 块只放 rows，不混入 `truncated`。
- config not found 错误提供 available configs。

### Agent Review

独立 agent 认为事务表高价值、correct_example 缺 time_range、坏 name 回显证据充分。

## 48. `axi.config.load`

### 调用覆盖

- MCP query 成功调用：`name + inline config`
- MCP query schema 错误：误把 `clock` 直接写进 args
- MCP query handler 错误：`config_path` 不存在

### 能力与入口形态

`axi.config.load` 加载 AXI channel 信号映射。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.config.load","args":{"name":"axi0","config":{"clock":"...","awvalid":"...","wdata":"...","rready":"..."}}}
```

### 失败返回评审

误把 `clock` 写在 args 顶层时返回：

```text
code: INVALID_REQUEST
invalid_arg: args.clock
expected: no additional properties allowed
correct_example.args.config.clock: axi_vip_fixture_top.clk
```

这能指导 AI 把信号路径放入 `config`，但 message 没有直接说明“AXI signal mapping 属于 args.config 内容，不属于 args 顶层”。

`config_path` 不存在时返回：

```text
code: INVALID_REQUEST
message: config file not found: <repo>/tmp/xdebug_action_review_20260709/no_such_axi.json
```

这是 handler 层错误，缺 `invalid_arg:"args.config_path"`、`expected:"existing JSON config file"` 和正确示例。

### 成功返回评审

成功 xout：

```text
summary:
  name: axi0
  status: loaded

config:
  name: axi0
  sampling_mode: clock_edge
  clock: axi_vip_fixture_top.clk
  edge: posedge
  sample_point: before
  rst_n: axi_vip_fixture_top.rst_n
```

对 debug 的价值：

- 能确认配置名、采样 clock/edge/reset。
- 返回很紧凑，不冗余。

不足：

- 不展示 AW/W/B/AR/R 关键 channel signal mapping，加载错路径时不利于排查。
- 大型 AXI config 的 `correct_example` 很长，作为错误返回会占据大量文本。

### 结论

- 成功返回适合作“已加载”确认，但不够验证完整 AXI mapping。
- schema 层错误可恢复；handler 层 `config_path` 错误提示不足。

### 修改建议

- 成功返回增加可折叠/compact 的 `signals:` 摘要，至少列 clock/reset 和每个 channel 的 valid/ready/data/id/resp。
- bad `config_path` 统一补 `invalid_arg/expected/correct_example`。
- 对顶层 `args.clock` 错误补充 suggestion：`put AXI signal mapping under args.config or config_path`。

### Agent Review

独立 agent 认可成功只确认加载、config_path 错误弱、顶层 clock 缺 suggestion；长 correct_example 属可用性风险。

## 49. `axi.config.list`

### 调用覆盖

- MCP query 成功调用：`name:"axi0"`
- MCP query schema/包装错误：传 `args:{}` 后后端报缺整个 `args`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.config.list` 查看指定 AXI 配置。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.config.list","args":{"name":"axi0"}}
```

### 失败返回评审

传 `args:{}` 时返回：

```text
invalid_arg: args
message: required property 'args' not found in object
correct_example.args.name: if0
```

用户实际传了空 args，理应报 `args.name` 缺失。这是 MCP wrapper/stdio-loop 对空 args 的错误定位问题。

配置不存在时返回：

```text
code: CONFIG_NOT_FOUND
message: action failed
```

这个错误不可用：没有缺失配置名、没有 `invalid_arg`、没有 available configs，也没有提示先 `axi.config.load`。

### 成功返回评审

成功 xout：

```text
data:
  name: axi0
  sampling_mode: clock_edge
  clock: axi_vip_fixture_top.clk
  edge: posedge
  sample_point: before
  rst_n: axi_vip_fixture_top.rst_n
```

对 debug 的价值：

- 能确认 clock/edge/reset。

不足：

- 不列 AXI channel signal mapping。
- 没有 summary。
- action 名称叫 list，但实际要求 name，只能 show 单个配置，和 `stream.config.list/event.config.list` 语义不一致。

### 结论

- 成功返回偏少。
- 缺失配置错误质量很差。
- `config.list` 语义不统一，AI 容易先调用空 args。

### 修改建议

- 支持无 name 列出所有 AXI configs，带 name 显示详情；或改名/别名为 `axi.config.show`。
- missing config 返回 `invalid_arg:"args.name"`、`missing_name`、`available_configs` 和 `next_actions:["axi.config.load"]`。
- 修复 MCP 空 args 错误定位，报告 `args.name` 缺失。

### Agent Review

独立 agent 认为 missing config 只有 action failed 是严重不可恢复问题，list 语义不一致证据明确。

## 50. `axi.query`

### 调用覆盖

- MCP query 初始失败：全量 `direction:"write"` 超过 MCP 30s socket timeout
- MCP query schema 错误：`query.index:0`
- MCP query 成功调用：`direction:"write", query.index:1`
- MCP query schema 错误：`direction:"both"`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.query` 查询单笔或统计 AXI transaction。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.query","args":{"name":"axi0","direction":"write","query":{"index":1}}}
```

### 失败返回评审

全量 `direction:"write"` 首次调用返回：

```text
code: SESSION_TRANSPORT_FAILED
message: direct session socket timed out after 30000ms
```

这是重要可用性问题：默认全量 query 会触发长扫描，但错误没有建议加 `query.index`、缩小 time window，或改用 `axi.request_response_pair/axi.export`。

`query.index:0` 返回：

```text
invalid_arg: args.query.index
message: instance is below minimum of 1
correct_example.args.query.index: 1
```

这是好的 schema 提示，能把 AI 从 0-based index 修正到 1-based。

`direction:"both"` 返回：

```text
invalid_arg: args.direction
allowed_values: ["write","read"]
```

清楚，但和 `axi.cursor/axi.analysis` 支持 `direction:"all"` 不一致。

配置不存在返回：

```text
code: ANALYZE_FAILED
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
correct_example.args.name: missing_axi
```

`correct_example` 回显坏 name，不利于修复。

### 成功返回评审

成功 xout：

```text
summary:
  name: axi0
  direction: write
  found: true
  addr: 00000000000008c0

transaction:
  time: 415000
  addr: 00000000000008c0
  id: 00
  len: 000
  size: 3
  burst: 1
  is_write: true

data:
  0000...245ea0e0
```

对 debug 的价值：

- 返回 transaction 关键字段，能定位地址、ID、burst、len、size。
- 对单笔查询有价值。

不足：

- `time` 是裸数字，没有单位。
- `data` 可能是一整条超长 hex，xout 可读性差；缺少 beat 分解、宽度、截断策略或 slice hint。
- 即使指定 index，调用耗时 25s，接近 MCP timeout。

### 结论

- 单笔成功返回有用，但默认全量查询对 MCP 交互不安全。
- 参数复杂度中等，主要迷惑点是 1-based index、direction enum、全量扫描风险。

### 修改建议

- 全量 query 超时前或超时后返回建议：使用 `query.index`、`time_range` 或 `limit`，并给出正确示例。
- transaction time 统一带单位。
- data 输出默认压缩或按 beat 表格展示，超长 payload 支持 `slice_hint`/`max_bits`。
- config not found 统一返回 available configs，不回显坏 name 作为 correct example。

### Agent Review

独立 agent 认为 timeout、index 仍慢、time 裸数字和超长 data 证据强；建议把性能/入口风险与返回格式问题分开。

## 51. `axi.cursor`

### 调用覆盖

- MCP query 成功调用：`op:"begin", direction:"all"`
- MCP query 成功调用：`op:"next", direction:"all"`
- MCP query schema 错误：非法 `op:"first"`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.cursor` 在 AXI transaction 间移动游标。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.cursor","args":{"name":"axi0","op":"begin","direction":"all"}}
```

### 失败返回评审

`op:"first"` 返回：

```text
invalid_arg: args.op
allowed_values: ["begin","next","prev","pre","last"]
correct_example.args.op: begin
```

清楚指出 enum，但没有 `did_you_mean:"begin"`。`pre` 和 `prev` 同时存在，命名容易混淆。

配置不存在返回：

```text
code: ANALYZE_FAILED
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
correct_example.args.name: missing_axi
```

仍然回显坏 name。

### 成功返回评审

成功 xout：

```text
summary:
  name: axi0
  op: begin
  direction: all
  found: true
  addr: 00000000000008c0

transaction:
  time: 415000
  addr: 00000000000008c0
  id: 00
  len: 000
  is_write: true
```

对 debug 的价值：

- 比 `axi.query` 轻量，适合交互式浏览。
- 支持 `direction:"all"`，能混合读写前进。

不足：

- `time` 没单位。
- 不返回 current index/cursor position，AI 难以复现“当前第几笔”。
- `op:"pre"` 语义不清。

### 结论

- 成功返回有用，建议作为交互式 AXI 浏览优先入口。
- op 命名和 cursor 状态可观测性需要优化。

### 修改建议

- 对 `op:"first"` 增加 `did_you_mean:"begin"`。
- 明确或废弃 `pre`，避免和 `prev` 冲突。
- 返回 `index`、`cursor_id/current_position` 和带单位 time。

### Agent Review

独立 agent 认可缺 index/current position、time 无单位、坏 name 回显；pre/prev 是同族合同可读性问题。

## 52. `axi.analysis`

### 调用覆盖

- MCP query 成功调用：`analysis:"latency", direction:"all"`
- MCP query 成功调用：`analysis:"osd", direction:"all"`
- MCP query schema 错误：非法 `analysis:"throughput"`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.analysis` 对 AXI transaction 做聚合分析。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.analysis","args":{"name":"axi0","analysis":"latency","direction":"all"}}
```

### 失败返回评审

非法 `analysis:"throughput"` 返回：

```text
invalid_arg: args.analysis
allowed_values: ["latency","osd","outstanding"]
correct_example.args: {"name":"if0","include_transactions":false}
```

allowed_values 清楚，但 `correct_example` 没包含 required/关键字段 `analysis` 和 `direction`，对 AI 修复帮助不足。

配置不存在返回：

```text
code: ANALYZE_FAILED
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
```

结构化字段较好，但 correct example 仍回显坏 name。

### 成功返回评审

latency 成功 xout：

```text
summary:
  analysis: latency
  max: 364110000.0
  min: 600000.0
  avg: 155662899.3710692
  samples: 6360
```

osd 成功 xout：

```text
summary:
  analysis: osd
  max: 134.0
  min: 0.0
  avg: 102.54464942589608
  samples: 1397308
```

对 debug 的价值：

- 能快速给出 latency/outstanding 深度的聚合统计。
- summary 很紧凑。

不足：

- latency 的单位没有显示。
- `osd` 缩写对无上下文 AI 不直观，应显示 `outstanding_depth` 或解释。
- `analysis:"outstanding"` 与 `osd` 的关系不清楚，且与 `axi.outstanding_timeline` 重叠。

### 结论

- 成功返回适合作快速 health check。
- 参数 enum 和结果字段需要更具语义。

### 修改建议

- summary 增加 `unit` / `time_unit` / `metric`。
- `osd` 增加别名或输出解释：`metric: outstanding_depth`。
- illegal analysis 的 correct_example 必须包含 `analysis:"latency"`。
- 明确 `axi.analysis(outstanding/osd)` 和 `axi.outstanding_timeline` 的边界。

### Agent Review

独立 agent 认为 latency 单位缺失、osd 缩写、illegal analysis 示例缺字段合理；与 timeline 边界需更多证据。

## 53. `axi.request_response_pair`

### 调用覆盖

- MCP query 成功调用：`time_range + limit`
- MCP query schema 错误：旧顶层 `begin/end`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.request_response_pair` 在时间窗口内配对 AXI 请求和响应。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.request_response_pair","args":{"name":"axi0","time_range":{"begin":"0ns","end":"200ms"},"limit":5}}
```

### 失败返回评审

旧顶层 `begin/end` 返回：

```text
invalid_arg: args.begin
did_you_mean: args.time_range.begin
correct_example.args: {"name":"if0","include_transactions":false}
```

`did_you_mean` 很有用，但 correct_example 没有 `time_range`，不能直接照抄修复。

配置不存在返回：

```text
code: ACTION_FAILED
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
```

结构化字段可用，但 correct example 回显坏 name。

### 成功返回评审

成功 xout：

```text
data:
  name: axi0
  begin: 0ns
  end: 200000000ns
  transaction_count: 5
  truncated: true

transactions:
  addr_time  type  id  addr  len  size  burst  beats  first_data_time  last_data_time  resp_time  resp  match_time  latency
```

对 debug 的价值：

- 这是 AXI 组里最有 debug 价值的视图之一，能直接看到请求、响应、数据时间和 latency。
- 时间字段带单位，优于 `axi.query/cursor`。

不足：

- `transaction_count:5` 是返回数量还是总数不明确。
- `truncated:true` 没给 total count。
- 默认示例缺 `time_range`，导致错误修复慢。

### 结论

- 成功返回非常适合定位 AXI latency 和响应配对问题。
- schema 错误提示有方向，但 correct_example 不够贴近。

### 修改建议

- correct_example 包含 `time_range` 和 `limit`。
- summary 分开 `returned_count/total_count/truncated`。
- 与 `axi.latency_outlier` 共享 transaction 表格字段说明。

### Agent Review

独立 agent 认可高价值事务表和 correct_example 缺 time_range；returned/total/truncated 问题明确。

## 54. `axi.latency_outlier`

### 调用覆盖

- MCP query 成功调用：`time_range + limit`
- MCP query schema 错误：旧数量字段 `max_items`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.latency_outlier` 返回窗口内延迟最高的 AXI transactions。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.latency_outlier","args":{"name":"axi0","time_range":{"begin":"0ns","end":"200ms"},"limit":5}}
```

### 失败返回评审

旧字段 `max_items` 返回：

```text
invalid_arg: args.max_items
expected: no additional properties allowed
correct_example.args: {"name":"if0","include_transactions":false}
```

缺 `did_you_mean:"args.limit"`，且 correct_example 没展示 `limit/time_range`。

配置不存在返回：

```text
code: ACTION_FAILED
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
```

结构化字段可用，但示例仍回显坏 name。

### 成功返回评审

成功 xout：

```text
outliers:
  addr_time  type  id  addr  len  size  burst  beats  first_data_time  last_data_time  resp_time  resp  match_time  latency
  515ns      RD    'h02 ... latency 23130ns
  565ns      WR    'h01 ... latency 15010ns
```

对 debug 的价值：

- 直接按 latency 排序，定位慢 transaction 很高效。
- 字段足够完整，包含 id/addr/beats/resp/match_time。

不足：

- outlier 表后混有 `outlier_count: 5`，不是独立 summary。
- 没有说明排序方向和 latency 单位来源。

### 结论

- 成功返回高价值。
- 错误提示对旧字段迁移不足。

### 修改建议

- `max_items` 错误加 `did_you_mean:"args.limit"`。
- correct_example 包含 `time_range` 和 `limit`。
- summary 增加 `returned_count/total_count/sort:"latency_desc"`。

### Agent Review

独立 agent 认为 outlier 表高价值、max_items 缺 did_you_mean 有证据；排序方向建议补更明确证据。

## 55. `axi.outstanding_timeline`

### 调用覆盖

- MCP query 成功调用：`time_range + limit`
- MCP query schema 错误：旧顶层 `begin/end`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.outstanding_timeline` 返回 AXI read/write outstanding 随时间变化的采样序列。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.outstanding_timeline","args":{"name":"axi0","time_range":{"begin":"0ns","end":"200ms"},"limit":10}}
```

### 失败返回评审

旧顶层 `begin/end` 返回：

```text
invalid_arg: args.begin
did_you_mean: args.time_range.begin
correct_example.args: {"name":"if0","include_transactions":false}
```

有正确字段提示，但示例没有 `time_range`。

配置不存在返回结构化 `invalid_arg:"args.name"` 和 `expected`，但 correct example 回显坏 name。

### 成功返回评审

成功 xout：

```text
summary:
  sampling_mode: clock_edge
  clock: axi_vip_fixture_top.clk
  edge: posedge
  sample_time_semantics: time is sample_time
  sample_count: 10
  truncated: true

samples:
  time   read  write
  205ns  0     0
  215ns  0     0
```

对 debug 的价值：

- 明确给出采样语义、clock、edge，这是好设计。
- 可用于观察 outstanding 深度趋势。

不足：

- 默认从空闲区开始时，返回的前 10 条可能全是 0；AI 需要知道如何选窗口或 cursor。
- summary 和 samples 块后重复采样元数据。
- `limit` 控制 sample 数，但没有建议如何根据 clock/window 选择。

### 结论

- 成功返回结构清楚，但窗口选择对结果价值影响很大。
- 错误提示仍受 correct_example 泛化问题影响。

### 修改建议

- correct_example 包含 `time_range`。
- 当样本全为 0 时给 suggestion：缩小到 transaction 活跃窗口或先用 `axi.request_response_pair` 找时间。
- 减少 samples 块尾部重复 metadata。

### Agent Review

独立 agent 认可采样语义展示和 correct_example 泛化问题；全 0 suggestion 需避免过度推断。

## 56. `axi.channel_stall`

### 调用覆盖

- MCP query 成功调用：`channel:"r" + time_range + rules.max_wait_cycles + limit`
- MCP query schema 错误：非法 `channel:"x"`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.channel_stall` 检查 AXI 某个 channel 的 valid/ready stall。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.channel_stall","args":{"name":"axi0","channel":"r","time_range":{"begin":"0ns","end":"200ms"},"rules":{"max_wait_cycles":2},"limit":5}}
```

### 失败返回评审

非法 channel 返回：

```text
invalid_arg: args.channel
allowed_values: ["aw","w","b","ar","r"]
correct_example.args: {"name":"if0","include_transactions":false}
```

allowed_values 清楚，但 correct_example 没包含 `channel/time_range/rules`，不可直接照抄。

配置不存在返回结构化 `invalid_arg:"args.name"`，但 correct example 回显坏 name。

### 成功返回评审

成功 xout：

```text
summary:
  sample_count: 1000001
  transfer_count: 15055
  max_stall_cycles: 109
  truncated: true

findings:
  type        severity  begin     end       cycles
  long_stall  warning   15175ns   15475ns   30
```

对 debug 的价值：

- 对协议 backpressure debug 很有价值，直接给出 stall 区间和 cycles。
- 包含 clock/edge/sample_time 语义。

不足：

- 传 `limit:5` 仍返回约 20 条 finding，limit 语义和用户预期不一致。
- `sample_count:1000001` 和 `truncated:true` 说明扫描较大，但没有提示如何缩小窗口。
- summary/data/块尾 metadata 重复。

### 结论

- 成功返回高价值。
- `limit` 的实际控制对象不清楚，容易让 AI 以为能限制 findings 行数。

### 修改建议

- 明确 `limit` 控制 sample 还是 finding；如果用于 finding，修正实现。
- 增加 `finding_limit` 或统一 `limit` 为返回 item 数。
- correct_example 包含 `channel/time_range/rules/limit`。
- 当 truncated 时建议缩小 `time_range` 或调大明确的 scan limit。

### Agent Review

独立 agent 认为 limit:5 返回约 20 条 findings 是明确问题；建议补 exact returned_count 便于验收。

## 57. `axi.export`

### 调用覆盖

- MCP query 初始成功但无交易：`time_range 0ns-1us`
- MCP query 成功重试：`time_range 0ns-20us`
- MCP query schema 错误：旧字段 `output_file`
- MCP query handler 错误：非法 `format:"json"`
- MCP query handler 错误：配置名不存在

### 能力与入口形态

`axi.export` 导出 AXI transactions 到文件。MCP query 形态：

```json
{"session_id":"case_a","action":"axi.export","args":{"name":"axi0","time_range":{"begin":"0ns","end":"20us"},"format":"tsv","output":{"path":"<repo>/tmp/axi0"}}}
```

### 失败返回评审

旧字段 `output_file` 返回：

```text
invalid_arg: args.output_file
expected: no additional properties allowed
correct_example.args.output.path: <repo>/tmp/if0_axi
```

这是好反馈，能直接迁移到 `output.path`。

非法 `format:"json"` 返回：

```text
code: INVALID_REQUEST
message: format must be tsv or csv
```

这是 handler 层错误，缺 `invalid_arg:"args.format"`、`allowed_values:["tsv","csv"]` 和 correct example。

配置不存在返回：

```text
code: CONFIG_NOT_FOUND
message: AXI config not found: missing_axi
invalid_arg: args.name
expected: name of a previously loaded config
```

结构化字段较好，但 correct example 回显坏 name。

### 成功返回评审

0-1us 初次成功但无交易：

```text
summary:
  write_count: 0
  read_count: 0
  total_count: 0
```

0-20us 重试成功：

```text
summary:
  write_count: 20
  read_count: 2
  total_count: 22
  format: tsv

data:
  write_file: <repo>/tmp/xdebug_action_review_20260709/axi0_20us.write.tsv
  read_file: <repo>/tmp/xdebug_action_review_20260709/axi0_20us.read.tsv
  meta_file: <repo>/tmp/xdebug_action_review_20260709/axi0_20us.meta.json
```

对 debug 的价值：

- 成功返回清楚给出 read/write/meta 文件和数量。
- 对离线分析有价值。

不足：

- 当导出 0 条时没有提示窗口可能太窄或响应不在窗口内。
- 输出绝对路径在用户可见回答中应谨慎脱敏。
- `format` handler 错误没有结构化字段。

### 结论

- 成功返回可用，文件产物明确。
- 初次 0 结果需要 suggestion，避免 AI 误以为没有 AXI traffic。

### 修改建议

- 0 结果时建议用 `axi.request_response_pair` 找活跃窗口，或扩大 `time_range`。
- 非法 `format` 错误统一走 schema 或 handler structured error。
- config not found 不回显坏 name，返回 available configs。

### Agent Review

独立 agent 认可文件产物、0 结果缺 suggestion、format handler 错误弱；后续报告应避免传播具体临时绝对路径。

## 58. `detect_abnormal`

### 调用覆盖

- MCP query 成功调用：`signals + time_range + checks + limit`
- MCP query schema 错误：`checks` 数组项误写成字符串
- MCP query schema 错误：未知 check `type`

### 能力与入口形态

`detect_abnormal` 检测 glitch、stuck、unknown/X/Z 等异常。MCP query 形态：

```json
{"session_id":"case_a","action":"detect_abnormal","args":{"signals":["top.sig"],"time_range":{"begin":"0ns","end":"200ns"},"checks":[{"type":"unknown_xz"}],"limit":10}}
```

### 失败返回评审

`checks:["unknown_xz"]` 返回：

```text
invalid_arg: args.checks[0]
expected: type "object"
received_type: string
correct_example.args.checks[0].type: unknown_xz
```

未知 check type 返回：

```text
invalid_arg: args.checks[0].type
allowed_values: ["unknown_xz","glitch","stuck"]
```

这两类 schema 错误都很清楚，能直接指导 AI 把字符串改成对象，并选择合法 type。

### 成功返回评审

成功 xout：

```text
summary:
  finding_count: 3
  truncated: false

findings:
  type        signal                     severity  time  pulse_width  value
  glitch      ai_complex_top.glitch_sig  info      96ns  0.2ns
  unknown_xz  ai_complex_top.xz_bus      warning   85ns               8'hxx known=false bits=xxxxxxxx width=8
```

对 debug 的价值：

- 能直接定位异常类型、信号、时间、脉宽和值。
- 对 X/Z 和窄脉冲排查很有用。

不足：

- findings 块尾部混入 `truncated:false`。
- `stuck` 成功样例未在本轮输出中出现，可能需要更长窗口或更清晰的 rule 说明。

### 结论

- 参数错误提示质量较高。
- 成功返回紧凑且有 debug 价值。

### 修改建议

- findings 表只放 finding 行，`truncated` 留在 summary/data。
- 文档明确每种 check 所需/可选字段，如 `glitch.min_pulse_width`、`stuck.min_duration`。

### Agent Review

独立 agent 认为 checks 错误和 enum 错误提示清楚，成功 findings 有价值；stuck 未覆盖应列为覆盖缺口。

## 59. `expr.eval_at`

### 调用覆盖

- MCP query 成功调用：`expr + signals + time + clock`
- MCP query schema 错误：缺 `clock`
- MCP query handler 错误：表达式引用未提供 alias

### 能力与入口形态

`expr.eval_at` 在单点时间采样并计算表达式。MCP query 形态：

```json
{"session_id":"case_a","action":"expr.eval_at","args":{"clock":"top.clk","time":"145ns","expr":"valid && !ready","signals":{"valid":"top.valid","ready":"top.ready"}}}
```

### 失败返回评审

缺 `clock` 返回：

```text
invalid_arg: args.clock
expected: type "string"
correct_example.args.clock: top.u.clk
```

这是好的 schema required 提示。

表达式引用缺失 alias 返回：

```text
code: ACTION_FAILED
message: Unknown alias in expression: missing
```

handler 层提示不足：没有 `invalid_arg:"args.signals.missing"`，没有建议把 `missing` 加入 `args.signals`，也没有 correct example。

### 成功返回评审

成功 xout：

```text
summary:
  expr: valid&&!ready
  time: 145ns
  status: true
  clock_edge_hit: true

operands:
  valid  ai_complex_top.hs_valid  1'h1
  ready  ai_complex_top.hs_ready  1'h0

sample_rows:
  signal  path  before  middle  after
```

对 debug 的价值：

- operands、clock_context、before/middle/after 都很有用。
- 能解释表达式结果为什么为 true/false/unknown。

不足：

- `edge: negedge` 但 `clock_edge_kind: posedge` 同时出现，语义需要更直观解释。
- 输出较长，但对表达式 debug 可接受。

### 结论

- 成功返回高价值。
- handler alias 错误需要结构化。

### 修改建议

- Unknown alias 返回 `invalid_arg:"args.signals.<alias>"`、`missing_alias`、`defined_aliases` 和 correct example。
- clock_context 中明确 `edge` 是目标采样边沿，`clock_edge_kind` 是 requested_time 落在哪种真实边沿。

### Agent Review

独立 agent 认可 operands/clock_context/sample_rows 价值和 alias 错误弱；edge/clock_edge_kind 需引用具体字段解释。

## 60. `expr.normalize`

### 调用覆盖

- MCP query 成功调用：`expr`
- MCP query schema/包装错误：传 `args:{}`

### 能力与入口形态

`expr.normalize` 规范化表达式。MCP query 形态：

```json
{"session_id":"case_a","action":"expr.normalize","args":{"expr":"valid && !ready"}}
```

### 失败返回评审

传 `args:{}` 返回：

```text
invalid_arg: args
message: required property 'args' not found in object
correct_example.args.expr: valid && !ready
```

这再次复现 MCP 空 args 定位问题：用户传了空 args，但错误说缺整个 args，理应报 `args.expr` 缺失。

### 成功返回评审

成功 xout：

```text
summary:
  expr: valid && !ready
  source: string_fallback
  confidence: low

args:
  name   type    op
  valid  signal
                 not
  op: and
```

对 debug 的价值：

- 能显示解析出的操作和 confidence。
- `string_fallback/low` 诚实暴露语义可信度。

不足：

- `args:` 块名容易和 request args 混淆，实际是表达式 AST/operands。
- `not` 行缺 name，表格可读性一般。
- 如果 action 是 design 类，但当前结果是 string fallback，用户可能误以为已基于 NPI 解析。

### 结论

- 成功返回可用但命名容易误导。
- 空 args 错误需要修 MCP/validator 定位。

### 修改建议

- 输出块名改为 `normalized_expr` 或 `expr_tree`。
- summary 增加 `semantic_source`，明确是否用 design/NPI。
- 修空 args 错误为 `args.expr` missing。

### Agent Review

独立 agent 认为空 args 和 args 块名混淆有证据；string_fallback 是否未用 NPI 应表述为建议。

## 61. `verify.conditions`

### 调用覆盖

- MCP query 成功调用：三条 condition，分别 pass/fail/unknown
- MCP query schema 错误：缺 `clock`
- MCP query 语义风险：`op:"contains"` 仍成功
- MCP query 语义风险：condition 缺 `signal` 仍成功并返回 unknown

### 能力与入口形态

`verify.conditions` 在单点时间验证多条 signal condition。MCP query 形态：

```json
{"session_id":"case_a","action":"verify.conditions","args":{"clock":"top.clk","time":"95ns","conditions":[{"signal":"top.sig","op":"==","value":"'h1"}]}}
```

### 失败返回评审

缺 `clock` 返回：

```text
invalid_arg: args.clock
expected: type "string"
correct_example.args.clock: top.u.clk
```

required 错误清楚。

但非法/非预期 condition 没有失败：

```text
op: contains
status: pass
```

缺 `signal` 也没有失败：

```text
signal: <empty>
status: unknown
```

这比错误提示不足更严重：AI 可能传错 op 或漏 signal，却得到貌似成功的验证结果。

### 成功返回评审

成功 xout：

```text
summary:
  verdict: fail
  condition_count: 3
  passed: 1
  failed: 1
  unknown: 1

checks:
  signal  time  op  expected  observed  known  status  pass

sample_rows:
  signal  path  before.status  before.value  middle.status  middle.value  after.status  after.value
```

对 debug 的价值：

- 同时展示 pass/fail/unknown 和 before/middle/after，价值很高。
- 对 X/Z unknown 判断直观。

不足：

- condition schema/runtime 对 `op` 和 `signal` 约束过弱。
- clock_context 中 `edge` 与 `clock_edge_kind` 组合需要解释。

### 结论

- 成功返回高价值。
- 参数合同存在严重宽松问题：错误 condition 会变成 unknown 或 pass，而不是 fail fast。

### 修改建议

- schema 要求每个 condition 必须有 `signal/op/value`。
- `op` 增加 enum 或 runtime 白名单；未知 op 返回 `invalid_arg:"args.conditions[i].op"`。
- 如果保留 `eq/contains` 等别名，文档和 allowed_values 必须明确。

### Agent Review

独立 agent 认为非法 condition 成功是高优先级合同问题，会导致假阳性验证结论。

## 62. `window.verify`

### 调用覆盖

- MCP query 成功调用：`time_range + conditions + edge/sample_point`
- MCP query schema 错误：旧字段 `posedge`
- MCP query handler 错误：表达式引用未提供 alias

### 能力与入口形态

`window.verify` 在采样窗口内验证表达式条件。MCP query 形态：

```json
{"session_id":"case_a","action":"window.verify","args":{"clock":"top.clk","time_range":{"begin":"140ns","end":"175ns"},"conditions":[{"expr":"valid && !ready","signals":{"valid":"top.valid","ready":"top.ready"},"mode":"always"}]}}
```

### 失败返回评审

旧字段 `posedge:true` 返回：

```text
invalid_arg: args.posedge
expected: use clock, edge, and sample_point
correct_example.args.clock: top.u.clk
```

这是好的迁移提示。

表达式 alias 缺失返回：

```text
code: ACTION_FAILED
message: Unknown alias in expression: missing
```

和 `expr.eval_at` 一样，缺 `invalid_arg`、`missing_alias`、`defined_aliases` 和 correct example。

### 成功返回评审

成功 xout：

```text
summary:
  all_passed: true
  sample_count: 4
  failed_samples: 0
  unknown_samples: 0
  sampling_mode: clock_edge
  edge: posedge
  sample_time_semantics: time is sample_time

conditions:
  expr           mode    passed  pass_samples  failed_samples  unknown_samples
  valid&&!ready  always  true    4             0               0
```

对 debug 的价值：

- 适合证明窗口内条件是否始终满足或 eventually 满足。
- summary 包含采样语义，利于避免边沿误判。

不足：

- 默认只给聚合结果，不展示失败样本详情；如果失败，需要可选 `examples` 或 `first_failure`。
- alias 错误不结构化。

### 结论

- 成功返回简洁有用。
- 表达式错误需要与 `expr.eval_at` 共享统一诊断。

### 修改建议

- Unknown alias 统一返回 `invalid_arg:"args.conditions[i].signals.<alias>"`。
- 失败时默认返回 first failing sample 的 time/operand values。
- correct_example 包含 `edge/sample_point` 的推荐写法。

### Agent Review

独立 agent 认可成功聚合、posedge 迁移提示和 alias 错误问题；失败样本详情缺失未实测，应标为待验证。

## 63. `handshake.inspect`

### 调用覆盖

- MCP query 成功调用：`clock/valid/ready/data/time_range/rules`
- MCP query schema 错误：旧字段 `max_stall_cycles`
- MCP query schema 错误：缺 required `ready`

### 能力与入口形态

`handshake.inspect` 检查 valid/ready 传输、stall 和数据稳定性。MCP query 形态：

```json
{"session_id":"case_a","action":"handshake.inspect","args":{"clock":"top.clk","valid":"top.valid","ready":"top.ready","data":["top.data"],"rules":{"max_wait_cycles":2}}}
```

### 失败返回评审

旧顶层 `max_stall_cycles` 返回：

```text
invalid_arg: args.max_stall_cycles
expected: no additional properties allowed
correct_example.args: {"clock":"top.u.clk","valid":"top.u.valid","ready":"top.u.ready"}
```

缺少关键迁移提示：应给 `did_you_mean:"args.rules.max_wait_cycles"` 或 `args.rules.max_stall_cycles` 的当前真实字段。

缺 `ready` 返回：

```text
invalid_arg: args.ready
expected: type "string"
correct_example.args.ready: top.u.ready
```

required 错误清楚。

### 成功返回评审

成功 xout：

```text
summary:
  sample_count: 10
  transfer_count: 3
  max_stall_cycles: 4
  data_stability_violations: 3

findings:
  long_stall warning 150ns 190ns 4
```

对 debug 的价值：

- 对通用 valid/ready 接口很有价值。
- 输出紧凑，直接给 transfer_count、stall 和 data stability。

不足：

- `rules.max_wait_cycles` 与输出 `max_stall_cycles` 命名不完全一致。
- `data` 参数是数组，但 correct_example 不展示 data/rules，导致高级用法不明显。

### 结论

- 成功返回高价值。
- 旧字段迁移提示不足。

### 修改建议

- `args.max_stall_cycles` 错误加 `did_you_mean:"args.rules.max_wait_cycles"`。
- 统一 rule/output 命名，或说明 wait/stall 的关系。
- correct_example 增加 data/rules 示例。

### Agent Review

独立 agent 认为旧 max_stall_cycles 缺 did_you_mean 和 rules/output 命名不清都有证据。

## 64. `sampled_pulse.inspect`

### 调用覆盖

- MCP query 成功调用：`clock/valid/payload/time_range/edge/limit`
- MCP query schema 错误：缺 `clock`
- MCP query handler 错误：`valid` 信号不存在

### 能力与入口形态

`sampled_pulse.inspect` 检查 raw pulse 是否被 clock sample 到，以及 payload 是否在未采样 valid 时变化。MCP query 形态：

```json
{"session_id":"case_a","action":"sampled_pulse.inspect","args":{"clock":"top.clk","valid":"top.glitch","payload":"top.data","time_range":{"begin":"0ns","end":"200ns"},"edge":"posedge","limit":5}}
```

### 失败返回评审

缺 `clock` 返回：

```text
invalid_arg: args.clock
expected: type "string"
correct_example.args.clock: ai_complex_top.clk
```

required 错误清楚。

`valid` 信号不存在返回：

```text
code: ACTION_FAILED
message: Signal not found: ai_complex_top.no_such_sig
invalid_arg: args.signal
expected: existing signal path
correct_example.args.valid: ai_complex_top.no_such_sig
```

问题：

- `invalid_arg` 应为 `args.valid`，不是 `args.signal`。
- correct_example 回显坏 signal。
- 缺候选 signal 或建议用 `signal.resolve/scope.list`。

### 成功返回评审

成功 xout：

```text
summary:
  sample_count: 20
  sampled_high_cycles: 0
  risk_count: 6
  truncated: true

first_risk:
  type: unsampled_valid_pulse
  raw_begin: 96ns
  raw_end: 96.2ns
  previous_sample_edge: 95ns
  next_sample_edge: 105ns

findings:
  unsampled_valid_pulse ...
  payload_changed_without_sampled_valid ...
```

对 debug 的价值：

- 对“波形里有窄脉冲但 DUT 没采到”的问题非常有价值。
- first_risk 给了最近采样边沿，定位清楚。

不足：

- 默认 xout 很长，metadata 分散在 payloads/findings 多个块。
- findings 表字段很多，容易淹没核心 first_risk。
- payload 参数名支持单个字符串，但 payloads 输出变成 alias `payload0`，需要说明。

### 结论

- 成功返回高价值但偏冗长。
- handler 层 signal not found 的 invalid_arg 错误。

### 修改建议

- signal not found 使用真实参数路径：`args.valid` 或 `args.payload`。
- 0/坏路径 correct_example 不回显坏 signal，给 `signal.resolve` next action。
- xout 分为 compact summary + first_risk，完整 findings 受 `limit` 控制并减少重复 metadata。

### Agent Review

独立 agent 认为 args.valid 被报成 args.signal 且示例回显坏值是明确错误，成功返回高价值但冗长。

## 65. `source.context`

### 调用覆盖

- MCP query 初始 schema 错误：误传 `context`
- MCP query 成功调用：`file + line`
- MCP query handler 错误：文件不存在

### 能力与入口形态

`source.context` 返回源码行及其所在上下文块。MCP query 形态：

```json
{"session_id":"case_a","action":"source.context","args":{"file":"rtl/foo.sv","line":123}}
```

### 失败返回评审

误传 `context:2` 返回：

```text
invalid_arg: args.context
expected: no additional properties allowed
correct_example.args: {"file":"rtl/foo.sv","line":123}
```

schema 错误清楚，但 action 名叫 context，AI 很自然会猜 `context` 或 `before/after` 参数；如果不支持，应在 schema description 里说明上下文窗口由工具自动决定。

文件不存在返回：

```text
code: SOURCE_NOT_FOUND
message: <repo>/tmp/xdebug_action_review_20260709/no_such_file.sv
```

handler 层错误缺 `invalid_arg:"args.file"`、`expected:"existing source file"` 和 correct example。

### 成功返回评审

成功 xout：

```text
summary:
  file: <repo>/xdebug/testdata/waveform/ai_complex_wave/tb/ai_complex_top.sv
  line: 43

enclosing:
  begin_line: 37
  end_line: 57
  type: begin

context:
  hit    line  text
  true   43    task apb_write(input [15:0] addr, input [31:0] data);
```

对 debug 的价值：

- 能直接看到源码上下文和 enclosing block，很有用。
- `hit` 标记清楚。

不足：

- 输出绝对路径，用户可见报告需要脱敏或 root 映射。
- 不支持控制上下文行数。
- `context_kind: begin` 对 SV task/function/module 语义略弱。

### 结论

- 成功返回有 debug 价值。
- 参数 surface 过窄，常见 `context/before/after` 会被拒绝。

### 修改建议

- 支持 `context_lines` 或 `before/after`，或者在 schema/help 明确不支持。
- SOURCE_NOT_FOUND 补结构化字段和 next action。
- xout 支持 root 映射，避免默认暴露长绝对路径。

### Agent Review

独立 agent 认可源码上下文价值、绝对路径、context 参数直觉冲突和 SOURCE_NOT_FOUND 结构弱。

## 66. `trace.driver`

### 调用覆盖

- MCP query 成功调用：UART design session，`signal:"uart_16550.RXDin"`
- MCP query 语义风险：不存在 signal 返回 ok 且 `path_count:0`
- MCP query schema/包装错误：传 `args:{}`

### 能力与入口形态

`trace.driver` 查询设计侧 driver/source path。MCP query 形态：

```json
{"session_id":"case_a","action":"trace.driver","args":{"signal":"uart_16550.RXDin"}}
```

### 失败返回评审

传不存在 signal：

```text
@xdebug.trace.driver.v1
summary:
  signal: uart_16550.NO_SUCH_SIGNAL
  path_count: 0
```

这不是错误返回。对“信号拼错”这种参数问题来说，`ok:true + path_count:0` 不够清楚，缺 `empty_reason`。

传 `args:{}` 返回：

```text
invalid_arg: args
message: required property 'args' not found in object
```

再次复现 MCP 空 args 定位问题，理应报 `args.signal` 缺失。

### 成功返回评审

成功 xout：

```text
summary:
  signal: uart_16550.RXDin
  mode: driver
  path_count: 3

source: .../uart_16550.sv:164
> assign RXDin = loopback ? TXD : RXD;

active_signals:
  line  signal_path
  164   uart_16550.loopback -> uart_16550.RXDin
```

对 debug 的价值：

- 源码上下文和 driver path 非常有用。
- compact xout 没有返回冗余大结构。

不足：

- 输出绝对路径。
- 不存在 signal 的 0 path 未区分“信号不存在”还是“存在但无 driver”。

### 结论

- 成功返回高价值。
- 空结果语义需要增强。

### 修改建议

- 0 path 返回 `empty_reason: signal_not_found | no_driver | unsupported`。
- 对 signal_not_found 可设置 `ok:false`，或至少 warning + `signal.resolve` next action。
- 修空 args 错误定位。

### Agent Review

独立 agent 认为不存在 signal 返回 ok+path_count 0 缺 empty_reason 是核心问题。

## 67. `trace.load`

### 调用覆盖

- MCP query 成功调用：UART design session，`signal:"uart_16550.RXDin"`
- MCP query 语义风险：不存在 signal 返回 ok 且 `path_count:0`

### 能力与入口形态

`trace.load` 查询设计侧 load/fanout/source path。MCP query 形态：

```json
{"session_id":"case_a","action":"trace.load","args":{"signal":"uart_16550.RXDin"}}
```

### 失败返回评审

不存在 signal 返回：

```text
@xdebug.trace.load.v1
summary:
  signal: uart_16550.NO_SUCH_SIGNAL
  mode: load
  path_count: 0
```

和 `trace.driver` 一样，返回 ok 但没有说明 signal 是否存在。

### 成功返回评审

成功 xout：

```text
summary:
  signal: uart_16550.RXDin
  mode: load
  path_count: 5

source: .../uart_rx.sv:69
> filter[0] <= RXD;

active_signals:
  line  signal_path
  69    uart_16550.rx_channel.RXD -> uart_16550.RXDin
```

对 debug 的价值：

- 直接给出 load 源码和信号路径，适合静态 fanout 分析。
- 多个 source block 能覆盖端口连接与过程赋值。

不足：

- 可能重复展示同一 source line 的不同 signal_path，人工看有点长。
- 绝对路径问题同上。
- 0 path 缺 empty_reason。

### 结论

- 成功返回高价值。
- 和 `trace.driver` 应统一空结果语义。

### 修改建议

- 增加 `empty_reason` 和 signal existence check。
- 成功 summary 增加 `unique_source_count`，避免 path_count 与 source block 数混淆。
- 支持路径脱敏/root mapping。

### Agent Review

独立 agent 认可与 trace.driver 同族空结果语义不清；unique_source_count 建议需更多重复证据。

## 68. `trace.active_driver`

### 调用覆盖

- MCP query 成功调用：combined session，`signal + time`
- MCP query schema 错误：旧字段 `requested_time`
- MCP query handler 错误：signal 不存在

### 能力与入口形态

`trace.active_driver` 在指定时间回溯当前实际生效 driver/root cause。MCP query 形态：

```json
{"session_id":"case_a","action":"trace.active_driver","args":{"signal":"active_semantics_tb.u_dut.q_en","time":"26ns","include_trace":true}}
```

### 失败返回评审

旧字段 `requested_time` 返回：

```text
invalid_arg: args.time
message: required property 'time' not found
correct_example.args.time: 120ns
```

能提示必须用 `time`，但没有明确指出 `requested_time` 是多余旧字段；如果同时传了 `requested_time` 和缺 `time`，AI 需要自己推断迁移关系。

signal 不存在返回：

```text
code: SIGNAL_NOT_FOUND
message: action failed
```

这是差反馈：没有坏 signal、没有 `invalid_arg:"args.signal"`、没有 expected/correct_example。

### 成功返回评审

成功 xout：

```text
summary:
  signal: active_semantics_tb.u_dut.q_en
  requested_time: 26ns
  active_time: 15ns
  path_count: 4

source:
> else if (en)
> q_en <= data_a;

active_signals:
  line  signal_path
  34    data_a -> q_en
  33    en -> q_en
```

对 debug 的价值：

- 非常高，能把 requested_time 映射到真实 active_time，并标出生效源码行。
- active_signals 给出了数据和控制依赖。

不足：

- request 字段统一为 `time`，response summary 仍叫 `requested_time`，req/rsp 用词不一致。
- 输出绝对路径。
- signal not found 错误质量低于 `trace.active_driver_chain`。

### 结论

- 成功返回是 xdebug 的核心高价值能力。
- 错误路径需要补结构化字段，并统一 req/rsp 命名。

### 修改建议

- response 同时返回 `time` 或 `requested_time` 明确标 deprecated；文档说明区别。
- signal not found 统一返回 `invalid_arg:"args.signal"` 和 `correct_example`。
- `requested_time` 旧字段错误加 `did_you_mean:"args.time"`。

### Agent Review

独立 agent 认为成功能力高价值，requested_time 迁移和 signal not found 弱错误证据充分。

## 69. `trace.active_driver_chain`

### 调用覆盖

- MCP query 成功调用：combined session，`signal + time + clk_period`
- MCP query schema 错误：误传 `clock_period`
- MCP query handler 错误：signal 不存在

### 能力与入口形态

`trace.active_driver_chain` 多跳回溯 active driver 链。MCP query 形态：

```json
{"session_id":"case_a","action":"trace.active_driver_chain","args":{"signal":"active_semantics_tb.u_dut.chain_out","time":"26ns","clk_period":"10ns"}}
```

### 失败返回评审

误传 `clock_period` 返回：

```text
invalid_arg: args.clock_period
expected: no additional properties allowed
correct_example.args.clk_period: 10ns
```

能从 correct_example 看出正确字段，但缺 `did_you_mean:"args.clk_period"`。

signal 不存在返回：

```text
code: SIGNAL_NOT_FOUND
message: signal not found: active_semantics_tb.u_dut.no_such
invalid_arg: args.signal
expected: existing signal path
correct_example.args.signal: active_semantics_tb.u_dut.no_such
```

比 `trace.active_driver` 好，但 correct_example 仍回显坏 signal。

### 成功返回评审

成功 xout：

```text
summary:
  signal: active_semantics_tb.u_dut.chain_out
  start_time: 26ns
  hop_count: 4
  termination: primary_input

active_signals:
  hop  line  signal_path
  0    28    chain_mid -> chain_out
  1    27    chain_src -> chain_mid
  2    149   tb.chain_src -> u_dut.chain_src
```

对 debug 的价值：

- 非常高，能把组合 assign 和 TB drive 串成因果链。
- hop/index/termination 清楚。

不足：

- `clk_period` 缩写不如 `clock_period` 自解释，且错误没有 did_you_mean。
- start_time/request time 命名与 `trace.active_driver` 不一致。
- 路径仍是绝对路径。

### 结论

- 成功返回高价值。
- 字段命名和同族错误结构需要统一。

### 修改建议

- 支持 `clock_period` alias 或错误加 `did_you_mean:"args.clk_period"`。
- response time 字段与 active_driver 统一。
- signal not found correct_example 不回显坏 signal。

### Agent Review

独立 agent 认可因果链高价值、clock_period 缺 did_you_mean、坏 signal 示例回显问题。

## 70. `rc.generate`

### 调用覆盖

- MCP query 成功调用：`config_path + output.path`
- MCP query schema 错误：旧字段 `rc_path`，缺 `output`
- MCP query schema 错误：同时传 `output.path` 和旧 `rc_path`
- MCP query handler 错误：`config_path` 不存在

### 能力与入口形态

`rc.generate` 根据 JSON 配置生成 nWave signal rc。MCP query 形态：

```json
{"session_id":"case_a","action":"rc.generate","args":{"config_path":"<repo>/tmp/wave_view.json","output":{"path":"<repo>/tmp/signal.rc"}}}
```

### 失败返回评审

只传旧 `rc_path` 时返回：

```text
invalid_arg: args.output
message: required property 'output' not found
correct_example.args.output.path: signal.rc
```

同时传 `output.path` 和旧 `rc_path` 时返回：

```text
invalid_arg: args.rc_path
expected: no additional properties allowed
correct_example.args.output.path: signal.rc
```

能看到正确字段，但缺 `did_you_mean:"args.output.path"`。

`config_path` 不存在返回：

```text
code: CONFIG_NOT_FOUND
message: <repo>/tmp/xdebug_action_review_20260709/no_such_view.json
```

handler 层缺 `invalid_arg:"args.config_path"`、`expected` 和 correct_example。

### 成功返回评审

成功 xout：

```text
summary:
  written: true
  config_path: <repo>/tmp/xdebug_action_review_20260709/rc_wave_view.json
  rc_path: <repo>/tmp/xdebug_action_review_20260709/active_semantics.rc
  valid: true
  group_count: 1
  signal_count: 4
```

对 debug 的价值：

- 能确认写出 rc、配置有效、group/signal 数量。
- 对波形调试工作流有用。

不足：

- request 使用 `output.path`，response 仍叫 `rc_path`，req/rsp 用词不一致。
- README 中仍可见旧 `rc_path/include_preview` 示例，容易误导。
- 成功返回不展示 invalid/missing signal diagnostics 的 compact 摘要。

### 结论

- 成功返回可用。
- req/rsp 和文档存在旧字段残留。

### 修改建议

- response 增加 `output.path`，`rc_path` 标 deprecated 或移除。
- 旧 `rc_path` 错误加 `did_you_mean:"args.output.path"`。
- config not found 补结构化字段。
- 更新 README/skill 中所有 rc.generate 示例到 `output.path`。

### Agent Review

独立 agent 认为 output.path/rc_path 不一致、README 旧字段残留、config_path 错误弱均有证据；missing signal diagnostics 需补覆盖。

## 37. `stream.config.load`

### 调用覆盖

- MCP query 成功调用：`config_path`
- MCP query handler/contract 错误：缺少 `streams/config/config_path/file`
- MCP query schema 错误：误传 `name`
- MCP query handler 错误：`config_path` 不存在

### 能力与入口形态

`stream.config.load` 加载 stream 配置，可以通过 `streams`、`config`、`config_path` 或 `file` 提供。MCP query 推荐形态：

```json
{"session_id":"case_a","action":"stream.config.load","args":{"config_path":"xdebug/configs/streams.json"}}
```

### 失败返回评审

空 args 返回：

```text
code: INVALID_REQUEST
message: stream.config.load requires args.streams, args.config, args.config_path, or args.file
recoverable: true
```

这个 message 可读，但缺 `required_any_of` 和 `correct_example`。

误传 `name` 返回：

```text
invalid_arg: args.name
did_you_mean: args.stream
correct_example.args.streams: [...]
```

这里 `did_you_mean:"args.stream"` 是误导：`stream.config.load` schema 不接受 `stream` 字段。对 config.load 来说，`name` 不是改成 `stream`，而是应删除，或放进每个 stream 配置项的 `name` 字段。

`config_path` 不存在返回：

```text
code: INVALID_REQUEST
message: config file not found: <repo>/tmp/no_such_streams.json
recoverable: true
```

缺 `invalid_arg:"args.config_path"`。

### 成功返回评审

成功 xout：

```text
summary:
  loaded: 7
  mode: replace

streams:
  valid_only
  ready_stream
  ...

issues:
  valid_only WARNING CLOCK_COMPLEX clock expression is not a plain signal...
```

对 debug 的价值：

- `loaded/mode/streams` 直接确认配置已加载。
- `issues` 能提前指出复杂 clock 表达式，这是很有价值的质量提示。

不足：

- issues 只列 stream 名和 message，建议补 `severity_count`。
- 如果 mode 默认 replace，应显示 `mode_source: default`。

### 结论

- 成功返回很好，尤其是 issues。
- 缺 anyOf 的结构化错误。
- `args.name` 的 did_you_mean 是错误建议，会直接误导 AI。

### 修改建议

- 空 args 错误增加：

```json
{"required_any_of":["args.streams","args.config","args.config_path","args.file"]}
```

- 对 `args.name` 返回 `suggestion:"remove args.name; stream names belong inside each stream definition"`，不要给 `args.stream`。
- config path not found 统一补 `invalid_arg/expected`。

### Agent Review

独立 agent 认为 did_you_mean 指向不被 schema 接受字段是明确错误建议，结论很强。

## 38. `stream.config.list`

### 调用覆盖

- MCP query 成功调用：默认 compact
- MCP query 成功调用：`verbose:true`
- raw_request 成功调用

### 能力与入口形态

`stream.config.list` 列出已加载 stream 定义。MCP query 形态：

```json
{"session_id":"case_a","action":"stream.config.list","args":{}}
```

### 失败返回评审

本轮未构造 schema 错误；schema 只允许 `verbose/time_unit`。同类 additionalProperties 错误预计和其它 list/config action 一致。

### 成功返回评审

默认 xout：

```text
summary:
  count: 7

streams:
  name sampling_mode clock edge handshake packet field_count channel_id_valid allow_interleaving sample_point
```

对 debug 的价值：

- 默认表格字段选择很好，能快速选 stream。
- `handshake/packet/field_count` 直接反映能力。

`verbose:true` 返回非常宽的表，包含 clock/reset/vld/rdy/bp/sop/eop/data_fields/stable_fields/description 等。

问题：

- verbose 表过宽，在终端和 AI 上都难扫描。
- 字段按所有 stream 的 union 展开，导致大量空列。
- 对复杂 stream，`stream.show` 更适合查看单个详情。

### 结论

- 默认返回可用性高。
- verbose 模式信息完整但可读性差。

### 修改建议

- verbose 改为分块输出，每个 stream 一个小节，而不是超宽 union table。
- 默认 summary 增加 `warning_count`，继承 config.load issues。
- 如果 verbose 表保留，至少把字段分组：core/handshake/packet/fields/meta。

### Agent Review

独立 agent 认为默认返回和 verbose union 评价合理；失败路径未构造，报告处理克制。

## 39. `stream.show`

### 调用覆盖

- MCP query 成功调用：`stream:"ready_stream"`
- MCP query schema 错误：旧字段 `name`

### 能力与入口形态

`stream.show` 显示单个 stream 定义和语义摘要。MCP query 形态：

```json
{"session_id":"case_a","action":"stream.show","args":{"stream":"ready_stream"}}
```

### 失败返回评审

误用 `name` 返回：

```text
invalid_arg: args.name
message: required property 'stream' not found in object; use args.stream instead
did_you_mean: args.stream
```

这是好的迁移错误：直接说明旧字段应改成 `stream`。

### 成功返回评审

成功 xout：

```text
summary:
  stream: ready_stream
  handshake: vld/rdy
  packet_enabled: false

config:
  clock/edge/sample_point/reset/vld/rdy

data_fields:
  addr/data/is_wr/low8
  channel_id: ...
  channel_id_valid: every_beat
  allow_interleaving: false
  description: ...
  issues: [empty]

semantics:
  transfer: vld/rdy
  stall: enabled
```

对 debug 的价值：

- 信息密度高，能直接帮助写 `stream.query`。
- semantics 明确 transfer/stall。

不足：

- `channel_id/channel_id_valid/allow_interleaving/description/issues` 被放在 `data_fields` 块下，不是 data field，层级混杂。
- 如果后续 AI 根据 `data_fields` 生成 match，可能把 `channel_id_valid` 当成可 match field。

### 结论

- 成功返回很有用。
- 需要整理 xout 分组，避免 metadata 混入 data_fields。

### 修改建议

- 分成 `fields:`、`routing:`、`metadata:`、`issues:`。
- `fields` 只放可用于 `match.field` 的字段。
- `stream.show` 可增加 `valid_query_values`，帮助后续调用 `stream.query`。

### Agent Review

独立 agent 认可 name->stream 迁移和信息密度评价；建议补 match.field 可用字段来源。

## 40. `stream.validate`

### 调用覆盖

- MCP query 成功调用：`stream/time_range/limit`
- MCP query handler 错误：stream 不存在

### 能力与入口形态

`stream.validate` 校验 stream 配置，并可做动态窗口统计。MCP query 形态：

```json
{"session_id":"case_a","action":"stream.validate","args":{"stream":"ready_stream","time_range":{"begin":"0ns","end":"200ns"},"limit":10}}
```

### 失败返回评审

stream 不存在返回：

```text
code: STREAM_NOT_FOUND
message: stream config not found: no_such_stream
recoverable: true
```

能读懂，但缺：

- `invalid_arg:"args.stream"`
- `available_streams`
- `next_action:"stream.config.list"`

### 成功返回评审

成功 xout 包含：

```text
summary:
  stream: ready_stream
  ok: true

dynamic:
  clock_edges: 20
  vld_cycles: 13
  transfer_count: 11
  stall_cycles: 2
  stall_windows: 2
  control_xz_count: 0
  data_xz_count: 0
  ready_bp_conflict_count: 0

first_transfer/last_transfer/first_stall/last_stall
```

对 debug 的价值：

- 非常高。它不只是静态校验，还给出 transfer/stall/XZ/冲突统计。
- first/last transfer 和 stall 让用户能直接跳到关键时间。

不足：

- summary 只有 `ok:true`，核心动态统计都在 dynamic 块里；建议 summary 也带 `transfer_count/stall_cycles/issues_count`。
- `limit` 对 validate 的影响不清楚。

### 结论

- 成功返回是 stream 组里最有 debug 价值的入口之一。
- handler not found 错误需补可用 stream 列表。

### 修改建议

- `STREAM_NOT_FOUND` 增加 `available_streams` 和 MCP 正确示例。
- summary 加核心动态统计。
- docs 中强调 validate 可作为 stream.query 前置健康检查。

### Agent Review

独立 agent 认可 STREAM_NOT_FOUND 缺恢复信息；limit 语义不清需补实测或降级为文档建议。

## 41. `stream.query`

### 调用覆盖

- MCP query handler 错误：猜测 `query:"transfer"`，实际不支持
- MCP query schema 错误：缺少 `query`
- MCP query schema 错误：旧 match 简写 `{opcode:...}`
- MCP query 成功调用：`summary`
- MCP query 成功调用：`first_transfer`
- MCP query 成功调用：`match_field` + `match.field/op/value`
- MCP query handler 错误：stream 不存在
- raw_request 成功调用：`summary`

### 能力与入口形态

`stream.query` 查询 stream summary、transfer、stall、packet、field match 等。实际可用 query 值从测试证据看包括：

```text
summary, first_transfer, last_transfer, transfer_window,
first_packet, packet_at, stall_window, packet_window, match_field
```

MCP query 示例：

```json
{"session_id":"case_a","action":"stream.query","args":{"stream":"ready_stream","query":"summary","time_range":{"begin":"0ns","end":"200ns"},"limit":5}}
```

match_field 示例：

```json
{"session_id":"case_a","action":"stream.query","args":{"stream":"ready_stream","query":"match_field","match":{"field":"low8","op":"==","value":"8'h05"},"time_range":{"begin":"0ns","end":"200ns"},"limit":5}}
```

### 失败返回评审

猜 `query:"transfer"` 时返回：

```text
code: INVALID_REQUEST
message: unsupported stream.query type: transfer
recoverable: true
```

这是 handler 层错误，但缺最关键的 `allowed_values`。schema 也没有枚举 query string，所以 AI 很容易猜错。

缺少 `query` 时 schema 返回：

```text
invalid_arg: args.query
expected: oneOf schema
received_type: missing
correct_example.args.query: summary
```

旧 match 简写 `{opcode:"8'h5a"}` 返回：

```text
invalid_arg: args.match.field
message: required property 'field' not found
```

能指向新结构，但没有专门提示“不要用字段名简写，使用 {field,op,value}”。

stream 不存在错误同 validate，缺 available streams。

### 成功返回评审

`summary` 返回 transfer/stall/packet/XZ 等统计；`first_transfer` 额外返回 row；`match_field` 返回 match_count 和 rows。

优点：

- debug 价值高，尤其是 `first_transfer` row 直接给 time、fields、channel。
- summary 里的 `hint: use stream.export for large result` 有助于下一步。

问题：

- `summary` 查询也返回 `truncated:true`，这会误导 AI 以为 summary 不完整。
- `query` 可用值没有出现在 schema 或错误 allowed_values 中。
- `match_field` 查不到时只 `match_count:0`，没有展示可用字段列表。

### 结论

- 能力强，但入口复杂度高。
- 最大 AI 迷惑点是 `query` string 没有枚举，且“transfer”这种自然词不支持。

### 修改建议

- schema 把 query string 收紧为 enum，或 handler 错误返回 `allowed_values`。
- 对 `query:"transfer"` 给 `did_you_mean:"transfer_window"` 或 `first_transfer/last_transfer`。
- 对旧 match 简写返回 `suggestion:"use match:{field,op,value}"`。
- summary query 不应标 `truncated:true`，或改成 `rows_truncated:true`。

### Agent Review

独立 agent 认为 query 值无 enum/handler allowed_values 缺失是核心问题；truncated 语义建议进一步确认。

## 42. `stream.export`

### 调用覆盖

- MCP query 成功调用：`transfer/tsv/output.path`
- MCP query schema 错误：`packet_beats` 缺 `output`
- MCP query schema 错误：非法 `kind`
- MCP query schema 错误：旧字段 `name`
- raw_request 成功调用

### 能力与入口形态

`stream.export` 将 stream 查询结果写到文件。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "stream.export",
  "args": {
    "stream": "ready_stream",
    "kind": "transfer",
    "format": "tsv",
    "time_range": {"begin": "0ns", "end": "200ns"},
    "output": {"path": "<repo>/tmp/ready_stream.tsv"}
  }
}
```

### 失败返回评审

`packet_beats` 缺 output 返回：

```text
invalid_arg: args.output
message: required property 'output' not found
correct_example.kind: transfer
```

问题：错误是因为 `kind=packet_beats` 条件要求 output，但 correct_example 却给 `kind:"transfer"`，没有展示 packet_beats 的正确修法。

非法 kind 返回：

```text
invalid_arg: args.kind
allowed_values: ["transfer","packet","packet_beats"]
```

很好。

旧 `name` 字段返回：

```text
invalid_arg: args.name
did_you_mean: args.stream
```

很好。

### 成功返回评审

成功 xout：

```text
summary:
  stream: ready_stream
  transfer_count: 11
  truncated: false

data:
  output_file: <repo>/tmp/xdebug_stream_ready_transfer.tsv
  meta_file: <repo>/tmp/xdebug_stream_ready_transfer.tsv.meta.json
  kind: transfer
  format: tsv
  row_count: 11
```

对 debug 的价值：

- `output_file/meta_file/kind/format/row_count` 足够后续脚本处理。
- summary 保留 stream 动态统计。

风险：

- 入参统一为 `output.path`，返回为 `output_file/meta_file`；命名不一致。
- 默认输出本机绝对路径。
- `kind=transfer` 似乎也接受 output，但 schema 只要求 packet_beats 时 output；如果不传 output 的行为需要确认。

### 结论

- 成功返回可用。
- 条件 required 错误的 correct_example 不匹配触发场景。
- output path 命名问题与 `list.export` 一致。

### 修改建议

- 条件 required 错误应保留用户选择的 kind，并给对应正确示例：

```json
{"stream":"ready_packet","kind":"packet_beats","format":"tsv","output":{"path":"<repo>/tmp/ready_packet_beats.tsv"}}
```

- response 使用 `output.path` / `output.meta_path` 或同时提供。
- 对所有 file-export action 统一 path redaction 和字段命名。

### Agent Review

独立 agent 认可 packet_beats 条件示例不匹配问题；kind=transfer 无 output 行为仍需确认。

## 33. `event.config.load`

### 调用覆盖

- MCP query 成功调用：`name + config_path`
- MCP query schema 错误：误把 `clock` 直接写进 args
- MCP query schema 错误：缺少 `name`
- MCP query handler 错误：`config_path` 不存在

### 能力与入口形态

`event.config.load` 保存事件查询配置。当前合同要求 request args 只传 `name` 和可选 `config_path/time_unit`；`clock/rst_n/signals/fields` 来自配置文件内容。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "event.config.load",
  "args": {
    "name": "evt0",
    "config_path": "xdebug/configs/event0.json"
  }
}
```

### 失败返回评审

误把 `clock` 直接放进 args 时返回：

```text
code: INVALID_REQUEST
invalid_arg: args.clock
expected: no additional properties allowed
schema_path: schemas/v1/actions/event.config.load.request.schema.json
correct_example.args: {name:"if0", config_path:"events.json"}
```

这个 schema 错误能阻止文档中曾经出现过的错误用法，但没有直接说明“clock 应写在 config 文件里，不是 request args”。

缺少 `name` 时返回：

```text
invalid_arg: args.name
received_type: missing
```

较清楚。

`config_path` 不存在时返回：

```text
code: INVALID_REQUEST
message: config file not found: <repo>/tmp/no_such_event_config.json
recoverable: true
```

handler 错误不足：

- 缺 `invalid_arg:"args.config_path"`。
- 缺 `expected:"existing JSON config file path"`。
- 缺 `correct_example` 和配置文件最小结构提示。

### 成功返回评审

成功 xout：

```text
summary:
  name: evt0
  status: loaded

config:
  clock: ai_complex_top.clk
  rst_n: ai_complex_top.rst_n
  edge: posedge
  sample_point: before

signals:
  payload/rdy/vld/xz

payload_lo:
  signal: payload
  left: 3
  right: 0
```

对 debug 的价值：

- 成功返回直接展示 clock、reset、edge、signals 和 fields，对确认配置内容很有用。
- 对 AI 后续写 `expr` 很关键，因为 aliases 和 fields 都可见。

冗余/风险：

- `summary` 和 `data` 都有 `name/status`，轻微重复。
- fields 被按字段名展开为顶层块，多个 fields 时可读，但缺一个明确的 `fields:` header。

### 结论

- 成功返回调试价值高。
- schema 层能阻止 inline clock/signals，但提示还不够解释为什么。
- handler path 错误需要结构化。

### 修改建议

- 对 `args.clock/signals/rst_n` 额外字段返回 `suggestion:"put clock/signals/rst_n in the config file content, not request args"`。
- `config_path` 不存在错误补 `invalid_arg/expected/correct_example`。
- 成功 xout 用 `fields:` 包装 field list，避免字段块和其它 top-level 区域混杂。

### Agent Review

独立 agent 认可 aliases/fields 价值和 args.clock 错误问题；fields 顶层展开风险可补更多证据。

## 34. `event.config.list`

### 调用覆盖

- MCP query 成功调用：`args:{}`
- MCP query schema 错误：不支持 `filter`
- raw_request 成功调用

### 能力与入口形态

`event.config.list` 列出已加载 event 配置。MCP query 形态：

```json
{"session_id":"case_a","action":"event.config.list","args":{}}
```

### 失败返回评审

误传 `filter` 返回：

```text
invalid_arg: args.filter
expected: no additional properties allowed
correct_example.args.limit: 5
```

清晰度评价：

- 能明确 `filter` 不支持。
- 没有提示“先 list 再本地过滤”。
- correct_example 给 `limit`，但没有说明 `name` 可用于查询单个配置摘要。

### 成功返回评审

成功 xout：

```text
data:
  count: 1

events:
  evt0
```

对 debug 的价值：

- 简洁，能列出配置名。

不足：

- 缺 summary 层，不符合大多数 action 的 compact 风格。
- 只列 name，不显示 clock、signal_count、fields_count；AI 仍需调用其它 action 或记忆 load 输出。

### 结论

- 参数简单，成功输出可用但信息偏少。
- 缺 summary 是一致性问题。

### 修改建议

- 增加 summary：`count`、可选 `names`。
- events 表增加 `clock/edge/signal_count/field_count`。
- 对 filter 错误给本地过滤建议。

### Agent Review

独立 agent 认为成功输出偏少和 filter 替代建议缺失合理；name 查询单个配置若未实测应保留条件语气。

## 35. `event.find`

### 调用覆盖

- MCP query 成功调用：使用已加载 `name:"evt0"`
- MCP query 成功调用：inline `clock + signals`
- MCP query 成功但空结果：`vld && rdy`
- MCP query schema 错误：缺少 `name` 或 `clock+signals`
- MCP query handler 错误：表达式 alias 不存在
- raw_request 成功调用
- raw_request schema 错误：缺少 `name` 或 `clock+signals`

### 能力与入口形态

`event.find` 查找满足表达式的事件样例。MCP query 可用两种形态：

```json
{"session_id":"case_a","action":"event.find","args":{"name":"evt0","expr":"vld && !rdy","time_range":{"begin":"0ns","end":"200ns"},"limit":5}}
```

或 inline：

```json
{
  "session_id": "case_a",
  "action": "event.find",
  "args": {
    "clock": "ai_complex_top.clk",
    "signals": {"vld":"ai_complex_top.event_vld","rdy":"ai_complex_top.event_rdy"},
    "expr": "vld && !rdy",
    "time_range": {"begin":"0ns","end":"200ns"},
    "limit": 5
  }
}
```

### 失败返回评审

缺少配置来源时返回：

```text
code: INVALID_REQUEST
invalid_arg: args
required_any_of: ["args.name", "args.clock + args.signals"]
message: provide one of: args.name or args.clock + args.signals
```

这是较好的 anyOf 错误，能让 AI 直接补齐。

表达式 alias 不存在时返回：

```text
code: EVENT_FAILED
message: Unknown alias in expression: bad_alias
recoverable: true
```

handler 错误不足：

- 缺 `invalid_arg:"args.expr"`。
- 缺 `unknown_alias:"bad_alias"`。
- 缺 `available_aliases:["vld","rdy","payload","xz","payload_lo"]`。
- 缺修正示例。

### 成功返回评审

非空命中 xout：

```text
summary:
  event_count: 1
  mode: first
  inline: false
  sampling_mode: clock_edge
  clock: ai_complex_top.clk
  edge: posedge
  sample_point: before
  first: 115ns
  last: 115ns

events:
  time   signals                                                                     fields
  115ns  payload=8'h5a rdy=1'h0 vld=1'h1 xz=8'hzz known=false bits=zzzzzzzz width=8  payload_lo=4'ha
```

对 debug 的价值：

- summary 包含 event_count、clock/edge/sample_point、first/last，价值高。
- events 表同时显示 alias 值和 field 值，能解释为什么 expr 命中。
- `known=false/bits/width` 对 x/z 诊断有用。

冗余/风险：

- events 表下方又混入 `first/last/begin/end/sampling_mode/clock/edge` 这些 summary 字段，层级不清。
- inline 和 config 模式 edge 默认不同：配置为 posedge before，inline 默认 negedge；这很容易造成时间差异。成功返回显示了 edge，但如果 AI 没注意会误比两个结果。

### 结论

- 成功返回 debug 价值高。
- 参数复杂度较高，但 anyOf 错误做得不错。
- handler expression 错误需要列可用 aliases。

### 修改建议

- `EVENT_FAILED Unknown alias` 增加结构化字段：

```json
{
  "invalid_arg": "args.expr",
  "unknown_alias": "bad_alias",
  "available_aliases": ["vld","rdy","payload","xz","payload_lo"]
}
```

- xout events block 只放 rows；begin/end/clock/edge 放 summary/data。
- inline 模式如果未显式 edge/sample_point，返回 warning 或在 summary 显示 `edge_source:default`。

### Agent Review

独立 agent 认为 anyOf、unknown alias、metadata 混表问题证据充分；inline/config edge 差异应说明来自本轮对比。

## 36. `event.export`

### 调用覆盖

- MCP query 成功调用：`name/expr/time_range/limit`
- MCP query schema 错误：误传 `output.path`

### 能力与入口形态

`event.export` 名称像导出，但当前 request schema 不接受 `output.path`，而是返回更多 event 数据或 aggregate 结果。MCP query 形态：

```json
{"session_id":"case_a","action":"event.export","args":{"name":"evt0","expr":"vld && !rdy","time_range":{"begin":"0ns","end":"200ns"},"limit":1}}
```

### 失败返回评审

误传 `args.output` 返回：

```text
invalid_arg: args.output
expected: no additional properties allowed
schema_path: schemas/v1/actions/event.export.request.schema.json
correct_example.args: {clock, signals, expr, limit}
```

问题：

- 对一个叫 `export` 的 action，不接受 output path 容易违背直觉。
- 错误没有说明“event.export currently returns events in response; it does not write to file”。
- correct_example 没有给 name/config 模式，只给 inline 模式。

### 成功返回评审

成功 xout 和 `event.find` 非常接近：

```text
summary:
  event_count: 1
  mode: export
  inline: false
  first: 115ns
  last: 115ns

events:
  115ns payload=8'h5a rdy=1'h0 vld=1'h1 ...
```

对 debug 的价值：

- 和 find 一样，单个事件信息完整。
- mode 显示为 export，能区分 action。

风险：

- 能力边界和 `event.find` 重叠很大；如果只是 mode 不同，AI 不知道什么时候用 export。
- 不接受 output path 但 action 名叫 export，会让 AI 自然猜 `output.path`。
- 如果 export 用于 aggregate 或更多 rows，schema 里 `aggregate/group_by/events` object/array 约束太松，AI 容易到 handler 层才失败。

### 结论

- 成功返回有 debug 价值，但与 `event.find` 边界不够清晰。
- 名称和参数合同冲突：`export` 不写文件。

### 修改建议

- docs/xout 明确：
  - `event.find`：找少量样例，默认 first/sample。
  - `event.export`：返回更完整事件集或 aggregate，不写文件。
- 若长期保留 `export` 名称，考虑支持 `output.path`；否则改名或在错误里加清晰提示。
- 对 `args.output` 错误返回 `suggestion:"event.export returns events in response; use limits/aggregate, not output.path"`。
- 收紧 `aggregate` schema。

### Agent Review

独立 agent 认可 export 名称与 output.path 直觉冲突；aggregate/schema 过松需要补 schema review。

## 30. `list.diff`

### 调用覆盖

- MCP query 成功调用：`name/time_range`
- MCP query schema 错误：误用顶层 `begin/end`
- raw_request 成功调用

### 能力与入口形态

`list.diff` 在时间窗口内查找 list 中信号首次出现差异的时间。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "list.diff",
  "args": {
    "name": "review_list",
    "time_range": {"begin": "0ns", "end": "200ns"}
  }
}
```

### 失败返回评审

误用 `begin/end` 顶层字段时返回：

```text
code: INVALID_REQUEST
invalid_arg: args.time_range
message: required property 'time_range' not found
correct_example.args.time_range.begin/end
```

问题：

- 和 `signal.changes` 不同，这里没有对 `args.begin` 返回 `did_you_mean: args.time_range.begin`，而是报缺少整个 `time_range`。
- 因为 `begin/end` 是 additionalProperties，同时 `time_range` required，错误选择了 required 缺失而非额外字段，更不利于自动修复。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  diff_found: true
  diff_time: 0ns
```

raw_request 后续成功返回 `diff_time:55ns`，原因是同一 session 中先执行了 `list.delete(index:3)` 删除了一个 signal，list 状态发生变化。

对 debug 的价值：

- `diff_found/diff_time` 直接回答问题，很紧凑。

不足：

- 不显示是哪两个/哪些信号出现差异，也不显示对应值。
- 对状态依赖强；如果 list 被修改，结果改变但 response 不包含 list version 或 signal_count。

### 结论

- 成功返回过于简略，只适合作为“有无差异”初筛。
- 错误提示未复用 `did_you_mean` 迁移逻辑。

### 修改建议

- 成功返回增加：

```text
summary:
  diff_found: true
  diff_time: 0ns
  signal_count: 3
  differing_signals: [...]
```

- 对顶层 `begin/end` 返回 `did_you_mean`。
- 返回 `list_revision` 或至少 `signal_count`，帮助解释状态依赖。

### Agent Review

独立 agent 认为 begin/end did_you_mean 缺失证据充分；raw/query 状态差异应归类为状态依赖风险。

## 31. `list.export`

### 调用覆盖

- MCP query handler 错误：窗口小于 256ns
- MCP query schema 错误：非法 `format:"json"`
- MCP query schema 错误：旧字段 `output_file`
- MCP query 成功调用：`output.path`
- raw_request 成功调用

### 能力与入口形态

`list.export` 导出 list 中信号的窗口数据，目前 format 仅支持 `u64bin`，路径统一放在 `args.output.path`：

```json
{
  "session_id": "case_a",
  "action": "list.export",
  "args": {
    "name": "review_list",
    "time_range": {"begin": "0ns", "end": "300ns"},
    "format": "u64bin",
    "output": {"path": "<repo>/tmp/xdebug_action_review_20260709_review_list"}
  }
}
```

### 失败返回评审

窗口过小时返回：

```text
code: TIME_RANGE_TOO_SMALL
message: list.export requires at least 256ns; use list.value_at or value.batch_at for point reads
recoverable: true
```

这是一个好的 handler 层错误：

- 说明最小窗口约束。
- 直接给出替代 action，能指导 AI 改策略。

不足：

- 缺 `invalid_arg:"args.time_range"`。
- 缺 `min_duration:"256ns"` 和可执行 corrected example。

非法 format 返回：

```text
invalid_arg: args.format
allowed_values: ["u64bin"]
correct_example.args.format: u64bin
```

旧字段 `output_file` 返回：

```text
invalid_arg: args.output_file
expected: no additional properties allowed
correct_example.args.output.path: <repo>/tmp/if0_list_export
```

缺点：没有 `did_you_mean:"args.output.path"`。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  signal_count: 3
  row_count: 9
  format: u64bin.v1

data:
  output_dir: <repo>/tmp/...
  manifest_file: <repo>/tmp/.../manifest.json

signals:
  index  signal  file  row_count  width  word_count  columns
  0      ...
```

对 debug 的价值：

- `signal_count/row_count/format/manifest_file` 对后续离线分析有用。
- 每个 signal 的 file/row_count/width 清楚。

风险：

- 入参叫 `output.path`，成功返回叫 `output_dir`，容易让 AI 误以为 path 必须是目录。schema description 也说“路径”，但实际是输出目录。
- signals 表 index 从 0 开始，而 `list.show` 显示 index 从 1 开始，和 `list.delete(index)` 语义冲突风险高。
- 默认 xout 暴露本机绝对路径。

### 结论

- 成功返回对导出调试有用。
- 错误提示中 `TIME_RANGE_TOO_SMALL` 是正面样本。
- 主要问题是 output path/dir 命名不一致，以及 index base 不一致。

### 修改建议

- schema 把 `output.path` 描述明确为 output directory，或改为 `output.dir`；若保持 `path`，response 使用 `output.path` 而不是 `output_dir`。
- `output_file` 错误增加 `did_you_mean:"args.output.path"`。
- export signals 表不要使用容易和 list index 混淆的 `index`；改成 `file_index` 或 `row_index_base:0`。
- compact 输出路径做相对/脱敏。

### Agent Review

独立 agent 认可 output path/index base 问题；建议核准 format=json 属于 schema 还是 handler 错误。

## 32. `list.delete`

### 调用覆盖

- MCP query 成功调用：`index:3`
- MCP query schema 错误：缺少 `signal/index`
- MCP query handler 错误：index 越界
- MCP query handler 错误：list 不存在
- raw_request schema 错误：缺少 `signal/index`

### 能力与入口形态

`list.delete` 从 list 删除一个 signal，可以通过 signal path 或 index 指定。MCP query 形态：

```json
{"session_id":"case_a","action":"list.delete","args":{"name":"review_list","index":3}}
```

或：

```json
{"session_id":"case_a","action":"list.delete","args":{"name":"review_list","signal":"ai_complex_top.sig_a"}}
```

### 失败返回评审

缺少 `signal/index` 时 schema 返回：

```text
code: INVALID_REQUEST
invalid_arg: args
required_any_of: ["args.signal","args.index"]
message: provide one of: args.signal or args.index
```

这是较好的 anyOf 错误，能告诉 AI 必须二选一。缺点仍是 correct_example 为 native envelope。

index 越界或 list 不存在时均返回：

```text
code: DEL_FAILED
message: action failed
recoverable: true
```

这是不可恢复的 handler 错误：

- 没有说明是 index 越界、signal 不存在还是 list 不存在。
- 没有 `invalid_arg`。
- 没有合法 index range。
- 没有 available lists。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  deleted: true
  removed: 3
```

问题：

- `removed:3` 看起来像删除了 3 个 item，但实际是删除 index 3 或第 3 个 signal。字段名非常容易误读。
- 不显示被删除的 signal path。
- 不显示删除后 count。

### 结论

- schema anyOf 错误做得不错。
- handler 错误严重不足。
- 成功返回字段 `removed` 语义不清，和 index base 问题叠加会误导 AI。

### 修改建议

- 成功返回改为：

```text
summary:
  name: review_list
  deleted: true
  removed_index: 3
  removed_signal: ai_complex_top.hs_valid
  count_after: 2
  index_base: 1
```

- index 越界返回：

```json
{
  "code": "LIST_INDEX_OUT_OF_RANGE",
  "invalid_arg": "args.index",
  "received": 99,
  "valid_range": "1..2",
  "index_base": 1
}
```

- list 不存在返回统一 `LIST_NOT_FOUND`，不要泛化成 `DEL_FAILED`。

### Agent Review

独立 agent 认为 anyOf 好、DEL_FAILED 差、removed:3 易误解均有证据，应列为同族高优先级。

## 25. `list.create`

### 调用覆盖

- MCP query 成功调用：`name + signals[]`
- MCP query schema 错误：缺少 `name`

### 能力与入口形态

`list.create` 创建命名信号列表，可带初始 signals。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "list.create",
  "args": {
    "name": "review_list",
    "signals": ["ai_complex_top.sig_a", "ai_complex_top.sig_b"]
  }
}
```

### 失败返回评审

缺少 `name` 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.name
expected: type "string"
received_type: missing
schema_path: schemas/v1/actions/list.create.request.schema.json
correct_example.args.name: if0
```

清晰度评价：

- schema 层缺字段提示清楚。
- `correct_example` 是 native envelope，路径是占位 `top.u.*`。

### Handler 层错误评审

本轮没有触发 list name 冲突错误；首次创建成功。需要后续补一个 duplicate name 行为确认：如果重复 create 覆盖、返回 existing，还是失败，必须在 docs 和 error 中明确。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  status: created
  created: true
```

优点：

- 简洁，能确认列表名和创建状态。

不足：

- 创建时传入了两个 initial signals，但成功返回不显示 `signal_count`，需要再调用 `list.show` 才确认内容。
- 如果 initial signals 里有坏路径，当前未在本节覆盖；应确认 create 是接受未验证路径还是即时校验。

### 结论

- 参数简单，成功返回过于简略。
- 作为状态创建 action，建议返回创建后的 list 摘要。

### 修改建议

- 成功返回增加 `signal_count` 和可选前 N 个 signals。
- duplicate create 行为需要 schema/handler/docs 明确。
- 如果 `signals` 支持 alias object，应和 `value.batch_at` 一样检查 schema/runtime 一致。

### Agent Review

独立 agent 认为成功返回缺 signal_count 有证据；duplicate/bad signal 未覆盖已被如实说明。

## 26. `list.add`

### 调用覆盖

- MCP query 成功调用：向 `review_list` 添加 `ai_complex_top.hs_valid`
- MCP query handler 错误：list 不存在
- MCP query handler 错误：signal 不存在
- raw_request handler 错误：list 不存在

### 能力与入口形态

`list.add` 向已有 list 追加一个 signal。MCP query 形态：

```json
{"session_id":"case_a","action":"list.add","args":{"name":"review_list","signal":"ai_complex_top.hs_valid"}}
```

### 失败返回评审

list 不存在时返回：

```text
code: ADD_FAILED
message: ai_complex_top.sig_a
recoverable: true
```

这是本组最差的错误提示：

- code 没说 list 不存在。
- message 只是 signal 名，反而掩盖真正错误。
- 缺 `invalid_arg:"args.name"`。
- 缺 `list_name/no_such_list`、`available_lists` 和 `next_action:"list.show"`。
- raw_request 也只是把同样坏错误包在 `stdout_tail` 中。

signal 不存在时返回：

```text
code: SIGNAL_NOT_FOUND
message: ai_complex_top.no_such
recoverable: true
```

这个错误至少 code 对，但仍缺 `invalid_arg:"args.signal"`、候选和 scope next action。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  signal: ai_complex_top.hs_valid
  status: added
  added: true
```

优点：

- 简洁直接。

不足：

- 不显示追加后的 `signal_count`。
- 如果 signal 已存在，是否去重/重复追加不明确。

### 结论

- 成功返回可用。
- handler 错误质量不足，尤其 list 不存在时几乎不能指导 AI 修复。

### 修改建议

- list 不存在时返回：

```json
{
  "code": "LIST_NOT_FOUND",
  "invalid_arg": "args.name",
  "missing_name": "no_such_list",
  "suggestion": "call list.show without name to list available lists, or call list.create first",
  "mcp_correct_example": {"session_id":"case_a","action":"list.create","args":{"name":"no_such_list"}}
}
```

- signal 不存在时复用统一 path-not-found 结构。
- 成功返回增加 `signal_count` 和 `already_exists`。

### Agent Review

独立 agent 认为 list 不存在错误不可恢复的证据强；成功返回缺 count/already_exists 是明确遗漏。

## 27. `list.show`

### 调用覆盖

- MCP query 成功调用：指定 `name`
- MCP query handler 错误：list 不存在
- MCP query schema 错误：不支持 `filter`
- raw_request 成功调用

### 能力与入口形态

`list.show` 展示一个 list 内容；`name` 是可选字段，省略时应展示所有 list 或默认列表视实现而定。MCP query 形态：

```json
{"session_id":"case_a","action":"list.show","args":{"name":"review_list"}}
```

### 失败返回评审

list 不存在返回：

```text
code: LIST_NOT_FOUND
message: no_such_list
recoverable: true
```

问题：

- code 比 `list.add` 好，但仍缺 `invalid_arg:"args.name"`。
- 没有 `available_lists` 或建议省略 name 查看全部。

误传 `filter` 返回：

```text
invalid_arg: args.filter
expected: no additional properties allowed
correct_example.args: {}
```

这能说明 filter 不被支持，但没有告诉用户“先 show 再本地过滤”。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  signal_count: 3

signals:
  index  signal
  1      ai_complex_top.sig_a
  2      ai_complex_top.sig_b
  3      ai_complex_top.hs_valid
```

对 debug 的价值：

- `signal_count` 和 index 表很清楚。
- index 从 1 开始，可直接用于 `list.delete(index)`，但 docs/输出没有强调 index base。

不足：

- 如果 list 中支持 alias，当前表没有 alias column。
- 不存在 list 错误没有给可用列表。

### 结论

- 成功返回很适合 debug。
- handler 错误可读但不够可恢复。

### 修改建议

- `LIST_NOT_FOUND` 增加 `invalid_arg/available_lists/next_action`。
- signals 表增加 `alias` column 或明确 list 只保存 paths。
- summary 增加 `index_base:1`，避免 delete index 误用。

### Agent Review

独立 agent 认可 index_base 风险；name 省略行为缺实测证据，不宜当事实写死。

## 28. `list.value_at`

### 调用覆盖

- MCP query 成功调用：读取 `review_list` 在 10ns 的 values
- MCP query schema 错误：缺少 `clock`
- raw_request 成功调用
- raw_request schema 错误：缺少 `clock`

### 能力与入口形态

`list.value_at` 对 list 内所有信号做同一时间点批量读取。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "list.value_at",
  "args": {
    "name": "review_list",
    "time": "10ns",
    "clock": "ai_complex_top.clk"
  }
}
```

### 失败返回评审

缺少 `clock` 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.clock
expected: type "string"
received_type: missing
schema_path: schemas/v1/actions/list.value_at.request.schema.json
correct_example.args.clock: top.u.clk
```

优点：

- required 字段清晰。

不足：

- correct_example 仍是占位路径/native envelope。
- 如果 list 不存在或 clock 不存在，预计会走 handler 错误；本节未重复触发，统一按 `list.show` 和 `value.at` 的问题处理。

### 成功返回评审

成功 xout：

```text
target:
  name: review_list
  time: 10ns

values:
  signal                   before  middle  after
  ai_complex_top.sig_a     'h00    'h00    'h00
  ai_complex_top.sig_b     'h00    'h00    'h00
  ai_complex_top.hs_valid  'h0     'h0     'h0
```

对 debug 的价值：

- 和 `value.batch_at` 输出一致，适合比较信号组。
- `before/middle/after` 保留采样边界信息。

不足：

- target 不显示 `clock/edge`，不如 `value.at` 完整。
- summary 缺 `signal_count/missing_signal_count`。
- 如果 list 中某个 signal 过期，是否 partial 成功需要明确计数。

### 结论

- 成功返回很有用。
- 缺少 clock/edge 和 partial summary，影响自动化判断。

### 修改建议

- target 增加 `clock/edge`。
- summary 增加 `signal_count/ok_count/missing_count/partial_failure`。
- 错误示例增加 MCP 壳。

### Agent Review

独立 agent 认为成功表格评价合理；list/clock 错误引用同类问题时应标注未重复验证。

## 29. `list.validate`

### 调用覆盖

- MCP query 成功调用：验证 `review_list`
- MCP query handler 错误：list 不存在

### 能力与入口形态

`list.validate` 检查 list 内 signal 是否存在。MCP query 形态：

```json
{"session_id":"case_a","action":"list.validate","args":{"name":"review_list"}}
```

### 失败返回评审

list 不存在返回：

```text
code: LIST_NOT_FOUND
message: no_such_list
recoverable: true
```

问题同 `list.show`：缺 `invalid_arg/available_lists/next_action`。

### 成功返回评审

成功 xout：

```text
summary:
  name: review_list
  all_found: true

signals:
  signal                   status
  ai_complex_top.sig_a     ok
  ai_complex_top.sig_b     ok
  ai_complex_top.hs_valid  ok
```

对 debug 的价值：

- `all_found` 一眼能看出 list 是否可用。
- 每个 signal 的 status 表适合定位坏路径。

不足：

- summary 缺 `ok_count/missing_count`。
- 如果 missing，建议返回 `missing_signals[]` 和 `next_actions`。

### 结论

- 成功返回清楚。
- list 不存在错误仍需结构化恢复信息。

### 修改建议

- summary 增加 `signal_count/ok_count/missing_count`。
- list not found 错误复用统一结构。
- missing signal 行增加建议 `scope.list/signal.resolve`。

### Agent Review

独立 agent 认可 list not found 缺结构化字段；missing signal 建议需要实际输出样例支撑。

## 21. `signal.changes`

### 调用覆盖

- MCP query 成功调用：`signal/time_range/limit`
- MCP query schema 错误：旧字段 `begin/end`
- MCP query 兼容路径：`time_range.from/to` 被接受并归一化为 `begin/end`
- raw_request 成功调用
- raw_request schema 错误：旧字段 `begin/end`

### 能力与入口形态

`signal.changes` 读取单个信号的 value-change timeline。MCP query 推荐形态：

```json
{
  "session_id": "case_a",
  "action": "signal.changes",
  "args": {
    "signal": "ai_complex_top.sig_a",
    "time_range": {"begin": "0ns", "end": "200ns"},
    "limit": 5
  }
}
```

### 失败返回评审

误用旧顶层窗口字段 `begin/end` 时返回：

```text
code: INVALID_REQUEST
invalid_arg: args.begin
did_you_mean: args.time_range.begin
message: ... use args.time_range.begin instead
correct_example.args.time_range.begin/end
```

清晰度评价：

- 这是目前较好的错误提示样本：明确指出旧字段和新字段映射。
- `did_you_mean` 对 AI 自动修复很有用。
- 仍然缺 MCP 壳示例，`correct_example` 是 native envelope。

`time_range.from/to` 被 runtime 接受并等价返回 `begin:0ns/end:200ns`。这对兼容旧调用友好，但和“对外合同统一为 `time_range.begin/end`”存在漂移风险：AI 可能继续传播 `from/to`。

### Handler 层错误评审

本轮未单独构造 `signal` 不存在；同类错误已在 `value.at` / `signal.stability` 覆盖，当前 handler path-not-found 仍需 `invalid_arg/near_matches/next_actions`。

### 成功返回评审

成功 xout：

```text
summary:
  signal: ai_complex_top.sig_a
  returned_change_rows: 3
  actual_transition_count: 2
  truncated: false

data:
  includes_initial_value: true
  semantic_note: signal.changes returns value-change rows...
  initial_value/final_value/first_change/last_change
```

对 debug 的价值：

- `returned_change_rows` 和 `actual_transition_count` 区分初始值行和真实跳变，很有价值。
- `semantic_note` 明确提醒不要把 row count 当 sampled high cycles，这能防止常见误读。
- `initial/final/first/last` 足够做快速定位。

冗余/风险：

- `transition_count` 与 `actual_transition_count` 同时出现，可能让 AI 疑惑二者是否不同。
- 默认 xout 没展示具体 changes rows，只展示 summary；对 limit=5 的 timeline 检查可能需要 rows。

### 结论

- 成功返回有高 debug 价值，尤其是 semantic_note。
- schema 错误对旧字段迁移做得好。
- 主要问题是 `time_range.from/to` 仍被接受，和当前合同收敛方向冲突。

### 修改建议

- 若保留 `from/to` 兼容，应返回 warning：`deprecated: use time_range.begin/end`。
- 或在 schema/runtime 都拒绝 `from/to`，统一提示 `did_you_mean`。
- `transition_count` 与 `actual_transition_count` 保留一个主字段，另一个作为 alias 不在 compact 中显示。
- compact 在 rows 数较小时展示 changes rows；或明确提示 `aggregate_only:false` / `limit` 的输出行为。

### Agent Review

独立 agent 认可 begin/end did_you_mean 与 from/to 兼容漂移问题；transition_count 混淆判断有证据。

## 22. `signal.statistics`

### 调用覆盖

- MCP query 成功调用：`signal/clock/time_range/limit`
- MCP query handler 错误：clock 不存在
- raw_request 成功调用

### 能力与入口形态

`signal.statistics` 统计 signal 活动；带 `clock` 时按 clock edge 采样。MCP query 推荐形态：

```json
{
  "session_id": "case_a",
  "action": "signal.statistics",
  "args": {
    "signal": "ai_complex_top.hs_valid",
    "clock": "ai_complex_top.clk",
    "time_range": {"begin": "120ns", "end": "210ns"},
    "limit": 1000
  }
}
```

### 失败返回评审

clock 不存在返回：

```text
code: ACTION_FAILED
message: Clock signal not found: top.clk
invalid_arg: args.clock
expected: existing clock signal path
correct_example.args.clock: top.clk
```

问题：

- `invalid_arg/expected` 有用。
- `correct_example` 回显坏 clock，不能作为修复模板。
- 缺少 `next_actions:["scope.roots","scope.list"]` 或 clock 候选。

### 成功返回评审

成功 xout：

```text
summary:
  sampling_mode: clock_edge
  clock: ai_complex_top.clk
  edge: negedge
  sample_count: 10
  known_count: 10
  unknown_count: 0
  truncated: false

data:
  transition_count: 2
  first/final/min/max
  low_cycles/high_cycles/high_ratio

activity:
  high_burst_count
  first_high_time/last_high_time/last_fall_time
  max_high_cycles
```

对 debug 的价值：

- `sampling_mode/edge/sample_time_semantics` 清楚说明统计语义。
- `high_cycles/high_ratio` 和 activity burst 对 valid/ready 类信号很有用。
- `first_change_time/last_change_time` 方便定位窗口。

冗余/风险：

- summary 和 data 重复 `sampling_mode/clock/edge/truncated`。
- `limit` 对统计扫描的含义不够直观，是限制 samples、changes 还是 returned rows 需要说明。
- 如果无 clock 模式也支持，response 应清楚区分 raw-change statistics vs clock-sampled statistics。

### 结论

- 成功返回 debug 价值很高。
- 主要缺陷仍是 handler path-not-found 的修复建议不足。
- 参数复杂度中等，`signal` 必填但 `clock` 可选会让 AI 误以为 clock 不是统计 valid 的必要条件；docs 应强调有 clock 才是采样周期统计。

### 修改建议

- clock not found 错误不要回显坏 clock；提供 `scope.roots/scope.list` 下一步。
- response compact 去掉 summary/data 重复字段。
- schema/docs 明确 `limit` 语义。

### Agent Review

独立 agent 认可 clock not found 回显坏值；关于 clock 可选的影响建议改成文档说明采样模式差异。

## 23. `signal.stability`

### 调用覆盖

- MCP query 成功调用：稳定信号 `stable_sig`
- MCP query handler 错误：信号不存在
- raw_request 成功调用

### 能力与入口形态

`signal.stability` 判断单信号在窗口内是否稳定。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "signal.stability",
  "args": {
    "signal": "ai_complex_top.stable_sig",
    "time_range": {"begin": "0ns", "end": "200ns"}
  }
}
```

### 失败返回评审

信号不存在返回：

```text
code: ACTION_FAILED
message: Signal not found: ai_complex_top.no_such
invalid_arg: args.signal
expected: existing signal path
correct_example.args.signal: ai_complex_top.no_such
```

问题：

- `invalid_arg/expected` 有用。
- `correct_example` 回显坏 signal，不能使用。
- 缺 `near_matches` 和 `next_actions`。

### 成功返回评审

成功 xout：

```text
data:
  signal: ai_complex_top.stable_sig
  begin: 0ns
  end: 200ns

changes:
  time  value
  0ns   1'h1
  transition_count: 1
  stable: true
  value: 1'h1
```

对 debug 的价值：

- `stable:true` 和 stable value 直接回答问题。
- changes 中保留初始值和 transition_count，能解释稳定判断依据。

冗余/风险：

- 缺 summary 层，和大多数 action 的 `summary` 风格不一致。
- `changes` 表下混入 `transition_count/truncated/stable/value` 这类 summary 字段，层级不清。
- `transition_count:1` 但 stable true，只有理解“初始值行不算变化”才不会误读。

### 结论

- action 能力实用，成功信息足够定位稳定性。
- 默认 xout 结构需要整理，尤其是 summary 缺失和 changes 区域混杂字段。

### 修改建议

- 增加 summary：

```text
summary:
  signal: ai_complex_top.stable_sig
  stable: true
  value: 1'h1
  actual_transition_count: 0
```

- changes 区域只放 rows；统计字段放 summary/data。
- signal not found 错误修复同其它 path 错误。

### Agent Review

独立 agent 认为缺 summary、表格混入统计、transition_count 易误读均有证据；建议说明 transition_count 可能含初始值。

## 24. `counter.statistics`

### 调用覆盖

- MCP query 成功调用：`clock/vld/cnt/time_range/limit`
- MCP query schema 错误：缺少 `args.cnt`
- MCP query handler 错误：clock 不存在
- raw_request 成功调用
- raw_request schema 错误：缺少 `args.cnt`

### 能力与入口形态

`counter.statistics` 按 clock 和 valid 条件采样 counter，统计计数行为。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "counter.statistics",
  "args": {
    "clock": "ai_complex_top.clk",
    "vld": "ai_complex_top.counter_inc",
    "cnt": "ai_complex_top.counter_inc",
    "time_range": {"begin": "0ns", "end": "200ns"},
    "limit": 20
  }
}
```

本轮为了覆盖调用，使用了同一个 signal 作为 `vld` 和 `cnt`；这能执行成功，但不是典型计数器用法。

### 失败返回评审

缺少 `cnt` 时：

```text
code: INVALID_REQUEST
invalid_arg: args.cnt
expected: type "string"
received_type: missing
schema_path: schemas/v1/actions/counter.statistics.request.schema.json
correct_example.args.vld: {expr:"valid && ready", signals:{...}}
correct_example.args.cnt: "{top.cnt_hi,top.cnt_lo}"
```

清晰度评价：

- 能准确指出缺 `cnt`。
- 示例展示了 `vld` 可以是 object expr，但 schema 对 vld object 内部没有结构约束；AI 可能复制复杂表达式后到 handler 层才失败。
- correct_example 仍是 native envelope 和占位 top 路径。

clock 不存在时：

```text
code: ACTION_FAILED
message: Clock signal not found: top.clk
invalid_arg: args.clock
expected: existing clock signal path
correct_example.args.clock: top.clk
```

同样存在坏值回显问题。

### 成功返回评审

成功 xout：

```text
summary:
  sampling_mode: clock_edge
  clock: ai_complex_top.clk
  edge: negedge
  sample_count: 20
  valid_count: 15
  unknown_count: 0
  truncated: false

data:
  cnt: ai_complex_top.counter_inc
  vld: ai_complex_top.counter_inc
  min_value: 0
  max_value: 0
  average_value: 0
  min_count: 15
  max_count: 15
```

对 debug 的价值：

- `sample_count/valid_count/valid_false_count` 有用。
- `min/max/average/min_count/max_count` 可以快速看 counter 范围。

不足：

- 对“计数器是否递增、回绕、停顿、异常”的说明不够；缺 `increase_count/decrease_count/stall_count/wrap_count/anomaly_count` 这类直接 debug 字段。
- 当 `vld` 和 `cnt` 相同，输出没有 warning，容易让 AI 把不合理配置当成有效分析。
- `vld` 支持 string 或 object，但 schema 不约束 object 结构，错误可能后移到 handler。

### 结论

- action 参数复杂度高于普通 signal action，尤其是 `vld` 可为表达式对象。
- 成功返回可作为基础统计，但对 counter debug 的根因信息偏弱。
- 错误提示对缺字段较清楚，对 handler path 错误仍不可恢复。

### 修改建议

- response 增加 counter-specific debug 字段：

```text
summary:
  monotonic: true
  increase_count: N
  stall_count: N
  decrease_count: N
  wrap_count: N
  anomaly_count: N
```

- 如果 `vld` 和 `cnt` 是同一路径，返回 warning：`vld_equals_cnt_may_be_unintended`。
- 收紧 `vld` object schema，明确 `expr/signals` required。
- missing/path 错误追加 MCP 示例和 scope next action。

### Agent Review

独立 agent 认可 schema 约束弱与 clock 回显坏值；counter-specific 增强项应表述为建议而非当前目标缺陷。

## 19. `signal.resolve`

### 调用覆盖

- MCP query waveform-only handler 错误：当前主 session 未加载 design
- MCP query design session 调用：action 成功返回，但 domain status 为 `not_found`
- MCP query schema 错误：误用 `args.sig`
- raw_request schema 错误：误用 `args.sig`

### 能力与入口形态

`signal.resolve` 用于在 design database 中解析 signal 并返回匹配候选。MCP query 形态：

```json
{"session_id":"case_a","action":"signal.resolve","args":{"signal":"top.u.ready"}}
```

它不是纯 waveform path lookup；在 waveform-only session 下会返回 `DESIGN_NOT_LOADED`。

### 失败返回评审

waveform-only session 调用返回：

```text
code: DESIGN_NOT_LOADED
message: design not loaded; open session with -dbdir
recoverable: true
```

清晰度评价：

- message 能告诉用户需要 design database。
- 但 MCP 用户需要的是 `xverif_debug_session_open(..., daidir=...)` 示例，而不是 native `-dbdir`。
- 缺少 `missing_resource:"daidir"` 或 `required_session_mode:"design"`。

误用 `sig` 时，schema 错误返回：

```text
invalid_arg: args.signal
received_type: missing
correct_example.target.daidir: simv.daidir
```

问题：

- 没有 `did_you_mean:"args.signal"`，虽然用户传了 `args.sig`。
- correct_example 是 native envelope。

design session 中查询不存在 signal 时，MCP tool 返回成功文本，但 xout 内部 domain summary 为：

```text
summary:
  count: 0
  message: Signal not found: no_such_signal
  ok: false
  status: not_found
```

这说明 action transport 成功和 domain resolution 成功是两层语义。当前 xout 能看懂，但 MCP 顶层不会把它当 error。

### 成功返回评审

本轮在 `xdebug/testdata/design/uart/simv.daidir` 上未拿到非空 match；`scope.roots` 对该 design session 也返回 `design root discovery returned no top handles`。因此没有把 `count:0/status:not_found` 当作有调试价值的成功 match。

已有返回对 debug 的价值：

- 能确认 design session 已可调用该 action。
- 能以 domain status 表达 `not_found`，比抛硬错误更适合批量探索。

不足：

- `ok:false` 出现在 xout summary/data 内部，而 MCP 顶层仍是成功 tool result，AI 需要额外识别 domain ok。
- `not_found` 缺少下一步建议，例如列 design roots、检查 daidir 是否包含可遍历 top、或使用 waveform `scope.list`。

### 结论

- 参数简单，但 session 前置条件容易被 AI 忽略。
- waveform-only 错误提示方向正确，但不是 MCP 壳表达。
- domain-level `ok:false` 与 MCP/tool-level success 的双层语义需要标准化展示。

### 修改建议

- `DESIGN_NOT_LOADED` 增加：

```json
{
  "missing_resource": "daidir",
  "required_session_kind": "design",
  "mcp_correct_example": {"tool":"xverif_debug_session_open","args":{"name":"case_a","daidir":"<simv.daidir>"}}
}
```

- 对 `args.sig` 这类近似字段返回 `did_you_mean:"args.signal"`。
- domain `not_found` 返回增加 `next_actions:["scope.roots","scope.list"]` 和 `checked_sources:["design"]`。

### Agent Review

独立 agent 认为 DESIGN_NOT_LOADED 和双层 not_found 语义问题有证据；成功非空 match 未覆盖，保守评价正确。

## 20. `signal.canonicalize`

### 调用覆盖

- MCP query waveform-only handler 错误：`DESIGN_NOT_LOADED`
- MCP query design session 成功调用：`signal:"uart_top.clk"`
- MCP query schema 错误：误用 `args.sig`
- raw_request 成功调用：design session
- raw_request handler 错误：waveform-only session `DESIGN_NOT_LOADED`

### 能力与入口形态

`signal.canonicalize` 返回信号 canonical 名称。MCP query 形态：

```json
{"session_id":"case_a","action":"signal.canonicalize","args":{"signal":"top.u.ready"}}
```

### 失败返回评审

waveform-only session 返回：

```text
code: DESIGN_NOT_LOADED
message: design not loaded; open session with -dbdir
recoverable: true
```

问题同 `signal.resolve`：缺 MCP session open 示例，缺结构化 `missing_resource`。

误用 `args.sig` 时 schema 返回：

```text
invalid_arg: args.signal
received_type: missing
correct_example.target.daidir: simv.daidir
```

缺 `did_you_mean:"args.signal"`。

### 成功返回评审

design session 成功 xout：

```text
summary:
  query: uart_top.clk
  ambiguous: false

data:
  query: uart_top.clk
  canonical: uart_top.clk
  ambiguous: false
  aliases: [empty]
  fsdb_candidates: [empty]
  port_mappings: [empty]
```

对 debug 的价值：

- `query/canonical/ambiguous` 清晰。
- `aliases/fsdb_candidates/port_mappings` 对跨 design/waveform 映射有潜在价值。

风险：

- 本轮 `signal.resolve` 对同一查询返回 not_found，但 `signal.canonicalize` 仍返回 `canonical: uart_top.clk`，看起来像成功解析。这可能只是字符串规范化，而不是验证路径存在。
- 返回缺少 `resolved:true/exists:true`，AI 可能误把 canonical 字符串当作真实存在的 design signal。

### 结论

- 成功输出简洁，但“canonicalize 是否验证存在”语义不清。
- 和 `signal.resolve` 的能力边界需要更明确：resolve 应找候选，canonicalize 可能只做规范化。

### 修改建议

- response 增加：

```text
summary:
  canonical: uart_top.clk
  exists: false | true | unknown
  verified_by: design | waveform | none
```

- docs 和 xout 明确：如果 canonicalize 不验证存在，应标 `status: normalized_only`。
- `DESIGN_NOT_LOADED` 和 `args.sig` 错误修复同 `signal.resolve`。

### Agent Review

独立 agent 认为 canonicalize 是否验证存在属于风险推断；建议后续补源码或额外实测确认。

## 17. `scope.roots`

### 调用覆盖

- MCP query 成功调用：`args:{}`
- MCP query schema 错误：`args.source:"bad"`
- raw_request 成功调用
- raw_request schema 错误：`args.source:"bad"`

### 能力与入口形态

`scope.roots` 发现当前 session 的 waveform/design root，通常是从 signal/clock path 错误恢复的第一步。MCP query 形态：

```json
{"session_id":"case_a","action":"scope.roots","args":{}}
```

可选：

```json
{"session_id":"case_a","action":"scope.roots","args":{"source":"auto"}}
```

### 失败返回评审

非法 `source` 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.source
allowed_values: ["auto","wave","design"]
schema_path: schemas/v1/actions/scope.roots.request.schema.json
correct_example.args.source: auto
```

清晰度评价：

- `allowed_values` 很有用，AI 可以直接修正。
- `correct_example` 仍是 native envelope，不是 MCP 壳。
- message 里有 `instance not found in required enum`，可读性一般但不阻碍恢复。

raw_request 同一错误仍由 `XVERIF_CLI_FAILED/stdout_tail` 包装。

### Handler 层错误评审

本 action 在只有 waveform、没有 design 的情况下不失败，而是在成功返回中给出 limitation：

```text
limitations:
  design roots unavailable: design not loaded
```

这比把缺 design 当错误更适合 debug。若用户显式 `source:"design"`，后续应验证是否仍成功但空结果，或返回更具体 limitation。

### 成功返回评审

成功 xout：

```text
summary:
  recommended: ai_complex_top
  source: auto
  roots: 1
  matched: 0
  wave: 1
  design: 0

roots:
  path            status     sources  wave            design
  ai_complex_top  wave_only  wave     ai_complex_top

limitations:
  design roots unavailable: design not loaded
```

对 debug 的价值：

- `recommended` 非常有价值，是 AI 修正 signal/clock path 的关键。
- `wave/design/matched` 能说明为什么路径只来自波形。
- limitations 清楚说明 design 未加载。

冗余/风险：

- `matched:0` 对初次用户不够自解释，可改成 `matched_wave_design_roots`。
- response schema 中 summary 字段叫 `recommended_root/root_count/wave_count/design_count`，xout 用 `recommended/roots/wave/design`，字段名有轻微不一致。

### 结论

- 这是恢复路径错误的核心 action，成功返回调试价值高。
- 错误返回可恢复，主要缺 MCP 壳示例。
- xout 字段名建议和 response schema 对齐。

### 修改建议

- MCP wrapper 增加 `mcp_correct_example`。
- xout summary 使用 schema 字段名或至少避免 `roots` 同时表示 count 和表名。
- 在 signal/clock not found 错误中主动推荐本 action。

### Agent Review

独立 agent 认可其作为恢复入口的价值；字段名与 schema 不一致需要补 schema 证据或降低语气。

## 18. `scope.list`

### 调用覆盖

- MCP query 成功调用：`path:"ai_complex_top", recursive:false, max_depth:1`
- MCP query schema 错误：误用旧字段 `depth`
- MCP query 空结果：`path:"no_such_scope"`
- raw_request 成功调用

### 能力与入口形态

`scope.list` 列出指定 scope 下的子 scope 和 signals。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "scope.list",
  "args": {"path":"ai_complex_top","recursive":false,"max_depth":1}
}
```

注意 schema 使用 `max_depth`，不接受 `depth`。

### 失败返回评审

误传 `depth` 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.depth
expected: no additional properties allowed
received_type: integer
schema_path: schemas/v1/actions/scope.list.request.schema.json
correct_example.args.path: ""
```

清晰度评价：

- 能指出 `depth` 不允许。
- 没有 `did_you_mean:"max_depth"`，但这是最需要的恢复信息。
- correct_example 只给 `path:""`，没有展示 `max_depth` 的正确写法。

`path:"no_such_scope"` 返回 ok 但空结果：

```text
summary:
  path: no_such_scope
  returned_signal_count: 0
  total_signal_count: 0
data:
  scopes: [empty]
  signals: [empty]
```

这不是错误，但对 AI 不够明确：无法区分“scope 不存在”和“scope 存在但为空”。

### 成功返回评审

成功 xout：

```text
summary:
  path: ai_complex_top
  recursive: false
  returned_signal_count: 23
  total_signal_count: 23
  truncated: false

signals:
  ai_complex_top.clk
  ai_complex_top.rst_n
  ai_complex_top.sig_a
  ...
```

对 debug 的价值：

- 直接列出可用 signal，是修正 `value.at` / `stream` / `event` 路径的关键。
- `truncated` 字段对大 scope 很重要。
- 默认 xout 非常适合人工和 AI 继续选路径。

不足：

- 空 path 结果需要 `path_exists` 或 `status:no_match`。
- schema/说明没有突出 `max_depth` 是正确字段，导致 AI 容易用 `depth`。
- 对大列表应给 `returned_scope_count` 与 `returned_signal_count` 分开；当前只有 signal count，scope count 隐含在表里。

### 结论

- 成功返回对 debug 非常有用。
- 常见错误 `depth` 应直接提示 `max_depth`。
- 空结果应区分不存在和空 scope。

### 修改建议

- 对 `args.depth` 错误增加：

```json
{"did_you_mean":"args.max_depth","mcp_correct_example":{"session_id":"case_a","action":"scope.list","args":{"path":"ai_complex_top","max_depth":1}}}
```

- 空结果增加 `summary.path_exists:false` 或 `status:"not_found"`。
- signal/clock not found 类错误的 `next_actions` 应包含 `scope.list`。

### Agent Review

独立 agent 认为 depth/max_depth 和空结果语义问题证据充分；建议补 scope count 输出证据。

## 15. `value.at`

### 调用覆盖

- MCP query 首次失败：`clock:"top.clk"` 不存在
- MCP query 成功重试：通过 `scope.roots/scope.list` 修正为 `ai_complex_top.clk`
- MCP query schema 错误：缺少 `args.clock`
- MCP query schema 错误：非法 `args.format`
- MCP query handler 错误：`signal:"ai_complex_top.no_such"`
- raw_request 成功调用：同一 session 下读取 `ai_complex_top.sig_a`
- raw_request schema 错误：缺少 `args.clock`

### 能力与入口形态

`value.at` 读取单个信号在指定时间、指定 clock 采样语义下的值。MCP query 形态：

```json
{
  "session_id": "case_a",
  "action": "value.at",
  "args": {
    "signal": "ai_complex_top.sig_a",
    "time": "10ns",
    "clock": "ai_complex_top.clk"
  }
}
```

### 重试记录

首次使用惯性示例 `top.clk/top.*` 失败：

```text
code: INVALID_REQUEST
message: Clock signal not found: top.clk
invalid_arg: args.clock
expected: existing clock signal path
correct_example.args.clock: top.clk
```

随后调用 `scope.roots` 得到 root `ai_complex_top`，再用 `scope.list(path:"ai_complex_top")` 找到 `ai_complex_top.clk/sig_a/sig_b`，成功重试。

评价：失败提示能指出 clock 不存在，但 `correct_example` 仍回显坏 clock，且没有建议 `scope.roots` / `scope.list`。这是 AI 很容易卡住的点。

### 失败返回评审

缺少 `clock` 时：

```text
code: INVALID_REQUEST
invalid_arg: args.clock
expected: type "string"
received_type: missing
schema_path: schemas/v1/actions/value.at.request.schema.json
correct_example.args: {signal:"top.u.ready", clock:"top.u.clk", time:"100ns", format:"hex"}
```

非法 `format` 时：

```text
code: INVALID_REQUEST
invalid_arg: args.format
allowed_values: h/hex/b/bin/binary/d/dec/decimal/array_indexed/json/tsv/csv/u64bin
```

这些 schema 错误结构完整，能自动恢复；缺点是示例仍是占位路径，不能直接在当前 session 执行。

不存在 signal 时：

```text
code: SIGNAL_NOT_FOUND
message: failed to read value: ai_complex_top.no_such
recoverable: true
```

handler 错误不足：

- 缺 `invalid_arg:"args.signal"`
- 缺 `suggestion:"call scope.list or signal.resolve"`
- 缺 near-match 候选
- 缺 `correct_example`

### 成功返回评审

成功 xout：

```text
target:
  signal: ai_complex_top.sig_a
  time: 10ns
  clock: ai_complex_top.clk
  edge: negedge
  clock_edge_hit: true
  target_edge_hit: true

summary:
  status: ok
  signal                before  middle  after
  ai_complex_top.sig_a  'h00    'h00    'h00
```

对 debug 的价值：

- `target` 明确 signal/time/clock/edge，能复核采样语义。
- `before/middle/after` 对 clock-edge 采样 race 很有价值。
- `clock_edge_hit/target_edge_hit` 能帮助判断时间是否对齐。

冗余/风险：

- `before/middle/after` 的语义对初次用户可能不够自解释；建议在 xout 字段名或 docs 中固定说明。
- 如果 `clock_edge_hit:false`，应给下一/上一 clock edge 的建议时间。

### 结论

- 成功返回非常适合 debug。
- 高频错误 `clock/signal path 不存在` 的 handler 提示不够可恢复，且 `correct_example` 会回显坏路径。
- 参数复杂度中等，主要难点不是字段数量，而是真实 signal/clock 路径发现。

### 修改建议

- `Clock signal not found` 增加：

```json
{
  "invalid_arg": "args.clock",
  "suggestion": "call scope.roots then scope.list to find a clock signal",
  "mcp_correct_example": {
    "session_id": "case_a",
    "action": "value.at",
    "args": {"signal":"<existing_signal>","clock":"<existing_clock>","time":"100ns"}
  }
}
```

- `SIGNAL_NOT_FOUND` 增加 `invalid_arg/near_matches/next_action`。
- handler 生成的 `correct_example` 不得回显不存在路径。

### Agent Review

独立 agent 认为 clock/signal 错误和采样语义评价证据充分；建议补非法 format 的可选值分组问题。

## 16. `value.batch_at`

### 调用覆盖

- MCP query 首次失败：`clock:"top.clk"` 不存在
- MCP query 成功重试：`signals:["ai_complex_top.sig_a","ai_complex_top.sig_b"]`
- MCP query schema 错误：缺少 `args.clock`
- MCP query schema 错误：非法 `args.format`
- MCP query schema 错误：`signals` 为 string
- MCP query handler/contract 错误：`signals` 为 alias object
- MCP query partial data：一个 signal 不存在时 action 仍成功，表内返回 `signal_not_found`
- raw_request 成功调用
- raw_request schema 错误：缺少 `args.clock`

### 能力与入口形态

`value.batch_at` 在同一个时间点批量读取多个信号。MCP query 推荐形态：

```json
{
  "session_id": "case_a",
  "action": "value.batch_at",
  "args": {
    "signals": ["ai_complex_top.sig_a", "ai_complex_top.sig_b"],
    "time": "10ns",
    "clock": "ai_complex_top.clk"
  }
}
```

### 重试记录

首次使用 `top.clk/top.*` 失败，错误和 `value.at` 相同：

```text
code: INVALID_REQUEST
message: Clock signal not found: top.clk
invalid_arg: args.clock
correct_example.args.clock: top.clk
```

通过 `scope.roots/scope.list` 修正到 `ai_complex_top.clk` 后成功。

### 失败返回评审

缺少 `clock` 和非法 `format` 的 schema 错误结构完整，包含 `invalid_arg/schema_path/allowed_values/correct_example`。

`signals` 传 string 时，schema 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.signals
expected: oneOf schema
received_type: string
correct_example.args.signals: ["top.u.valid","top.u.ready"]
```

问题：

- `expected:"oneOf schema"` 对 AI 不够直接，应该说 `array of signal paths or alias-to-path object`。
- 示例仍是占位路径。

更严重的问题是 schema/runtime 不一致：schema 允许 `signals` 是 object：

```json
{"signals":{"a":"ai_complex_top.sig_a","b":"ai_complex_top.sig_b"}}
```

但 handler 返回：

```text
code: MISSING_FIELD
message: args.signals[] and args.time are required
recoverable: true
```

该错误没有 `invalid_arg/schema_path/correct_example`，而且 message 暗示只接受 array。这里应收敛 schema 或修 runtime。

### 成功返回评审

成功 xout：

```text
target:
  time: 10ns
  signal_count: 2

values:
  signal                before  middle  after
  ai_complex_top.sig_a  'h00    'h00    'h00
  ai_complex_top.sig_b  'h00    'h00    'h00
```

对 debug 的价值：

- 表格格式很适合多信号对比。
- `before/middle/after` 与 `value.at` 一致，对采样边界 debug 有价值。

partial signal not found 时：

```text
values:
  ai_complex_top.sig_a    'h00
  ai_complex_top.no_such  signal_not_found
```

这是批量查询的实用设计：不因为一个信号失败而丢掉其它信号结果。

不足：

- summary 没有 `missing_signal_count` 或 `ok_signal_count`，AI 需要扫表才知道有部分失败。
- target 不显示 `clock/edge`，不如 `value.at` 完整。
- alias object 若未来支持，返回表应显示 alias 和 path；若不支持，应从 schema 移除。

### 结论

- 成功返回对 debug 很有用，尤其适合多信号同一时刻检查。
- 参数复杂度中等，核心风险是 `clock` 必填和 `signals` 的 array/object 合同不一致。
- partial failure 设计好，但 summary 需要计数。

### 修改建议

- 二选一修复 `signals` object：
  - 支持 alias object，并在返回中展示 `alias/path/value`。
  - 或从 schema 中移除 object，只保留 array。
- 对 partial signal not found 增加：

```text
summary:
  signal_count: 2
  ok_signal_count: 1
  missing_signal_count: 1
```

- `target` 增加 `clock/edge`。
- `oneOf schema` 错误改成人话，并追加 MCP 示例。

### Agent Review

独立 agent 认为 schema/runtime 冲突证据很强，应列为高优先级 contract 修复。

## 10. `cursor.set`

### 调用覆盖

- MCP query 成功调用：`args.name/time/time_unit`
- MCP query schema 错误：缺少 `args.time`
- MCP query handler 错误：`args.time:"not_a_time"`
- raw_request 成功调用：同一 session 下设置 `review_t1_raw`
- raw_request schema 错误：缺少 `args.time`

### 能力与入口形态

`cursor.set` 保存命名时间游标，后续 action 可通过游标名复用时间点。MCP query 推荐形态：

```json
{"session_id":"case_a","action":"cursor.set","args":{"name":"mark_a","time":"100ns"}}
```

raw/native envelope 形态：

```json
{"api_version":"xdebug.v1","action":"cursor.set","target":{"session_id":"case_a"},"args":{"name":"mark_a","time":"100ns"}}
```

### 失败返回评审

缺少 `time` 时，MCP query 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.time
expected: type "string"
received_type: missing
schema_path: schemas/v1/actions/cursor.set.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"cursor.set","target":{"session_id":"case_a"},"args":{"name":"mark_a","time":"100ns"}}
```

这个 schema 层错误基本可恢复，但 `correct_example` 仍是 native envelope，不是 MCP 壳。

`time:"not_a_time"` 到 handler 层后返回：

```text
code: ACTION_FAILED
message: Invalid time 'not_a_time'
invalid_arg: args.time
expected: time string such as 10ns, 100ps, or max for end
correct_example.args.time: "not_a_time"
```

这是本 action 的主要问题：handler 层 `correct_example` 回显了错误输入，而不是可执行示例。AI 看到 `correct_example` 后可能继续发送同样的坏值。

raw_request 对缺字段错误仍包装成 `XVERIF_CLI_FAILED`，backend 细节在 `stdout_tail` 中。

### 成功返回评审

成功 xout：

```text
cursor:
  name: review_t1
  time: 10ns
  origin: manual
  created_at: ...
  updated_at: ...

resolved_time:
  source: 10ns
  time: 10ns
  status: set
```

对 debug 的价值：

- `name/time/resolved_time/status` 足够确认游标已保存。
- 输出紧凑，没有明显冗余。

风险：

- `created_at/updated_at` 对 debug 价值较低，compact 模式可考虑隐藏。
- 如果时间单位被归一化，建议同时显示 canonical raw tick 或原始 time unit。

### 结论

- 参数复杂度低，AI 易用性整体好。
- schema 错误提示较好；handler 时间解析错误的 `correct_example` 明显有 bug。

### 修改建议

- handler 层时间解析失败时，`correct_example` 必须替换为有效值，例如：

```json
{"session_id":"case_a","action":"cursor.set","args":{"name":"mark_a","time":"100ns"}}
```

- MCP wrapper 追加 `mcp_correct_example`，native 示例保留为 `native_correct_example`。

### Agent Review

独立 agent 认为本节证据非常扎实，坏 time 被回显到 correct_example 是明确 bug 级问题。

## 11. `cursor.list`

### 调用覆盖

- MCP query 成功调用：`args:{}`
- MCP query schema 错误：`args.filter`
- raw_request schema 错误：`args.filter`

### 能力与入口形态

`cursor.list` 列出当前 session 内保存的游标。MCP query 形态：

```json
{"session_id":"case_a","action":"cursor.list","args":{}}
```

schema 只允许可选 `time_unit`，不支持 `filter`。

### 失败返回评审

传入 `args.filter` 时，MCP query 返回：

```text
code: INVALID_REQUEST
invalid_arg: args.filter
expected: no additional properties allowed
received_type: string
schema_path: schemas/v1/actions/cursor.list.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"cursor.list","target":{"session_id":"case_a"},"args":{}}
```

清晰度评价：

- 能明确指出 `filter` 不被允许。
- message 含 `false-schema` 这类内部术语，建议简化。
- `correct_example` 仍是 native envelope，不是 MCP query 壳。

raw_request 同一错误被包装成 `XVERIF_CLI_FAILED`，可恢复字段只在 `stdout_tail` 里。

### Handler 层错误评审

本 action 没有名字/路径等业务参数，本轮没有可构造的 handler 层错误。真正的问题是缺少筛选能力时 AI 可能自然猜 `filter`，schema 能拒绝但没有告诉用户如何替代，例如“先 list 再在本地过滤”。

### 成功返回评审

成功 xout：

```text
cursors:
  name  time  note  origin  clock  created_at  updated_at
  ...
  active_cursor: review_t1_raw
  cursor_count: 2
```

对 debug 的价值：

- `name/time/active_cursor/cursor_count` 有用。
- `origin/clock` 在游标来自自动流程或带 clock 时有价值。

冗余/风险：

- `created_at/updated_at` 默认 compact 中价值较低。
- `active_cursor` 和 `cursor_count` 混在表格后方，机器解析和人眼扫描都不够稳定；建议放入单独 `summary`。

### 结论

- 参数简单，但 AI 容易自然尝试 `filter`。
- 成功返回可用，建议把 summary 与 rows 分开。

### 修改建议

- 对额外字段 `filter` 的错误追加 `suggestion:"cursor.list does not filter; call cursor.list then filter locally"`。
- xout 改为顶部 `summary.cursor_count/active_cursor`，下面只放 rows。

### Agent Review

独立 agent 认为 filter 被拒和表格混入 summary 有证据；建议补空列表场景覆盖。

## 12. `cursor.get`

### 调用覆盖

- MCP query 成功调用：`args.name:"review_t1"`
- MCP query schema 错误：缺少 `args.name`
- MCP query handler 错误：不存在游标 `no_such_cursor`
- raw_request 成功调用：读取 `review_t1_raw`
- raw_request handler 错误：不存在游标

### 能力与入口形态

`cursor.get` 读取指定游标。MCP query 形态：

```json
{"session_id":"case_a","action":"cursor.get","args":{"name":"mark_a"}}
```

### 失败返回评审

缺少 `name` 时，MCP query 可返回两种不同形态：

- 传 `args:{}` 时，后端看到的是缺少整个 `args` 对象：

```text
invalid_arg: args
expected: type "object"
received_type: missing
```

- 传 `args:{"time_unit":"ns"}` 时，后端才指出缺少 `args.name`：

```text
invalid_arg: args.name
expected: type "string"
received_type: missing
```

这暴露了 MCP wrapper 的一个易迷惑点：空 dict 可能没有被序列化进 native envelope，导致错误位置从 `args.name` 漂移成 `args`。

不存在游标时返回：

```text
code: ACTION_FAILED
message: CURSOR_NOT_FOUND: Cursor 'no_such_cursor' does not exist
recoverable: true
```

该 handler 错误能说明问题，但缺少：

- `invalid_arg:"args.name"`
- `available_values` 或 `available_cursors`
- `correct_example`
- `next_action:"cursor.list"`

raw_request handler 错误同样被 `XVERIF_CLI_FAILED/stdout_tail` 包装。

### 成功返回评审

成功 xout：

```text
cursor:
  name: review_t1
  time: 10ns
  origin: manual
  created_at: ...
  updated_at: ...
```

对 debug 的价值：

- `name/time/origin` 足够。
- 输出简短，适合默认 xout。

冗余/风险：

- `created_at/updated_at` 对大多数 debug 不关键。
- 如果后续 action 可直接引用 active cursor，应在返回中提示是否当前 active。

### 结论

- 成功返回可用。
- handler 层不存在错误不够可恢复，应引导 `cursor.list`。
- MCP 空 args 的序列化行为会让 required 子字段错误变成顶层 args 缺失，影响 AI 修复。

### 修改建议

- `CURSOR_NOT_FOUND` 增加：

```json
{
  "invalid_arg": "args.name",
  "available_values": ["review_t1_raw"],
  "suggestion": "call cursor.list to inspect saved cursors",
  "mcp_correct_example": {"session_id":"case_a","action":"cursor.get","args":{"name":"review_t1_raw"}}
}
```

- MCP query 保留空 `args:{}`，让后端能报告 `args.name` 缺失。

### Agent Review

独立 agent 认可空 args 定位问题；建议说明 raw wrapper 弱化结构化错误不是 cursor.get 独有。

## 13. `cursor.use`

### 调用覆盖

- MCP query 成功调用：`args.name:"review_t1"`
- handler 错误用 `cursor.get/delete` 的同类不存在游标路径代表，同一 CursorManager 错误族。

### 能力与入口形态

`cursor.use` 将指定游标设为 active cursor。MCP query 形态：

```json
{"session_id":"case_a","action":"cursor.use","args":{"name":"mark_a"}}
```

### 失败返回评审

schema 与 handler 错误形态和 `cursor.get` 一致：

- 缺 `name` 属于 schema 错误，应指向 `args.name`。
- 不存在游标属于 handler 错误，当前同族错误只有 `CURSOR_NOT_FOUND` message 和 `recoverable:true`。

风险：

- active cursor 是隐式状态，错误提示如果不列 available cursor，AI 很难判断是拼写错误、session 错误，还是 cursor 尚未创建。
- 成功调用会改变后续 action 的上下文，默认 xout 应明确 `previous_active_cursor`，但当前只显示新 active。

### 成功返回评审

成功 xout：

```text
data:
  status: active
  active_cursor: review_t1

cursor:
  name: review_t1
  time: 10ns
  origin: manual
```

对 debug 的价值：

- `status/active_cursor/cursor.time` 很有用，能确认状态切换结果。
- 输出紧凑。

不足：

- 缺 `previous_active_cursor`，对排查“为什么后续窗口变了”不够友好。
- 没有 `session_id`，多个 session 并行时不容易核对状态归属。

### 结论

- 参数简单，但由于它改变隐式状态，成功返回应更强调状态变更。

### 修改建议

- 成功返回增加 `previous_active_cursor` 和 `session_id`。
- `CURSOR_NOT_FOUND` 同 `cursor.get`，增加 `available_values` 和 `cursor.list` 建议。

### Agent Review

独立 agent 认为成功路径结论合理，但 handler 错误主要按同族推断，建议显式标为待补覆盖。

## 14. `cursor.delete`

### 调用覆盖

- MCP query 成功调用：删除 `review_t1`
- MCP query handler 错误：删除不存在游标 `no_such_cursor`

### 能力与入口形态

`cursor.delete` 删除指定游标。MCP query 形态：

```json
{"session_id":"case_a","action":"cursor.delete","args":{"name":"mark_a"}}
```

### 失败返回评审

不存在游标时返回：

```text
code: ACTION_FAILED
message: CURSOR_NOT_FOUND: Cursor 'no_such_cursor' does not exist
recoverable: true
```

清晰度评价：

- message 能读懂，但没有结构化恢复字段。
- 对 delete 来说，缺少 `already_absent:true` 或幂等性说明；用户不知道这是否可忽略。
- 没有列出 available cursors，也没有建议 `cursor.list`。

### 成功返回评审

成功 xout：

```text
data:
  status: deleted
  name: review_t1
```

对 debug 的价值：

- 足够简洁，能确认删除目标。

不足：

- 如果删除的是 active cursor，应返回 `active_cursor_cleared:true` 或新的 active cursor。
- 当前返回没有 session_id，跨 session 并行时可读性较弱。

### 结论

- 成功返回非常简洁，可用。
- handler 错误需要更结构化，尤其是 delete 的幂等语义需要明确。

### 修改建议

- `CURSOR_NOT_FOUND` 增加 `invalid_arg:"args.name"`、`available_values`、`suggestion:"call cursor.list"`。
- 若 delete 不存在被视为失败，增加 `idempotent:false`；若可改为幂等，返回 `status:"absent"` 更适合自动化 cleanup。
- 成功删除 active cursor 时报告 active 状态变化。

### Agent Review

独立 agent 认可删除成功/失败评价；active cursor 状态变化建议应作为补充测试，不作为已证实缺陷。

## 9. `session.gc`

### 调用覆盖

- MCP query 成功调用：`xverif_debug_query(session_id="mcp_action_review_main_20260709_b", action="session.gc", args={})`
- MCP query 输入错误：`args.max_age_s`
- raw_request 成功调用：`{"api_version":"xdebug.v1","action":"session.gc","args":{}}`
- raw_request 输入错误：`args.max_age_s`

### 能力与入口形态

`session.gc` 用于清理 xdebug native session registry 中已经不健康或可回收的 session。当前 schema 表示该 action 不接受 action-specific args：

```json
{"session_id":"case_a","action":"session.gc","args":{}}
```

raw/native envelope 形态为：

```json
{"api_version":"xdebug.v1","action":"session.gc","args":{}}
```

### 失败返回评审

对 `args.max_age_s` 的 MCP query 返回结构化错误：

```text
code: INVALID_REQUEST
message: invalid parameter args.max_age_s ... expected no additional properties allowed
invalid_arg: args.max_age_s
expected: no additional properties allowed
received_type: integer
schema_path: schemas/v1/actions/session.gc.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"session.gc","args":{}}
```

清晰度评价：

- `invalid_arg/expected/received_type/schema_path` 齐全，能直接定位多余字段。
- `correct_example` 是 native envelope，不是 MCP query 壳。对 MCP 用户还不够直接。
- message 太长，包含 JSON schema 内部术语 `false-schema`，对 AI 和用户都没有额外帮助。

raw_request 对同一错误返回：

```text
code: XVERIF_CLI_FAILED
message: xdebug exit 1
stdout_tail: @xdebug.error.v1 ... invalid_arg: args.max_age_s ...
```

raw 入口的问题仍是 backend 结构化错误被包在 `stdout_tail` 中，AI 需要二次解析文本。

### Handler 层错误评审

本 action 当前没有可控的 handler 级业务参数；有效调用只做 registry 扫描和 cleanup。本轮没有构造出独立于 schema 的业务参数错误。

但它是资源清理类 action，通过 MCP query 执行时作用域是 xdebug native registry，而不是 MCP wrapper session manager。这个语义容易混淆，应在返回中明确 `scope:native_session_registry`。

### 成功返回评审

成功 xout 返回：

```text
summary:
  status: completed
  before_count: 1
  kept_count: 1
  removed_count: 0

before:
  id/session_id/mode/fsdb/socket_path/transport/file_dir/server_host/server_pid/...

kept:
  session_id/mode
removed: [empty]
```

对 debug 的价值：

- `before_count/kept_count/removed_count` 对确认 cleanup 效果有用。
- `kept/removed` 表格能说明哪些 session 被保留或移除。
- 如果移除失败，之前实测 `removed` 表格里的 `reason/kill_ok` 对排障有价值。

冗余/风险：

- compact xout 暴露大量底层路径和文件系统字段，例如 `socket_path/file_dir/fsdb_mtime/fsdb_dev/fsdb_inode`。这些对普通 debug 不必要，且在用户可见回答中不应直接传播。
- `before` 表格太宽，核心 cleanup 结论被稀释。
- 没有显式说明这是 native registry，不是 MCP manager。

### 结论

- 成功返回：有用，但 compact 默认过宽；建议压缩到 counts、kept/removed session_id、reason、kill result。
- 失败返回：schema 层已经较好，但 `correct_example` 应同时给 MCP 壳，message 应减少 schema 内部术语。
- 入口风险：这是 lifecycle/cleanup action，通过 MCP query 使用时容易和 MCP session manager 混淆。

### 修改建议

- MCP wrapper 为 schema 错误追加：

```json
{"session_id":"case_a","action":"session.gc","args":{}}
```

作为 `mcp_correct_example`。

- `session.gc` 成功 xout 增加：

```text
scope: native_xdebug_registry
```

- compact 默认隐藏 `socket_path/file_dir/dev/inode/mtime`，只在 debug verbosity 或 JSON full 模式展示。

### Agent Review

独立 agent 认可 registry scope 和 raw wrapper 问题；建议对 max_age_s 是否旧字段补证据，减少动机推断。

## 8. `session.kill`

### MCP 调用方式

- query 输入错误：`xverif_debug_query(session_id="session_kill_query_review_20260709", action="session.kill", args={"force":true})`
- query 成功调用：`xverif_debug_query(session_id="session_kill_query_review_20260709", action="session.kill", args={})`
- raw handler 错误：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"session.kill","target":{"session_id":"no_such_kill_review_20260709"},"args":{}})`

### 失败返回评审

输入/schema 错误 `args.force`：

```text
code: INVALID_REQUEST
invalid_arg: args.force
expected: no additional properties allowed
received_type: boolean
schema_path: schemas/v1/actions/session.kill.request.schema.json
correct_example:
  target.session_id: case_a
  args.session_id: case_a
```

评价：

- `invalid_arg/expected/received_type` 清晰。
- `correct_example` 有明显问题：同时出现 `target.session_id` 和 `args.session_id`。当前合同应避免 `args.session_id`，否则会误导 AI 把 session 选择写入 args。
- 对 MCP query 用户也缺少 MCP 壳示例。

handler 层错误：raw kill 不存在 session：

```text
code: XVERIF_CLI_FAILED
stdout_tail:
  code: SESSION_NOT_FOUND
  message: session not found: no_such_kill_review_20260709
```

评价：

- backend message 清楚。
- raw wrapper 仍隐藏结构化 backend error。

### 成功返回评审

query 成功 `session.kill` 返回：

```text
summary.session_id/mode/removed
session socket_path/transport/file_dir/server_pid/resource metadata
backends action: session.kill
summary.killed: true
```

对 debug 的价值：

- 对 native session 强制清理有价值，能看到 removed/killed 和底层 pid/path。
- 和 `session.close` 类似，适合 native 残留清理。

冗余/风险：

- 对 MCP flow 太危险：通过 `xverif_debug_query(action="session.kill")` 会 kill 当前绑定 native backend session。
- MCP wrapper session 仍可能需要再调用 `xverif_debug_session_close` 清理 manager 记录。
- 成功输出没有 warning 说明 MCP manager 是否同步。

### 结论

- 成功返回：native 清理证据充分，但 compact 输出偏底层。
- 失败返回：schema 错误基本清晰，但 `correct_example` 与推荐合同冲突；handler 错误受 raw wrapper 包装影响。
- 强建议：MCP query 层默认禁止 `session.kill`，要求用户使用 MCP 专用 close 或显式 raw/native opt-in。

### Agent Review

独立 agent 认为 correct_example 混用 target/args session_id 的证据明确；建议把禁止 query 调 kill 表述为设计建议。

## 7. `session.close`

### MCP 调用方式

- MCP 专用成功调用：先 `xverif_debug_session_open(name="session_close_review_20260709", fsdb=...)`，再 `xverif_debug_session_close(name="session_close_review_20260709")`
- MCP 专用 handler 错误：`xverif_debug_session_close(name="no_such_close_review_20260709")`
- query 对照：`xverif_debug_query(session_id="session_open_review_20260709", action="session.close", args={})`
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"session.close","target":{"session_id":"query_close_native_review_20260709"}})`

### 失败返回评审

MCP 专用 close 对不存在 session 返回：

```text
code: SESSION_NOT_FOUND
message: session not found: no_such_close_review_20260709
```

评价：

- 清晰，能直接判断 session 名或 id 不存在。
- 缺少建议：先 `xverif_debug_session_list`，或确认 MCP/native session 边界。
- 这是 handler 层错误，不是 schema 错误；MCP tool schema 层错误本轮未通过工具调用制造，因为工具参数缺失会在 MCP 框架侧拦截。

### 成功返回评审

MCP 专用 close 成功返回：

```text
ok: true
closed.alias/session_id/state/mode/backend/fsdb/pid
cleanup.backend_close: ok
cleanup.stdio_quit: ok
cleanup.terminate: ok
previous_state: alive
```

对 debug 的价值：

- 很有用，清楚展示 backend close、stdio quit、terminate 三步 cleanup。
- `previous_state` 能确认是否关闭了 live session。
- 信息不冗余，适合 MCP session 生命周期。

raw/native close 成功返回：

```text
summary.session_id/mode/removed
session socket_path/transport/file_dir/server_pid/mtime/inode
backends action: session.kill
summary.killed: true
```

对 debug 的价值：

- 对清理 native session 残留很有用。
- 对普通 MCP flow 偏底层，信息较多但可以接受。

### 入口风险

`xverif_debug_query(session_id="session_open_review_20260709", action="session.close", args={})` 实测会关闭当前 query 绑定的 native backend session，即 `session_open_review_20260709`，而不是关闭某个显式传入的 native target。

风险：

- 这会破坏 MCP wrapper 认为仍存在的 session。
- AI 很容易误用 `debug_query(action="session.close")` 代替 `xverif_debug_session_close`。
- 成功返回显示 native `session.close`，但没有提醒 MCP manager 映射是否同步更新。

建议：

- MCP `xverif_debug_query` 默认拒绝或强 warning `session.close` / `session.kill` / `session.open` 等 lifecycle action。
- MCP close 应只推荐 `xverif_debug_session_close`。
- 如果允许 native lifecycle action，必须要求显式 opt-in，例如 `allow_native_session_action:true`，并返回 MCP manager 状态同步说明。

### 结论

- 成功返回：MCP 专用 close 返回清晰、对 cleanup debug 很有用；raw close 适合 native 残留清理。
- 失败返回：`SESSION_NOT_FOUND` 清楚但可增加恢复建议。
- 最大问题是入口边界：通过 `xverif_debug_query` 调 native close 容易误伤当前 MCP backend session。

### Agent Review

独立 agent 认可 query 调 native close 的风险；建议补实测 MCP manager 后续状态是否失配。

## 6. `session.doctor`

### MCP 调用方式

- query 成功调用：`xverif_debug_query(session_id="session_open_review_20260709", action="session.doctor", args={})`
- query 输入错误：`args={"verbose":true}`
- raw handler 错误：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"session.doctor","target":{"session_id":"no_such_native_session_20260709"},"args":{}})`

### 失败返回评审

输入/schema 错误 `args.verbose`：

```text
code: INVALID_REQUEST
invalid_arg: args.verbose
expected: no additional properties allowed
received_type: boolean
schema_path: schemas/v1/actions/session.doctor.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"session.doctor","target":{"session_id":"case_a"},"args":{}}
```

评价：

- query 入口清晰可恢复。
- `correct_example` 仍是 native envelope，不是 MCP query 壳。

handler 层错误 `target.session_id` 不存在（raw/native）：

```text
code: XVERIF_CLI_FAILED
stdout_tail:
  action: session.doctor
  code: SESSION_NOT_FOUND
  message: session not found: no_such_native_session_20260709
  recoverable: true
```

评价：

- backend message 清楚，但 raw wrapper 仍把结构化错误藏在 `stdout_tail`。
- 缺少建议：先 `session.list` 或检查 MCP/native session 边界。

### 成功返回评审

成功 xout 返回包含：

```text
summary.session_id/mode/healthy
health.api_version/request_id/ok/action
tool.name/version
session.id/session_id/fsdb/fsdb_file/pid/transport/socket_path/file_dir/port/server_host/created_at/last_active/mtime/size/dev/inode
summary.id/session_id/healthy/status/message
health.id/session_id/healthy/status/message
```

对 debug 的价值：

- 对定位 session 是否 healthy 很有用。
- `pid/transport/socket_path/file_dir/server_host` 对 transport/进程问题有价值。
- `fsdb_file/mtime/size/inode` 对确认资源是否变化有价值。

冗余/风险：

- 输出明显重复：顶部 `summary`、后面的 `summary`、两个 `health` 段重复表达 healthy/status/message。
- 对普通用户过长，底层 inode/dev/socket/file_dir 信息可能分散注意力。
- 建议 compact xout 只保留一份 summary/health，底层 session 元数据放到 `debug/full` verbosity。

### 结论

- 成功返回：排障价值高，但 compact 输出冗余明显。
- 失败返回：query schema 错误清晰；raw handler 错误受 wrapper 包装影响，缺少恢复建议。

### Agent Review

独立 agent 认为成功返回冗余评价合理；建议标注 query handler 不存在 session 的失败路径尚未覆盖。

## 5. `session.list`

### MCP 调用方式

- MCP 专用调用：`xverif_debug_session_list(include_native=true)`
- query 成功调用：`xverif_debug_query(session_id="session_open_review_20260709", action="session.list", args={})`
- query 输入错误：`args={"filter":"alive"}`
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"session.list","args":{}})`

### 失败返回评审

输入/schema 错误 `args.filter`：

```text
code: INVALID_REQUEST
invalid_arg: args.filter
expected: no additional properties allowed
received_type: string
schema_path: schemas/v1/actions/session.list.request.schema.json
correct_example: {"api_version":"xdebug.v1","action":"session.list","target":{"session_id":"case_a"},"args":{}}
```

评价：

- `xverif_debug_query` 入口返回结构化字段，清晰可恢复。
- `correct_example` 是 native envelope，并含 `target.session_id`；对 MCP query 用户不够直接，最好同时提供 MCP 形态示例。
- `session.list` 基本无 handler 层语义错误；它是状态枚举 action。

### 成功返回评审

MCP 专用 `xverif_debug_session_list(include_native=true)` 返回：

```text
ok: true
sessions:
  alias/session_id/state/mode/backend/fsdb/pid
```

对 debug 的价值：

- 适合 MCP session manager 视角，能看到当前 MCP 托管 session。
- 信息紧凑，没有暴露 socket/file_dir，适合普通 MCP 用户。

native/query `session.list` 返回：

```text
summary.session_count
summary.expired_removed_count
sessions:
  id/session_id/mode/fsdb/socket_path/transport/file_dir/server_host/server_pid/created_at/last_active/fsdb_mtime/fsdb_size/...
```

本轮实际看到 native list 包含历史残留 session：`s3`、`cal`、`bad_param_review_probe`、`session_open_review_20260709`。

对 debug 的价值：

- 对排查 xdebug native session 残留、transport、socket/file_dir 很有用。
- 能暴露 MCP 专用 list 看不到的 native session，适合清理和诊断。

冗余/风险：

- 对普通 MCP flow 信息偏多，尤其 socket_path/file_dir/dev/inode 容易让 AI 分心。
- MCP 专用 list 与 native `session.list` 的范围不同，名称相似但语义不同；用户容易混淆。

### 结论

- 成功返回：MCP 专用 list 简洁；native list 对底层排障有价值但冗余。
- 失败返回：schema 错误清晰，但 `correct_example` 应补 MCP query 形态。
- 边界建议：tool help/skill 应明确 `xverif_debug_session_list` 列 MCP manager session，`session.list` 列 xdebug native session registry。

### Agent Review

独立 agent 认可 MCP manager list 与 native registry list 不同的核心发现；建议补充 include_native=true 的边界证据。

## 4. `session.open`

### MCP 调用方式

- MCP 专用成功调用：`xverif_debug_session_open(name="session_open_review_20260709", fsdb="<fixture>/waves.fsdb")`
- MCP 专用输入错误：`name:"1bad_name"`
- MCP 专用 handler/资源错误：`fsdb:".../no_such.fsdb"`
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"session.open","target":{"fsdb":".../waves.fsdb"},"args":{"name":"session_open_raw_review_20260709"}})`
- raw 输入错误：`args.name:"1bad_name"`
- raw handler/资源错误：`target.fsdb:".../no_such.fsdb"`
- query 对照：`xverif_debug_query(session_id="session_open_review_20260709", action="session.open", args={"name":"nested_open_20260709"})`

### 失败返回评审

输入参数错误 `name:"1bad_name"`：

```text
code: INVALID_SESSION_NAME
message: session name must start with an ASCII letter and contain only ASCII letters, digits, and underscores, with maximum length 64
```

评价：

- 人能直接理解命名规则。
- 缺少 `invalid_arg:"name"` 或 `invalid_arg:"args.name"`，也没有 `correct_example`。
- MCP 专用 tool 和 raw/native action 都有同样问题；raw_request 还会包一层 `XVERIF_CLI_FAILED`。

handler/资源错误 `fsdb` 不存在：

```text
code: INVALID_REQUEST
message: Usage: open [-dbdir <simv.daidir>] [-fsdb <waves.fsdb>] ...
recoverable: true
```

评价：

- 这个返回不清晰：没有明确说哪个 path 不存在，也没有 `invalid_arg:"fsdb"` / `target.fsdb`。
- usage 文本更像 CLI 帮助，不像可恢复的 action error。
- 对 AI 来说不可直接修复，只能猜测 fsdb/daidir 路径问题。

同名 session 重开：

```text
code: SESSION_ID_EXISTS
message: session id already exists: session_open_review_20260709
```

评价：

- 足够清晰，能知道换名或关闭旧 session。
- 可改进：增加 `suggestion:"use xverif_debug_session_close or choose a new name"`。

### 成功返回评审

MCP 专用 `xverif_debug_session_open` 成功返回：

```text
ok: true
session.alias
session.session_id
session.state: alive
session.mode: direct
session.backend: xdebug
session.fsdb
session.pid
```

对 debug 的价值：

- 非常有用，直接给出后续 `xverif_debug_query.session_id`。
- `state/mode/backend/fsdb/pid` 对排障有价值。
- 信息不冗余，适合作为 MCP session lifecycle 的成功响应。

raw `session.open` 成功返回：

```text
summary.session_id
summary.mode
session.id/session_id/mode/fsdb/socket_path/transport/file_dir/server_host
```

对 debug 的价值：

- 对 native session/transport 排障有价值。
- 对普通 MCP 用户偏冗余，暴露 socket/file_dir 等底层细节。

query 对照 `xverif_debug_query(action="session.open")`：

- 可以在已有 MCP session 内打开一个 native backend session。
- 返回 native `session.open` xout，而不是 MCP session manager 的 session 对象。

风险：

- 这会混淆 MCP 托管 session 和 xdebug native session 生命周期。
- AI 可能以为 `xverif_debug_query(action="session.open")` 是推荐 MCP open 方式；实际推荐应是 `xverif_debug_session_open`。

### 结论

- 成功返回：MCP 专用 tool 清晰有用；raw/native 返回适合底层 transport 排障但对普通 MCP flow 冗余。
- 失败返回：命名错误可读但缺少结构化字段；fsdb/daidir 资源错误不清晰，只给 usage 是明显问题。
- 入口边界：`session.open` 不应作为普通 `xverif_debug_query` 推荐 action；MCP skill 和 tool help 应强调用专用 session tool。

### Agent Review

独立 agent 认为资源与 native/query 生命周期混淆的判断合理；建议补充 MCP tool 参数与 native envelope 参数的 invalid_arg 路径差异。

## 3. `batch`

### MCP 调用方式

- query 成功调用：`xverif_debug_query(session_id="session_open_review_20260709", action="batch", args={"requests":[...]})`
- query 失败调用：`args.requests[]` 中第一个 child request 失败。
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"batch","args":{"requests":[...]}})`
- raw 失败调用 1：`args.requests` 传字符串。
- raw 失败调用 2：`args.requests[]` 中第一个 child request 失败。
- schema 查询：`xverif_debug_get_schema(action="batch", kind="request")`

### 失败返回评审

`args.requests:"not_array"` 的 backend 错误信息清楚，但被 raw_request 包装：

```text
code: XVERIF_CLI_FAILED
stdout_tail:
  action: batch
  code: INVALID_REQUEST
  invalid_arg: args.requests
  expected: type "array"
  received_type: string
  correct_example: {"api_version":"xdebug.v1","action":"batch","args":{"requests":[{"api_version":"xdebug.v1","action":"schema"}]}}
```

这个错误对人和 AI 都足够可修复，问题主要仍是 MCP raw_request 顶层没有提升结构化字段。

子请求失败时，例如第一个 child `schema.kind:"bad_kind"`，`xverif_debug_query` 实际返回：

```text
code: BATCH_PARTIAL_FAILURE
message: one or more child requests failed
recoverable: true
```

同样错误通过 raw_request 会再包一层：

```text
code: XVERIF_CLI_FAILED
stdout_tail:
  action: batch
  code: BATCH_PARTIAL_FAILURE
  message: one or more child requests failed
  recoverable: true
```

清晰度评价：

- `BATCH_PARTIAL_FAILURE` 说明有 child 失败，但 query/raw 默认都没有显示第几个 child、哪个 action、child error 是什么。
- 对 AI 修复非常不够：必须改用 JSON/envelope 或重放 child request 才知道如何修。
- 作为批处理工具，失败定位字段应比单 action 更强，而不是更弱。

建议：

- batch partial failure 的 xout/error 必须至少包含：
  - `failed_index`
  - `failed_action`
  - `child_error.code`
  - `child_error.invalid_arg`
  - `child_error.message`
  - `child_error.correct_example`
- MCP raw_request wrapper 也应提升 `BATCH_PARTIAL_FAILURE` 的 child details。

### 成功返回评审

成功 batch 调两个 schema request，默认 xout 返回：

```text
summary:
  count: 2
  all_ok: true
results:
  api_version ok action tool.name tool.version summary.action summary.kind data.schema_path
```

对 debug 的价值：

- 非常适合快速确认一批请求是否全部成功。
- 对 schema/path 类结果，表格 compact 且信息密度合适。
- `summary.count/all_ok` 直接可读，适合作为批量执行摘要。

冗余/风险：

- 成功路径不冗余。
- 如果 child 返回复杂 payload，默认表格可能只保留少数扁平字段；这对 quick scan 合理，但需要提醒用户详细证据应单独查或用 JSON。

### 结论

- 成功返回：清晰、紧凑、有用。
- 失败返回：schema 层错误可修复；child partial failure 在 query/raw 两个入口都缺少 child details，严重影响 AI 自动修复。

### Agent Review

独立 agent 认为 child failure 定位不足的结论证据充分；关于复杂 payload 被压扁应表述为 xout 风险而非已完全证实。

## 2. `schema`

### MCP 调用方式

- query 成功调用：`xverif_debug_query(session_id="session_open_review_20260709", action="schema", args={"action":"value.batch_at","kind":"request"})`
- query 失败调用：`kind:"bad_kind"`
- raw 成功调用：`xverif_debug_raw_request(request={"api_version":"xdebug.v1","action":"schema","args":{"action":"value.batch_at","kind":"request"}})`
- raw 失败调用 1：`kind:"bad_kind"`
- raw 失败调用 2：`action:"no.such.action"`

### 失败返回评审

`kind:"bad_kind"` 的 `xverif_debug_query` 返回：

```text
code: INVALID_REQUEST
message: schema args.kind must be request or response
recoverable: true
```

同样错误通过 raw_request 会再包一层：

```text
code: XVERIF_CLI_FAILED
message: xdebug exit 1
stdout_tail: @xdebug.error.v1
  action: schema
  code: INVALID_REQUEST
  message: schema args.kind must be request or response
  recoverable: true
```

`action:"no.such.action"` 的实际 MCP 顶层返回：

```text
code: XVERIF_CLI_FAILED
stdout_tail: @xdebug.error.v1
  code: UNKNOWN_ACTION
  message: unknown action: no.such.action
  recoverable: true
```

清晰度评价：

- query/raw 两个入口中，message 都能让人理解问题，但机器可恢复字段不足。
- 缺少 `invalid_arg:"args.kind"` 和 `allowed_values:["request","response"]`。
- unknown action 缺少候选建议，例如 `did_you_mean` 或提示先调用 `actions`。
- raw_request 还额外受 wrapper 影响，backend 错误被包在 `stdout_tail` 中。

建议：

- 对 `args.kind` 错误返回 `invalid_arg`、`allowed_values` 和 `correct_example`。
- 对未知 action 可返回 `did_you_mean` 或 `suggestion:"call actions first"`。
- MCP wrapper 提升 backend error 结构，避免 AI 解析 `stdout_tail`。

### 成功返回评审

默认 xout 返回 `value.batch_at` request schema，包括：

- schema id/title/type
- top-level required：`api_version/action/args`
- action enum
- args 下的 `clock/edge/format/sample_point/signals/slice_hint/time/time_unit`
- enum 值
- args required：`signals/time/clock`
- `x-purpose/x-how_it_works/x-when_to_use/x-arg_contract_notes`
- schema path

对 debug 的价值：

- 对 AI 查参数很有用，能看到 required、enum 和说明。
- 对确认 source-of-truth 路径有用。

冗余/风险：

- schema xout 把 JSON schema 层级压平后可读性一般：`signals` 字段名在 `oneOf` 段落中不明显，容易让 AI 看漏。
- `additionalProperties:false` 在 xout 中出现位置靠近 `time_unit`，可能被误读为 `time_unit` 的属性，而不是 `args` 对象约束。
- 对复杂 schema，建议 AI 使用 MCP `xverif_debug_get_schema(..., kind="request")` 的结构化 JSON，而不是默认 xout。

### 结论

- 成功返回：对人工快速看 schema 有价值，但复杂 schema 的 xout 层级表达不够稳。
- 失败返回：query 入口保留了 backend error，但 backend 本身缺少结构化可恢复字段；raw_request 入口还会额外包装。

### Agent Review

独立 agent 认为结论合理；建议进一步区分 query 入口与 raw wrapper 的错误证据，避免入口差异混淆。
