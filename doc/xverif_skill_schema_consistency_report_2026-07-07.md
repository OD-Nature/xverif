# xverif skill schema 一致性检查报告

日期：2026-07-07

范围：

- `skills/xverif/`
- `~/.codex/skills/xverif/`
- `xdebug/schemas/v1/actions/*.request.schema.json`
- `xcov/xcov/schemas.py`
- `xverif_mcp/src/xverif_mcp/server.py`

本次检查只读完成，未修改代码或 skill 文档。

## 总结

`skills/xverif` 与已安装的 `~/.codex/skills/xverif` 当前完全同步，没有镜像差异。

主要不一致集中在 xdebug 的 action 参数描述与 request schema 之间。xcov 示例与 `xcov/xcov/schemas.py` 当前 schema 对齐；xbit、xentry、xloc、xsva 文档与 MCP wrapper 签名未发现明显参数名漂移。

## 发现的问题

### 1. 多个 waveform value/verify action 漏写 `clock` 必填项

受影响 action：

- `value.at`
- `value.batch_at`
- `expr.eval_at`
- `list.value_at`
- `verify.conditions`

skill 文档中这些 action 的 required 描述或示例没有 `clock`：

- `skills/xverif/references/xdebug/action-reference.md`
- `skills/xverif/references/xdebug/json-api.md`
- `skills/xverif/references/xdebug/recipes.md`

但实际 schema 的 `args.required` 均包含 `clock`。例如：

- `xdebug/schemas/v1/actions/value.at.request.schema.json`：`signal,time,clock`
- `xdebug/schemas/v1/actions/value.batch_at.request.schema.json`：`signals,time,clock`
- `xdebug/schemas/v1/actions/expr.eval_at.request.schema.json`：`expr,time,signals,clock`
- `xdebug/schemas/v1/actions/list.value_at.request.schema.json`：`name,time,clock`
- `xdebug/schemas/v1/actions/verify.conditions.request.schema.json`：`conditions,time,clock`

影响：AI 按 skill 示例构造请求时，会缺少 schema 必填字段。

### 2. schema 内部的 `x-arg_contract_notes` 与 `required` 不一致

多个 schema 文件的真实 `args.required` 已包含 `clock`，但同文件的 `x-arg_contract_notes` 仍是旧描述。例如：

- `value.at.request.schema.json`：真实 required 是 `signal,time,clock`，但 notes 写 `required: signal, time`
- `value.batch_at.request.schema.json`：真实 required 是 `signals,time,clock`，但 notes 写 `required: signals, time`
- `expr.eval_at.request.schema.json`：真实 required 是 `expr,time,signals,clock`，但 notes 写 `required: expr, time, signals`
- `list.value_at.request.schema.json`：真实 required 是 `name,time,clock`，但 notes 写 `required: name, time`
- `verify.conditions.request.schema.json`：真实 required 是 `conditions,time,clock`，但 notes 写 `required: conditions, time`

影响：如果 `action-reference.md` 是由 schema metadata 生成，单独改 Markdown 会再次被旧 metadata 覆盖。

### 3. `axi.analysis` recipe 示例不符合 schema

`skills/xverif/references/xdebug/recipes.md` 中 `axi.analysis` 示例包含：

- `time_range`
- `max_items`
- `direction: "read"`

但 `xdebug/schemas/v1/actions/axi.analysis.request.schema.json` 中 `args` 只允许：

- `analysis`
- `direction`
- `id`
- `include_transactions`
- `name`
- `time_unit`

并且 `direction` enum 为：

- `wr`
- `rd`
- `all`

影响：示例请求按 schema 校验会失败；`read` 应改为 `rd`，`time_range/max_items` 应移到实际支持该筛选的 action 或改为 `limits`/其他合法参数。

### 4. `session.kill` required 描述过窄

`skills/xverif/references/xdebug/action-reference.md` 写：

- `session.kill` required: `session_id`

实际 `xdebug/schemas/v1/actions/session.kill.request.schema.json` 允许三种形式：

- `target.session_id`
- `args.session_id`
- `args.id`

`session.close` 的描述已经是正确的同类写法。

影响：文档会误导调用方只传裸 `session_id`，而实际 schema 不接受顶层裸字段。

### 5. `stream.config.load` required 描述过窄

`skills/xverif/references/xdebug/action-reference.md` 写：

- `stream.config.load` required: `streams`

实际 `xdebug/schemas/v1/actions/stream.config.load.request.schema.json` 的条件 required 是四选一：

- `streams`
- `config`
- `config_path`
- `file`

影响：文档漏掉了通过 inline config、配置文件路径或 file 加载 stream 配置的合法入口。

### 6. `event.find` / `event.export` 的条件 required 未被 schema 表达

`skills/xverif/references/xdebug/action-reference.md` 写：

- `event.find` required: `expr`，also one of: `name / clock + signals`
- `event.export` required: `expr`，also one of: `name / clock + signals`

但对应 schema 的 `args.required` 只有：

- `expr`

影响：如果 runtime 确实要求 `name` 或 `clock + signals`，schema 无法提前拦截缺参；如果 runtime 不要求，则 skill 文档描述过严。这里需要以 runtime 行为或 action spec 为准再收敛。

## 已确认无明显问题的部分

- repo 内 `skills/xverif` 与安装版 `~/.codex/skills/xverif` 无 diff。
- xcov 文档中的 JSON 示例与 `xcov/xcov/schemas.py` 当前 request schema 对齐。
- MCP 文档中 `xverif_tools`、`xverif_tool_help` 名称有效，二者在 `xverif_mcp/src/xverif_mcp/server.py` 后半段有定义。
- `skills/xverif/references/mcp/overview.md` 对 batch 参数嵌套的描述与 `xverif_batch` 实现一致。

## 建议修复顺序

1. 先修正 xdebug schema metadata，尤其是 `x-arg_contract_notes`，避免生成文档继续漂移。
2. 同步更新 `skills/xverif/references/xdebug/action-reference.md` 的 required 表。
3. 更新 `skills/xverif/references/xdebug/json-api.md` 和 `recipes.md` 中缺少 `clock` 的示例。
4. 修正 `axi.analysis` 示例，删除 schema 不支持的 `time_range/max_items`，并把 `direction:"read"` 改为 `direction:"rd"`。
5. 对 `event.find` / `event.export` 做一次 runtime 行为确认，再决定是增强 schema 条件 required，还是放宽 skill 文档。

## 检查命令摘要

```bash
diff -qr skills/xverif ~/.codex/skills/xverif

python3 - <<'PY'
import json, pathlib
for p in sorted(pathlib.Path('xdebug/schemas/v1/actions').glob('*.request.schema.json')):
    data = json.load(open(p))
    args = data.get('properties', {}).get('args', {})
    print(p.name, args.get('required', []))
PY
```

## 追加评审：action 语义一致但用词不一致

本节关注“同一个语义在不同 action、schema、skill 文档里使用了不同字段名或不同描述”的问题。这里不把所有兼容 alias 都视为 bug；只记录会误导 AI 构造请求、影响 schema 校验，或增加文档维护成本的情况。

### A. 时间窗口字段命名不统一

当前存在多套表达同一时间窗口的字段：

- `time_range: {begin, end}`
- 顶层 `begin` / `end`
- 顶层 `from` / `to`
- 顶层 `start` / `end`
- `around` / `before` / `after` 类窗口

实际实现里，通用 waveform 时间窗口解析支持 `time_range.begin/end`、`time_range.from/to`、顶层 `begin/end`、顶层 `from/to`，并在未指定 `around` 时使用默认 `0ns..max`。证据在 `xdebug/src/waveform/server/service/context.cpp` 的 `json_time_range()`。

但 schema 和 skill 对同义字段的暴露不一致：

- `signal.changes` / `signal.stability` / `signal.statistics` schema 暴露 `begin/end/from/to/time_range`。
- `axi.export` schema 暴露 `begin/end/start/to/time_range`，其 contract notes 写 `time_range / start + end`。
- `stream.query` / `stream.export` / `stream.validate` schema 暴露 `begin/end/start/time_range`，没有 `from/to`。
- `list.export` schema 暴露 `begin/end/time_range`，没有 `from/to/start/to`。
- skill 文档中有时说 `begin/end`，有时说 `time_range`，有时说 `start + end`。

影响：AI 很容易把某个 action 支持的窗口字段迁移到另一个 action。例如 `start/end` 在 `axi.export` 和 stream action 中出现，但不能泛化到所有 waveform action；`from/to` 在部分 signal action 中出现，也不能泛化到 list/stream schema。

建议：

- 文档主推 `time_range: {"begin": "...", "end": "..."}` 作为所有支持窗口 action 的规范写法。
- 把 `begin/end`、`from/to`、`start/end` 明确标为 compatibility aliases，并在 action-specific schema 中尽量统一。
- `action-reference.md` 的 args contract 避免写 `start + end` 这类只覆盖单个 action 的别名，除非同一行明确说明“alias only for this action”。

### B. 结果规模限制字段命名不统一

当前 action 参数里同时出现：

- `limit`
- `max_events`
- `max_samples`
- `max_findings`
- `max_examples`
- `max_items`
- 顶层 `limits.max_items` / `limits.max_events` / `limits.max_samples`

实际 schema 分布不一致：

- 多数 waveform scan action 用 `limit`、`max_events`、`max_samples`。
- `detect_abnormal` / `handshake.inspect` / `sampled_pulse.inspect` 还用 `max_findings`。
- event config/list action 使用 `max_examples`。
- signal resolve/canonicalize 使用 `max_items`。
- `json-api.md` 的“通用限制”示例把 `max_items` 和 `max_examples` 放在 `args` 中，同时又把 `max_rows/max_events/max_samples` 放在顶层 `limits` 中。
- `recipes.md` 和 `examples.md` 中出现过把 `max_items` 传给 `axi.analysis` 或 `axi.channel_stall` 的示例；其中 `axi.analysis` schema 不接受 `max_items`，`axi.channel_stall` schema 也不接受 `max_items`，只接受 `limit/max_events/max_samples`。

影响：`max_items` 看起来像通用字段，但它并不是所有 action 的合法 args 字段。对 `additionalProperties:false` 的 action，误用会直接 schema 失败。

建议：

- 文档中把顶层 `limits` 与 action-specific `args.limit/max_*` 分开说明。
- 对 AI 推荐优先使用 action schema 中明确存在的字段；不要把 `max_items` 当通用 args 字段。
- 修正 `axi.analysis` / `axi.channel_stall` 示例中的 `max_items`，按 action schema 改为合法字段或移除。

### C. 配置对象名称字段：`name` 与 `stream` 语义重叠

多类配置对象都使用 `name`：

- APB config：`args.name`
- AXI config：`args.name`
- event config：`args.name`
- list：`args.name`
- cursor：`args.name`

stream action 同时暴露 `stream` 和 `name`：

- `stream.show` required 是 `stream`，但 schema 也有 `name`。
- `stream.validate` required 是 `stream`，但 schema 也有 `name`。
- `stream.query` required 是 `stream, query`，但 schema 也有 `name`。
- `stream.export` required 是 `stream`，但 schema 也有 `name`。

schema 描述中，`name` 的通用 description 是“已保存配置、游标、列表或接口配置名称”，而 `stream` 的 description 是“已保存 stream 配置名称”。这两者在 stream action 中语义接近，但 required contract 只承认 `stream`。

影响：AI 看到其他 config 都用 `name` 后，容易对 stream action 也传 `name`，但 required 仍要求 `stream`，会造成缺参。

建议：

- stream 文档统一主推 `stream`，并说明 `name` 若存在只是兼容/内部字段，不是 required 替代。
- 如果 runtime 支持 `name` 作为 alias，应在 schema `anyOf` 和 contract notes 中表达；如果不支持，应考虑从 stream action schema 中移除或标注 deprecated。

### D. session 标识字段：`session`、`session_id`、`id`、`name` 混用

当前存在多层 session 命名：

- 原生 xdebug request 使用 `target.session_id`。
- 原生 `session.close` / `session.kill` schema 兼容 `args.session_id` 和 `args.id`。
- MCP `xverif_debug_query` 参数名是 `session`，表示 session alias 或 session_id。
- MCP `xverif_debug_session_open` 参数名是 `name`。
- 部分 session action schema 还暴露 `args.name`，但 `session.close` / `session.kill` 的 `anyOf` 不把 `args.name` 列为 required 替代。

影响：文档中如果不明确“原生 request 用 target.session_id，MCP query 用 session”，AI 容易把 MCP 的 `session` 字段放进原生 xdebug JSON，或把原生 `target.session_id` 放到 MCP query 顶层。

建议：

- 在 xdebug skill 中固定两条规则：
  - MCP tool 参数：`xverif_debug_query(session=..., action=..., args=...)`
  - 原生 xdebug JSON：`target.session_id`
- `args.id` 只作为 legacy compatibility alias 出现在低层 schema，不作为推荐写法。
- `session.close` / `session.kill` 的 skill 推荐写法统一为 `target.session_id`。

### E. AXI/APB direction 值用词不统一

AXI schema 中 direction enum 使用缩写：

- `wr`
- `rd`
- `all`

但 skill 示例中出现了自然词：

- `direction: "read"`

APB/AXI 文档正文又常用 read/write 语义描述 transaction，这与 schema enum 的 `rd/wr` 不是同一层命名。

影响：这是语义一致但值域用词不一致的高风险问题，因为 schema enum 会直接拒绝 `read/write`。

建议：

- 用户可见解释可以继续写 read/write。
- JSON 示例和 args contract 必须使用 schema enum：`rd`、`wr`、`all`。
- 在 action-reference 或 json-api 中补一句：AXI request 参数里的 direction 使用 `rd/wr/all`，不要写 `read/write`。

### F. 导出路径字段命名不统一

导出相关 action 使用多种字段：

- `axi.export`：`output_prefix`
- `list.export`：`output_dir`、`output_file`
- `stream.export`：`output_file`
- `rc.generate`：`rc_path`
- xcov export：`args.output.path`

这些字段语义都与“输出位置”有关，但不是互换字段。

影响：AI 容易把某个 export action 的 `output_file` 泛化到另一个 export action，或把 xcov 的 `output.path` 套到 xdebug action。

建议：

- 在 xdebug 文档中按 action 明确推荐：
  - `rc.generate` 用 `rc_path`
  - `list.export` 用 `output_dir` 或 `output_file`
  - `stream.export` 用 `output_file`
  - `axi.export` 用 `output_prefix`
- 不要在文档中用笼统的 `output path` 代替具体字段名。

### G. `time`、`at`、`requested_time` 三类“目标时间”命名不统一

单点时间语义目前有三套字段：

- waveform value/verify：`time`，部分 schema 也暴露 `at`
- active driver combined action：`requested_time`
- cursor：`time`

`value.at` / `value.batch_at` / `verify.conditions` schema 中存在 `at`，但 required 仍是 `time`；`trace.active_driver` 使用 `requested_time` 而不是 `time`。

影响：AI 可能把 `requested_time` 用到普通 waveform value action，或把 `time` 用到 `trace.active_driver`。这类错误会在 schema 校验阶段失败。

建议：

- 文档中把三类时间命名固定为：
  - 单点波形读取：`time`
  - active driver 根因追踪：`requested_time`
  - 兼容 alias：`at`，不作为推荐写法
- 示例中避免使用 `at`，除非专门说明兼容字段。

### H. `include_*` 字段存在“文档泛化”风险

`json-api.md` 中的 include 示例列出了一批设计侧和波形侧 include 字段，例如：

- `include_source`
- `include_ast`
- `include_candidates`
- `include_trace`
- `include_raw`
- `include_samples`
- `include_transactions`
- `include_beats`
- `include_accesses`

但 action-specific schema 并不都接受这些字段；许多 request schema 设置了 `additionalProperties:false`。例如 `trace.driver` 只接受 `include_statement_only/include_trace/limit/no_statement_only/role/signal/time_unit`；把 `include_source` 直接传给它会被 schema 拒绝。

影响：通用 include 示例容易被误读成所有 action 都支持这些 flags。

建议：

- 把 include 示例改成“历史/能力概览”，并明确“每个 action 只能传 schema 中列出的 include 字段”。
- 对高频 action 单独给合法 include 字段，例如 `trace.driver` 只推荐 `include_trace` 和 statement-only 相关选项。

## 术语统一建议

建议将 skill 中面向 AI 的推荐字段统一为以下规范写法：

| 语义 | 推荐写法 | 兼容/非推荐写法 |
| --- | --- | --- |
| MCP 查询 session | `session` | 不要在 MCP query 顶层写 `target.session_id` |
| 原生 xdebug session | `target.session_id` | `args.session_id`、`args.id` |
| 单点波形时间 | `time` | `at` |
| active driver 时间 | `requested_time` | 不要写 `time` |
| 时间窗口 | `time_range.begin/end` | `begin/end`、`from/to`、`start/end` |
| stream 配置名 | `stream` | `name` |
| APB/AXI 配置名 | `name` | 无 |
| AXI direction | `rd/wr/all` | `read/write` |
| action 内数量限制 | 以 action schema 为准：`limit/max_events/max_samples/max_findings/max_examples/max_items` | 不要把 `max_items` 泛化为通用 args |
| 导出路径 | 按 action 使用 `rc_path/output_file/output_dir/output_prefix` | 不要泛称 `output.path` |

## 追加修复建议

1. 为 xdebug skill 增加一个“推荐字段词典”，把上表放进 `json-api.md` 或独立 reference。
2. 对所有 JSON 示例做 schema 校验，并额外检查 enum 值，例如 AXI `direction`。
3. 对 schema 中保留的兼容 alias 增加 description，例如 `at`、`id`、`name` in stream actions，明确是否推荐。
4. 对通用 include/limits 示例加警告：最终以 action-specific schema 为准。
5. 长期建议生成 `action-reference.md` 时从 schema 的真实 `required/anyOf/properties/enum` 直接生成，而不是依赖可能漂移的 `x-arg_contract_notes`。

## 最终实施计划：xdebug action 参数语义统一

### Summary

本计划把 `xdebug` action 参数从“文档修补”升级为“schema + runtime + tests + skill docs”一致性修复。目标是消除 required 漂移、同义字段混用、示例非法字段，以及 MCP/native 参数命名不一致。

实施完成后同步 repo 内 `skills/xverif` 到安装版 `~/.codex/skills/xverif`。

### Public API / Contract Changes

- `clock` 保持必填：`value.at`、`value.batch_at`、`expr.eval_at`、`list.value_at`、`verify.conditions` 的 docs、examples、`x-arg_contract_notes` 全部补齐 `clock`。
- session 全栈统一为 `session_id`：
  - native xdebug request 只推荐并要求 `target.session_id`。
  - MCP API 从 `session` 迁移为 `session_id`。
  - `session.kill` 收紧 schema，只保留 `target.session_id`。
- 时间窗口统一为 `time_range.begin/end`：
  - schema/runtime/docs 收敛，移除或废弃 `begin/end`、`from/to`、`start/end` 的对外合同。
- 数量限制统一为 `args.limit`：
  - 迁移 `max_events/max_samples/max_findings/max_examples/max_items`。
  - 示例不再把 `max_items` 当通用字段。
- stream action 统一只使用 `stream`：
  - 从 stream action schema/docs 中移除 `name`。
- AXI direction 统一为 `read/write/all`：
  - 替换当前 `rd/wr/all` enum 和 runtime 分支。
- 单点时间统一为 `time`：
  - active-driver action 从 `requested_time` 迁移到 `time`。
  - `at` 不再作为推荐或 required 字段。
- 导出路径统一为 `output.path`：
  - xdebug export/rc action 与 xcov export 对齐到 `output.path`。
  - 迁移 `output_file/output_dir/output_prefix/rc_path`。
- `include_*` 不统一成公共对象：
  - 每个 action 文档只列该 action schema 允许的 include 字段。
  - 通用 include 示例降级为能力说明，强调以 action-specific schema 为准。
- `event.find/event.export` 行为不变，但重写 schema 表达，使 `expr + (name 或 clock+signals)` 更直观。

### Implementation Changes

- 更新 xdebug request schema：
  - 修正 `x-arg_contract_notes`，从真实 `required/anyOf` 派生或机械同步。
  - 收紧/迁移上述字段枚举、required、properties、`additionalProperties:false`。
- 更新 runtime dispatch 和 action handlers：
  - 按新字段名读取参数。
  - 删除或废弃旧 alias 的对外承诺；如实现中短期保留兼容，必须返回 warning 或在 docs 明确 deprecated。
- 更新 MCP 层：
  - `xverif_debug_query(session_id=...)` 替代 `session=...`。
  - batch 示例、server instructions、tool help、tests 同步新参数名。
- 更新 skill 文档：
  - `action-reference.md`、`json-api.md`、`recipes.md`、`examples.md`、`response-fields.md` 同步新合同。
  - 增加“推荐字段词典”，固定 session、time、time_range、limit、stream、direction、output.path 等标准写法。
- 更新并保留本报告：
  - 追加最终决策摘要，标明哪些原发现已被校正，例如 `event.find/export` 的 `anyOf` 漏读。

### Test Plan

- Schema/contract：
  - `make -C xdebug schema-test`
  - `make -C xdebug contract-test`
  - 增加覆盖：required notes 与 schema `required/anyOf` 一致。
- Runtime focused probes：
  - `value.at/value.batch_at/verify.conditions` 必须带 `clock` 成功，缺 `clock` 失败。
  - `session.kill` 只接受 `target.session_id`。
  - `stream.query/show/validate/export` 只接受 `stream`，不接受 `name`。
  - AXI direction 只接受 `read/write/all`。
  - 时间窗口只接受 `time_range.begin/end`。
  - export action 只接受 `output.path`。
- MCP tests：
  - 更新 `xverif_debug_query` 参数为 `session_id`。
  - 覆盖 batch 内 nested args 示例。
- Docs/examples validation：
  - 对 `skills/xverif/references/xdebug/*.md` 中所有 `xdebug.v1` JSON 示例做 schema 校验。
  - 对 enum 值做额外校验，特别是 AXI direction。
- Skill mirror：
  - 实施后 `diff -qr skills/xverif ~/.codex/skills/xverif` 必须无差异。

### Assumptions

- 这些字段统一允许破坏旧请求兼容；若实现阶段需要临时兼容，必须标 deprecated，不作为文档推荐合同。
- 本轮不改 xcov 行为，除导出路径文档/API 对齐到 `output.path` 时需要同步 xdebug/xcov 说明。
- 所有修改必须先以 schema 为 source of truth，再同步 runtime、tests、skill docs 和安装版 skill。

## 实施决策摘要：2026-07-07

本轮按上述计划开始实施，已完成以下合同校正：

- `xdebug/specs/actions/actions.yaml` 作为 required/anyOf/conditional source of truth：
  - `trace.active_driver*` 请求字段改为 `args.time`。
  - `list.diff` 请求字段改为 `args.time_range.begin/end`。
  - `rc.generate` 请求字段改为 `args.output.path`。
  - `session.close/session.kill` 收紧到 `target.session_id`。
  - `stream.export` 的条件 required 改为 `output`。
- request schema 生成器已改为同步：
  - `args.required`、`args.anyOf`、`args.allOf`。
  - `target.session_id` required。
  - `direction` enum 为 `read/write/all`。
  - `output` 对象为 `{"path": string}` 且 `additionalProperties:false`。
- `x-arg_contract_notes` 不再依赖 action-reference 表格人工文案，而是从 spec 的 `required_args`、`required_arg_groups`、`conditional_required_args` 派生。
- `event.find/event.export` 的原始发现已修正：它们不是单纯 required `expr`，实际合同是 `expr + (name 或 clock+signals)`；schema/docs/notes 均按此表达。
- runtime 已按新字段读取关键请求：
  - active-driver 使用 `time`。
  - list/axi/stream/rc export 使用 `output.path`。
  - list diff/export 和 axi export 使用 `time_range.begin/end`。
  - AXI/APB direction 使用 `read/write/all`。
  - event find/export 和 focused waveform handlers 使用 `args.limit`。
- MCP debug query 公开参数已改为 `session_id`；debug batch instruction 和测试脚本同步为 `session_id`。
- skill 文档已增加推荐字段词典，并更新 `action-reference.md`、`json-api.md`、`recipes.md`、`examples.md`、`response-fields.md`、`rc-generate.md` 中的请求示例与字段说明。

已验证：

- `python3 xdebug/tools/validate_examples.py`：通过，145 examples。
- `python3 xdebug/tools/sync_runtime_request_schemas.py --check`：通过。
- `python3 xdebug/tools/sync_action_schema_hints.py --check`：通过。
- `python3 xdebug/tools/check_action_contract.py`：通过，71 action specs。
- `make -C xdebug schema-test`：通过。
- `make -C xdebug contract-test`：通过。
- 自定义 request schema 探针：通过，覆盖 `clock` 必填、`session.kill target.session_id`、stream `name` 拒绝、AXI `rd` 拒绝、`output_dir/requested_time` 拒绝。
- `skills/xverif/references/xdebug/*.md` 中 `api_version:"xdebug.v1"` fenced JSON 示例 schema 校验：通过，21 个示例。

当前未完成/待确认：

- `xverif_mcp/tests/test_mcp_sdk_smoke.py` 中 coverage fake lifecycle 仍失败，错误为 xcov stdio-loop transport lost；该失败发生在 `xverif_cov_query` fake session，不属于本轮 xdebug 参数合同链路，但在完整 MCP 测试报告中需要单独处理。
- 安装版 skill mirror `~/.codex/skills/xverif` 已同步；`diff -qr skills/xverif ~/.codex/skills/xverif` 无输出。
