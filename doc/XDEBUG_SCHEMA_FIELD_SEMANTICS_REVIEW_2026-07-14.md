# xdebug schema 域字段语义评审（2026-07-14）

## 结论

当前 xdebug 的 action 目录、request schema、response schema 和 example 已能让调用方发现 action，并在一部分动作中构造正确请求；但**不能保证仅依赖 schema 的 agent 清楚理解每个域字段的含义**。主要障碍是：多数公共对象被声明为开放的 `object` 或无元素约束的 `array`，字段的语义、单位、条件依赖、完整性和 `summary/data` 归属只能从 example、skill 或运行时代码反推。

本轮为只读静态评审：覆盖 `actions.yaml` 登记的 72 个 request schema、72 个 response schema 和对应 request/response example；另专项检查 AXI/APB、stream、event、handshake 与 active-driver 合同。未运行 EDA/NPI/FSDB，也未修改源码、schema、example 或已有文档。报告由三个独立审阅面交叉核对后汇总。

结论按风险排序如下：

| 优先级 | 结论 | 影响范围 |
| --- | --- | --- |
| P0 | 大多数 request 的 `target`、`limits` 和部分核心 `args` 是开放对象；多数非 AXI response 的 `summary`、`data`、`findings`、`error` 也没有字段合同。 | 公共 action 的构造、解析、校验均不能由 schema 完成。 |
| P1 | 时间、协议配置、stream 查询、事件预算、证据和截断的语义不自描述；AXI 严格结构中仍缺关键业务字段的语义。 | agent 容易构造语义错误请求，或把部分结果解释为完整结果。 |
| P2 | 通用描述复用过度、部分字段字典路径漂移、少量公开但未定义的域。 | 降低可发现性，并可能把 agent 引向不存在的字段。 |

## 评审准则

一个公开域字段要被视为“可清楚描述”，其 action-specific schema 至少应能表达：

1. 字段用途与值域（对象必须列出 properties，数组必须列出 items）。
2. 时间/数值的单位、编码、窗口边界与采样语义。
3. `oneOf`/条件必填/互斥字段的选择规则和优先级。
4. 数据是否完整，以及扫描、分析、响应返回、渲染截断分别发生在哪一层。
5. `summary`（聚合结论）与 `data`/`findings`（逐项证据）的稳定边界。

这与 [schema-validation.md](agents/xdebug/schema-validation.md) 已定义的“字段边界清晰”“summary/data/findings/evidence 类型明确”和精确截断规则一致；example 应展示实例，不能成为唯一的字段字典。

## P0：schema 无法表达核心域字段

### 1. request 的资源与控制域普遍开放

绝大多数 request schema 将 `target` 和/或 `limits` 写成仅有 `type: object` 的对象，既没有字段白名单，也没有 `additionalProperties: false`。例如：

- `stream.query` 的 `target` 与 `limits`：`xdebug/schemas/v1/actions/stream.query.request.schema.json:24-25,141-143`。
- `event.find` 的 `target`：`xdebug/schemas/v1/actions/event.find.request.schema.json:27-29`。
- `axi.channel_stall` 的 `target` 与 `limits`：`xdebug/schemas/v1/actions/axi.channel_stall.request.schema.json:27-29,94-96`。

结果是 schema 既不能说明 `session_id`、`daidir`、`fsdb`、`run_manifest` 在哪个动作有效，也不能拒绝拼错的资源/限制字段。`session.open` 更直接暴露了这个断裂：其 `target` schema 只列出 `run_manifest`，但 example 使用 `daidir` 和 `fsdb`，同时该 schema 的提示又称会解析它们（`xdebug/schemas/v1/actions/session.open.request.schema.json:27-35,95`；`xdebug/examples/requests/session.open.basic.json:4-7`）。

**建议**：按 `requires` 和 action 实际能力定义闭合的 target `$defs`，用 `oneOf`/`anyOf` 表达已开 session 与路径开 session 的合法组合；无资源 action 不公开 `target`。`limits` 只在 handler 实际支持时公开，并列出所有字段及单位。

### 2. 非 AXI response 多为宽松外壳，不能提供机器可读字段含义

61 个非 AXI response schema 中有 57 个复用宽松模板：`summary` 仅为允许任意属性的 object，`data` 仅为 object，`findings`/`warnings` 仅为 array，`error` 无稳定结构，根对象同样允许未知字段。典型证据见 `xdebug/schemas/v1/actions/signal.changes.response.schema.json:32-52`，`handshake.inspect` 和 `apb.query` 也具有相同形态（分别见 `:32-50`）。

这使 transfer、stall、APB transaction、finding、时间、evidence 以及 `summary/data` 边界都无法由 schema 表达或验证。`x-output_notes` 让调用方“以 schema 和 example 为准”并不能修复该问题，因为 example 是单个实例而非字段合同。

**建议**：先定义共享的稳定 response `$defs`（error、warning、evidence、completeness、time），再为每个 action 关闭 `summary`、`data` 与 finding item。`apb.statistics` 的严格 `summary/data/filter/notes/analysis_quality` 结构可作为非 AXI 基线（`xdebug/schemas/v1/actions/apb.statistics.response.schema.json:163-238`）；trace 类已定义部分 source-context 结构，也可复用。

### 3. stream 的查询与配置域无法由 schema 独立理解

`stream.query.args.query` 允许任意 object，仅有“stream 查询条件”的笼统描述（`xdebug/schemas/v1/actions/stream.query.request.schema.json:98-108`）。`match` 未要求 `op`；`range` 不要求上下界，比较条件也未要求 `value`（`:50-92`）。唯一 basic example 只展示字符串 `"summary"`，没有定义 object 分支（`xdebug/examples/requests/stream.query.basic.json:8-14`）。

`stream.config.load` 中单 stream 配置的 `signals` 是任意 alias 到 string 的 map；`clock`、`vld`、`rdy`、`bp`、`reset`、`sop/eop`、`data`、`beat_fields` 与 `packet_stable_fields` 的值究竟是 alias、信号路径还是表达式，以及相互依赖都没有 schema 字段说明（`xdebug/schemas/v1/actions/stream.config.load.request.schema.json:47-125,162-240`）。example 同时出现 alias、`!rst_n` 和 SV expression，进一步说明这不是单纯 string path（`xdebug/examples/requests/stream.config.load.basic.json:12-35`）。

**建议**：定义可重用且闭合的 `StreamDefinition`；分别标注 alias 解析和表达式语法，列出 edge/sample-point 默认及 `dual` 的适用关系。为 query object 建带 discriminator 的闭合 schema，使用条件约束表达 `range => lo/hi`、比较 => `value`，并说明 `packet_index`、`channel`、`field_scope` 与 `query/match` 是否可组合。

## P1：字段存在但语义、单位或完整性不足

### 4. 时间合同没有成为 schema 自描述内容

`args.time`、`time_range.begin/end` 在多动作中仅为 string；`time_unit` 虽有 enum 但无说明。例如 `stream.query`（`xdebug/schemas/v1/actions/stream.query.request.schema.json:113-136`）、`event.find`（`:104-128`）和 `axi.channel_stall`（`:63-87`）。因此 agent 无法仅由 schema 得知：带单位字符串与 `time_unit` 的优先级、`auto` 如何解析、是否接受裸数、窗口端点是否包含、缺失一端的默认值。`trace.active_driver_chain.clk_period` 还只有描述文字中的 default，没有 JSON Schema `default`（`xdebug/schemas/v1/actions/trace.active_driver_chain.request.schema.json:44-47`）。

**建议**：提供公共 time `$defs`，写明 canonical grammar、单位/优先级、窗口边界和默认。每个动作有特殊采样语义时在 action-specific field 覆盖；默认值同时进入 schema 的 `default`。

### 5. 截断与完整性不能区分发生层级

18 个非 AXI example 只发布 bare `truncated`，且位置不一致：`event.export` 在 summary 中给 `truncated/row_count/line_limit`（`xdebug/examples/responses/event.export.basic.json:5-14`），`signal.statistics` 在 data 中给 `truncated`（`xdebug/examples/responses/signal.statistics.basic.json:12-20`），`sampled_pulse.inspect` 的 summary 为空、却以 `meta.truncated` 标示不完整（`xdebug/examples/responses/sampled_pulse.inspect.basic.json:5-11,252-255`）。61 个非 AXI response schema 中只有 `apb.statistics` 明确 `analysis_complete`；没有一个稳定声明 `scan_complete`、`response_truncated` 和 `render_truncated`。

AXI 生成 schema 虽有这些字段的候选位置，但 `common_summary()` 不要求它们，因此请求范围、扫描范围、`analysis_complete` 和截断均可省略（`xdebug/tools/sync_axi_response_schemas.py:205`）。`axi.analysis` example 也仅给 `full_scan_count`，没有完整性结论（`xdebug/examples/responses/axi.analysis.basic.json:5`）。

**建议**：定义统一 completeness object；当预算、截断或部分分析可能发生时，明确 required 的 `scan_complete`、`analysis_complete`、`response_truncated`、`render_truncated`（不适用时应返回 `true` 或 `null`，而非省略），并列出触发预算和受影响的范围。

### 6. 事件、协议 config 与 transport 的域语义不足

- `event.find` 的 `aggregate`、`group_by`、`events`、`max_samples`、`mode`、`rst_n` 缺 item shape 或字段说明；`line_limit` 只在特定 mode 可用，但这个条件不能从字段定义理解（`xdebug/schemas/v1/actions/event.find.request.schema.json:33-77,133-151`）。`event.export` 同类字段更多，basic example 未给 `output.path`，无法判断该动作是否必然写文件或其路径何时必填（`xdebug/examples/requests/event.export.basic.json:7-15`）。
- AXI/APB `config.load.config` 的协议缩写字段是 required 信号 string，但没有说明通道角色、方向、每 beat 语义和路径要求（AXI：`xdebug/schemas/v1/actions/axi.config.load.request.schema.json:29-175`；APB：`xdebug/schemas/v1/actions/apb.config.load.request.schema.json:29-95`）。`config` 与 `config_path` 使用 `anyOf`，因而可同时提供却无优先级；应改为 `oneOf`，或明确无 fallback 的冲突错误。
- `session.open.args` 的 `bind`、`bind_host`、`host`、`port` 无描述，port 未限定 1--65535，也没有以 transport 为 discriminator 限制 UDS/TCP/file 与资源目标的合法组合（`xdebug/schemas/v1/actions/session.open.request.schema.json:39-71`）。

### 7. AXI 严格结构缺少业务语义，且字段字典有两处漂移

10 个 AXI action 的 response schema 由生成器关闭未知字段，结构优于宽松模板；但几乎所有业务字段仍是无语义的 string/boolean。`TIME` 只说“规范化时间字符串”，不能区分 handshake、payload begin、扫描窗口或 duration；`latency`、`match_time`、`phase_order`、`response_dependency_violation`、`pairing_rule`、`read_event/write_event` 缺枚举、单位或 required 规则（`xdebug/tools/sync_axi_response_schemas.py:71,112,285,307`）。`axi.statistics` 甚至不在 `AXI_ACTIONS` 生成清单中，仍使用泛化 response（`:18`；`xdebug/examples/responses/axi.statistics.basic.json:5`）。

尤其 `valid_begin_time` 的正确但反直觉语义没有进入 schema：它是当前 payload 首次被采样为 VALID 并持续到该 beat handshake 的时间；连续 VALID 的 back-to-back payload 从前一 handshake 后的下一采样点起算，而不是 VALID 上升沿。该定义目前只在字段字典中（`skills/xverif/references/xdebug/response-fields.md:943,957`）。

字段字典还有两处实际路径漂移：

- 它把 `axi.channel_stall` 的 `name/channel/sample_count/...` 写为 `data.*`（`skills/xverif/references/xdebug/response-fields.md:1049`），而当前 schema、example 和实现都将其置于 `summary.*`（`xdebug/tools/sync_axi_response_schemas.py:307`；`xdebug/src/waveform/server/service/query_actions.cpp:397`）。
- 它把 `axi.export` 描述为 `data.begin/end/scan_begin/scan_end/write_file...`（`skills/xverif/references/xdebug/response-fields.md:988`），当前严格 schema 则使用 `summary.requested_range/scanned_range/output`（`xdebug/tools/sync_axi_response_schemas.py:350`）。

**建议**：在 AXI response 生成器的 `$defs` 中为每个业务字段加入双语 description、enum/required 与单位；将 `valid_begin_time` 的完整定义加入其字段 schema；把 `axi.statistics` 纳入生成器或为其维护同等严格的专用 schema；同步修正字段字典路径。

### 8. evidence、数值编码与 finding 的稳定形态缺失

- `trace.active_driver` example 包含 `requested_time`、`active_time`、`driver_last_change_time`、`time_semantics` 和 evidence 字段，但宽松 schema 不定义枚举、单位或必填关系；chain schema 也只将其中不少字段约为 string/object（`xdebug/examples/responses/trace.active_driver.basic.json:5-20`；`xdebug/schemas/v1/actions/trace.active_driver_chain.response.schema.json:85-121,200`）。
- `counter.statistics` 的 min/max/average 使用 string，却未说明数值编码、位宽或 X/Z 的纳入规则（`xdebug/examples/responses/counter.statistics.basic.json:5-10,27-30`）。`signal.statistics` 的 `high_cycles/low_cycles/transition_count/high_ratio/activity` 同样缺采样与 raw-change 边界（`xdebug/examples/responses/signal.statistics.basic.json:5-48`）。
- `sampled_pulse.inspect.data.findings` 混用 `raw_begin/raw_end` 与 `raw_time`、`payload` 与 `sampled_payloads`，没有 discriminator/required 形态；example 的 `risk_count=6` 但只列 4 项，且 `meta.truncated=true`，无法由 schema判断列表是否完整（`xdebug/examples/responses/sampled_pulse.inspect.basic.json:23-39,66-105,252-255`）。`handshake.inspect` 的 findings 同样没有 item 合同。

**建议**：为 evidence、统计、finding 定义可区分的 tagged object；明确 value encoding（例如 canonical string、radix、bit width、four-state 处理）和采样域；每个 response 将总数、返回数、截断状态和 evidence 列表显式关联。

## P2：可发现性与一致性问题

- `axi.channel_stall.args.rules` 允许任意 array/object，未定义 rule item 或默认规则（`xdebug/schemas/v1/actions/axi.channel_stall.request.schema.json:53-62`）。
- `trace.active_driver.args.limits` 是无定义对象，而已存在 canonical top-level `limits`；容易使调用方把深度等控制项写入错误位置（`xdebug/schemas/v1/actions/trace.active_driver.request.schema.json:44-46,74-99`）。应删除、拒绝或明确迁移该公开域。
- 多个 `args.name` 共用“已保存配置、游标、列表或接口配置名称”的泛化说明，无法指出实际命名空间（例如 `session.open` 的 `name`）。应改为 action-specific 描述。
- `event.export` 中 `events` 与 `preview`、`stream.export` 中 `summary.output` 与空 `data`、`batch.data.results` 与 summary failed count 的对应关系，都缺稳定边界（分别见 `xdebug/examples/responses/event.export.basic.json:15-37`、`stream.export.basic.json:5-20`、`batch.basic.json:5-20`）。

## 已具备的良好基线

以下合同已经足以作为收紧其它 schema 的样板，不应在整改时退化：

- `axi.query` 对 query 的两种形态和 selector 排斥关系已有较清楚的约束与 example（`xdebug/schemas/v1/actions/axi.query.request.schema.json:202-207`；`xdebug/examples/requests/axi.query.basic.json:8-15`）。
- AXI/APB statistics 对 address 的 exact/range/mask `oneOf`、过滤 AND 与 ID 内 OR 的规则较完整。
- AXI transaction 已有 address/data/response 分组、channel enum、beat index 从 1 开始、`include_data` 才返回 beats 的结构；其运行时 latency 和 B dependency 规则也与字段字典一致（`xdebug/tools/sync_axi_response_schemas.py:98`；`xdebug/src/waveform/axi/axi_transaction_json.cpp:10`；`xdebug/src/waveform/axi/axi_transaction_tracker.cpp:89`）。
- `apb.statistics` 已展示闭合 summary/data、`analysis_complete`、analysis quality、filter 和 notes 的非 AXI 方向。

## 建议的整改顺序（未实施）

1. **先建立共享词典与严格模板**：time、resource target、limits、completeness、error、evidence、value encoding、finding；所有 public object 默认关闭未知字段。
2. **优先修 P0 action**：session、stream、event、handshake/APB query，以及 57 个宽松 response；从 `apb.statistics` 和已有 trace/AXI `$defs` 抽取可复用部件。
3. **补齐语义和条件关系**：协议 config、transport、query discriminators、时间窗口、scan/response 预算；同步每个 example，使其只示范而不承担唯一说明职责。
4. **修正 AXI 生成器与字段字典**：覆盖 `axi.statistics`，将 `valid_begin_time` 等业务语义进入 schema，消除两处 response-fields 路径漂移。
5. **验证**：按现有说明先运行 `sync_runtime_request_schemas.py --check`、`sync_axi_response_schemas.py --check`、`sync_action_schema_hints.py --check`、schema/example 校验及相应 catalog suite；涉及真实 FSDB/NPI 的 contract 全程在沙箱外执行。

## 附录 A：字段级问题登记册

本附录补充主报告中的模式级结论。每条记录均给出可定位字段、当前可见合同、误用后果和应有的精确约束；它不是实施清单，也没有修改任何 public contract。

| ID | action 与字段路径 | 当前合同与证据 | 缺失语义 / 误用风险 | 建议的精确合同 |
| --- | --- | --- | --- | --- |
| REQ-01 | `session.open.target.daidir/fsdb/run_manifest` | schema 只列 `run_manifest`，却说明会解析 daidir/fsdb；basic example 传入 daidir/fsdb。见 `xdebug/schemas/v1/actions/session.open.request.schema.json:27-35,95`、`xdebug/examples/requests/session.open.basic.json:4-7`。 | 无法判断 design/waveform 是否可单独打开、manifest 是否与路径互斥或只作校验；拼错路径字段仍会过 schema。 | 关闭 target；用 `oneOf` 明确 `session_id`、仅 daidir、仅 fsdb、daidir+fsdb、仅 manifest 的合法分支；若 manifest 允许附带路径校验，显式声明其不改变 canonical resource。 |
| REQ-02 | 多动作 `target`、`limits` | `stream.query:24-25,141-143`、`event.find:27-29`、`axi.channel_stall:27-29,94-96` 只约束为 object。 | 调用方可猜测 `session`、`timeout`、`max_depth` 等任意字段，无法识别 handler 是否使用。 | 按 `requires` 建 action-specific target `$defs`；未使用 limits 的动作删除该域，使用者关闭属性并发布 minimum/default/截断作用域。 |
| REQ-03 | `trace.active_driver.args.limits` 对比顶层 `limits` | args 下是无定义 object，顶层才定义 `max_depth/max_nodes/max_alias_candidates/max_trace_signals`。`xdebug/schemas/v1/actions/trace.active_driver.request.schema.json:44-46,74-99`。 | 同一概念两个位置，可能被写入 args 后静默无效。 | 删除 args 下同名域；如保留兼容必须标 deprecated 并由 runtime 明确报错/警告，不能静默忽略。 |
| REQ-04 | `stream.config.load.config.streams[]` 与 `args.streams[]` | 两套重复定义；signals 为任意 `alias -> string`，clock/vld/rdy/bp/reset/sop/eop/data/fields 多无描述。`stream.config.load.request.schema.json:47-125,162-240`。 | 不知道引用 alias、路径还是表达式；无法判断 rdy/bp、sop/eop、channel_id/allow_interleaving 的依赖。example 已混用 alias、`!rst_n`、SV expression。 | 提取闭合的 `$defs.stream_definition`，两处引用同一对象；字段写明 alias-resolution/表达式 grammar。条件约束：interleaving=>channel_id，channel_id_valid=>channel_id 和相应 SOP/EOP；发布 edge/sample-point 默认。 |
| REQ-05 | `stream.query.query`、`match`、`field_scope` | query object 无 properties；match 仅 required `field`，range 不要求 lo/hi，比较不要求 value。`stream.query.request.schema.json:34-108`；example 只展示 `"summary"`。 | `{query:{}}`、缺范围值的 range 等无效请求可通过；顶层和嵌套 field_scope 并存时无优先级。 | string 分支 enum；object 分支以 kind discriminator 闭合。match required field/op；if range=>lo+hi，比较=>value；明确/约束 mask，禁止或合并双 field_scope。 |
| REQ-06 | `event.find.aggregate/group_by/events/max_samples/rst_n/mode` | aggregate 是开放 object，group_by 无 items，多数字段无说明。`event.find.request.schema.json:33-77`。 | 不知道聚合函数、group key、reset 极性及 scan 与 response 预算；易把 line_limit 当扫描预算。 | 聚合稳定则定义闭合对象（operation/field/output）；group_by 指定 item；max_samples/max_events 说明为 scan/file budget，耗尽时关联 completeness。reset 改为语义明确的 signal/expr 字段。 |
| REQ-07 | `event.find.mode` / `line_limit` | 条件约束令 line_limit 仅在 `mode:"all"` 合法，但字段说明没有写出。`event.find.request.schema.json:54-71,133-151`。 | first/last 请求带 line_limit 会得到难解释 schema error；也不知道 first/last 是否完整扫描。 | mode 描述 first/last/all 的选择、排序和扫描含义；line_limit 声明“仅 all，且只裁剪 response/XOUT evidence”；补三种最小 example。 |
| REQ-08 | `event.export.output.path/file_format` | action 与 output 描述指向导出，然而 output/path 均 optional，basic example 无 output。`xdebug/examples/requests/event.export.basic.json:7-15`。 | 调用方无法判断是否真的落盘。 | 若必写文件则 required output.path；若允许 response-only，用 destination discriminator 区分 file 与 response，并补带路径 example。 |
| REQ-09 | `axi.config.load.config.*` | 31 个 required mapping 均是无说明的 string；edge/sample_point 无已发布默认。`xdebug/schemas/v1/actions/axi.config.load.request.schema.json:29-175`。 | 可能颠倒 valid/ready，误解连续 valid payload 的采样时刻。 | 在生成器维护每个映射的协议角色、方向、每-beat 语义、路径/表达式限制和采样默认。 |
| REQ-10 | `apb.config.load.config.*` | PREADY/PSLVERR 等映射无字段说明；basic example 仅示范 config_path。`xdebug/schemas/v1/actions/apb.config.load.request.schema.json:29-95`。 | 可能把 PREADY 当可选/always-ready，或混淆 PWDATA/PRDATA。 | 明确 PREADY/PSLVERR 必填、wait/error sampling、读写数据方向；增加 inline config 最小 example。 |
| REQ-11 | APB/AXI `config` + `config_path`；stream 多输入源 | 使用 anyOf，多个来源可同时出现而无 precedence。 | 容易产生隐式覆盖、合并或 fallback 预期。 | 无合并合同则 `oneOf`；若允许合并，增加显式 source_policy，并针对 mode 与输入源建立 if/then。 |
| REQ-12 | `session.open.args.transport/bind/bind_host/host/port` | transport enum 为 uds/tcp/file，但字段无描述、port 无范围、没有 conditional dependency。`session.open.request.schema.json:39-71`。 | TCP 可能漏 port，UDS 可误带 host/port，file transport 输入不清。 | transport required/default 明确；tcp=>host+port(1..65535)，uds=>明确 socket_path 并禁止 TCP fields，file=>明确文件路径并禁止网络 fields。 |
| RSP-01 | 57 个非 AXI action 的 `summary/data/findings/warnings/error/meta` | 宽松模板要求 summary/data，却允许根和核心对象任意字段；典型见 `signal.changes.response.schema.json:6-52`。 | 不能从 schema生成 decoder、字段词典或错误处理；拼写/单位/数组项漂移都无法发现。 | success/error 用 oneOf；共享 Time/LogicValue/Completeness/Evidence/Finding/Error `$defs`；每个业务对象关闭 unknown fields 并写双语描述。 |
| RSP-02 | 多动作 `summary.truncated`，`signal.statistics.data.truncated` | 同一 bare 字段位置不一致；非 AXI 没有 scan_complete/response_truncated/render_truncated。`event.export.basic.json:5-14`、`stream.export.basic.json:5-18`、`signal.statistics.basic.json:12-20`。 | 不知道不完整的是扫描、分析、inline response、XOUT 还是文件。 | required `completeness`：scan_complete、analysis_complete、response_truncated、render_truncated、file_complete、truncation_scopes、returned/total count；bare truncated 仅兼容派生字段。 |
| RSP-03 | `sampled_pulse.inspect.data.findings[]` | summary 空；risk_count 为 6、返回 4 项且 meta.truncated。两类 finding 分别使用 raw_begin/raw_end 或 raw_time/payload。`sampled_pulse.inspect.basic.json:10,23-39,66-105,252-255`。 | 不知道是否是全量/前 N 项；无法按 finding 类型安全解析。 | `oneOf` + type const：pulse 分支 required raw_begin/raw_end/edge evidence，payload 分支 required raw_time/payload；summary required total/returned/completeness，first_risk 为 Finding 或 null。 |
| RSP-04 | `trace.active_driver` / `trace.active_driver_chain` 时间与 evidence | example 有 requested/active/last-change time、scope/status/source；active_driver 是宽松模板，chain 对应字段仍多为 string/object。`trace.active_driver.basic.json:5-20`、`trace.active_driver_chain.response.schema.json:85-122,200`。 | 静态候选可被误报为 active evidence，无法区分请求时刻、有效时刻及 unavailable/ambiguous。 | 固定 TimeSemantics；Evidence required scope enum、status enum、source enum/null 与静态/active 计数；summary 放 verdict/计数，data 放 paths/hops/evidence。 |
| RSP-05 | `counter.statistics`、`signal.statistics` | min/max/average 用 string，统计/采样/unknown 闭包未定义；signal high_ratio、transition_count 边界仅在 example。 | 不知道进制、位宽、有符号/XZ 排除，或 transition 是 raw 还是 sampled。 | 定义 Numeric/LogicValue；required sample/eligible/valid/unknown 计数；raw 和 sampled transition 分名；ratio 携带 denominator 与 null availability reason。 |
| RSP-06 | `event.export`、`stream.export`、`batch` summary/data 关系 | event 同时有 events/preview；stream artifact 放 summary 而 data 空；batch 的并行 failed arrays 不映射 results。`event.export.basic.json:5-40`、`stream.export.basic.json:5-20`、`batch.basic.json:5-20`。 | 不知道 preview 是否完整、artifact 是否写成，或失败项对应哪条 request。 | summary 只放 totals/completeness；data 使用 inline_events/preview/artifact；batch result 必带 index/request_action/result-or-error，避免平行数组。 |
| AXI-01 | `axi.statistics` summary/data | 不在 `AXI_ACTIONS` 生成清单，仍为泛化 response。`sync_axi_response_schemas.py:18-30`；example `axi.statistics.basic.json:5-27`。 | matched 可能被当完整总数，unresolved 可能被当错误 transaction。 | 纳入生成器；required analysis_complete、analysis_quality(enum complete/ambiguous)、full_scan_count、unresolved count/filter；明确 ambiguous 时 matched 不是完整过滤结论。 |
| AXI-02 | AXI transaction `*.valid_begin_time`、handshake_time、latency、match_time | schema 通用 TIME 仅称规范化 string。`sync_axi_response_schemas.py:71-80,112-158`。 | 易把 valid_begin 当 VALID rising edge、用 W/R data 时刻算 latency、把 match time 当完成时刻。 | 每字段写业务描述：valid_begin 为当前 payload 首次 sampled-valid（back-to-back 从前 handshake 后下一采样点）；latency=AR/AW handshake 到 RLAST/B handshake；match_time 是 filter anchor。 |
| AXI-03 | `response_dependency_violation`、`pairing_rule`、`phase_order` | boolean/string 无 enum/required。`sync_axi_response_schemas.py:146-158,294-305`。 | W-first 可被误判违规；B 早于 WLAST 的违规可能漏报；配对 FIFO/per-ID 规则不清。 | 描述 violation 为 B 不严格晚于匹配 AW 与 WLAST；pairing 三规则 required；phase_order enum `aw_before_w|same_cycle|w_before_aw|unknown` 并写明 W-first 合法。 |
| AXI-04 | `axi.channel_stall` finding 与 outstanding events | type/severity/event 为任意 string，common summary 无 required。`sync_axi_response_schemas.py:205-222,307-332`。 | ready-only 被当协议错误、open interval 的 end 被当最后 stalled sample、空 findings 被当无 stall。 | long_stall/warning、AR/RLAST/AW/B event 使用 enum；open_at_window_end required；returned/total/complete/truncation 与 sampled time semantics required。 |
| AXI-05 | 字段字典 `axi.channel_stall`、`axi.export` | dictionary 分别写成 `data.*`，实际为 `summary.*`；export dictionary 也与 requested/scanned/output 当前结构不同。`response-fields.md:988-1003,1049-1064`；`sync_axi_response_schemas.py:307-370`。 | agent 会读取不存在的路径并混淆用户过滤窗口、实际扫描窗口与 preview/落盘。 | 以 runtime/schema 为准同步字典：channel_stall counters 在 summary；export 明确 requested_range、scanned_range、output_written、preview 和 row_count 的关系。 |

## 附录 B：补充的正向合同检查点

- AXI transaction 的 address/data/response 分组、channel enum、`beats` 仅在 `include_data=true` 时存在、beat `index>=1`，已经提供了可复用结构基线（`xdebug/tools/sync_axi_response_schemas.py:98-158`）。
- trace chain 的 source-path/source-context 已具备部分严格证据结构（`xdebug/schemas/v1/actions/trace.active_driver_chain.response.schema.json:151-198`）；后续应提升为共享 `SourceEvidence`，补 closed shape、path_kind、source_revision 和 path_direction。
- APB/AXI statistics 的 address exact/range/mask `oneOf` 和过滤组合规则可作为 event/stream filter 的建模范式，而非以开放 object 代替。
