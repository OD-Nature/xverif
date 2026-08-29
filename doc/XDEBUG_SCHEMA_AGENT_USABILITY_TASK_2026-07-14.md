# xdebug Schema Agent 可用性增强任务书

## 1. 背景与问题陈述

xdebug 已具备 action catalog、action-specific request schema、examples 和 MCP 调用入口；现有合同可以较好地拒绝顶层未知字段和检查大部分 required 参数。但是 schema 仍无法独立回答 agent 真正需要的几个问题：该 action 是否适合当前问题、MCP 调用是否应包 native envelope、可选与嵌套参数分别代表什么、默认值何时生效、条件参数怎样组合，以及响应中的主要事实应从哪里读取。

根因不只是缺少 description，而是业务字段的 source 分散在 action schema、examples、`actions.yaml`、skill reference 与同步器的裸参数模板中。同步器还会按参数名收集第一个 schema；`mode`、`query`、`rules`、`output`、`format`、`name`、`channel`、`signals` 等具有 action-specific 语义的字段因而被过宽复用。MCP discovery 目前返回完整 native envelope，也会诱导调用方把 `api_version/action/target/args` 再次嵌入 MCP 的内层 `args`。

本任务将 schema 从“验证请求是否违法”提升为“agent 单次查询即可理解并构造请求”的合同。

本任务同时以 [字段级评审报告](XDEBUG_SCHEMA_FIELD_SEMANTICS_REVIEW_2026-07-14.md) 为验收基线；下列既有问题必须在本轮 request 合同或 get-schema guide 中得到可验证处理：

| 评审编号 | 必须处理的发现 | 本轮处理位置 |
| --- | --- | --- |
| REQ-01/02/03 | session target、通用 target/limits 开放，以及 `args.limits` 与顶层 limits 冲突 | action-specific target/limits schema、MCP 投影移除 native target、trace 合同与 audit |
| REQ-04/05 | stream definition 的 alias/表达式/互依赖与 stream query 的 selector/match 未建模 | StreamDefinition、stream query 判别 schema、constraints 与 examples |
| REQ-06/07/08 | event aggregate/group_by/reset/预算、mode-line_limit 关系、export destination 不清 | event contracts、预算 completeness guide、文件/response 目的地分支 |
| REQ-09--12 | AXI/APB mapping、input source、session transport 语义不足 | protocol config/transport action contracts 和 action-specific examples |
| RSP-01--06 | 多数 response 开放、截断位置漂移、finding/evidence/统计/summary-data 边界不足 | 后续全量 response 任务以本表为基线。 |
| AXI-01--05 | AXI statistics、valid_begin_time、pairing/stall、response field dictionary 漂移 | 同步修正 skill field dictionary 的已确认路径漂移，严格 AXI schema 改动仅在生成器 source 中进行。 |

## 2. 目标与成功标准

目标：让 agent 单次调用 `xverif_debug_get_schema` 后，无需读取安装包路径、仓库 Markdown 或推断 native envelope，即可：

1. 判断某 action 的用途、适用边界、禁用边界和相邻替代 action；
2. 使用 MCP 形态构造 `xverif_debug_query(session_id, action, args, limits, output_format)`；
3. 理解所有 request business field 的类型、语义、单位、合法值、默认值、动态值规则、条件依赖和互斥关系；
4. 获得最小可执行调用、常用合法调用、典型非法调用及修正方式；
5. 知道成功响应的主要字段、时间/unknown 表示、空结果和完整性字段应如何解释。

成功标准：每个 stable action 的 request business field 在 checked-in JSON Schema 中可独立解释；默认 MCP view 可直接转交 query tool；生成物、examples、skill 文档与静态 audit 一致；正式 MCP smoke 与 schema 回归通过。

## 3. 范围、非目标与兼容边界

### 3.1 本轮范围

- 建立独立结构化 `ActionContract`，作为 stable action 的 request 字段语义、action boundary、examples 与 constraints 的 canonical source。
- 从合同生成/校验 request schema、get-schema MCP projection、action reference、catalog agent hints 和 skill MCP 示例。
- 修改 native `schema` action 的 request/response 合同；扩展 MCP `xverif_debug_get_schema`。
- 收紧全量 stable request schema；优先实现 `stream.query/config.load`、`event.find/export`、`handshake.inspect`、`detect_abnormal`、`signal.changes`、协议 config、session transport 和 trace limits 的嵌套/条件语义。
- 新增 schema quality audit 与 MCP contract test，验证业务描述、object/array shape、conditional schema、MCP projection 和 examples。

### 3.2 非目标

- 不在本轮把全部 stable action response JSON Schema 改造成闭合业务模型；仅为 schema discovery action 建立严格 response。
- 不增加新的 xdebug query action、运行时 fallback、transport fallback、输入源优先级或静默 alias 兼容。
- 不改变已经确认的 action handler 业务语义；发现 schema 与 handler 不一致时，先以测试和明确错误收紧，不能在 schema 中猜测行为。

### 3.3 兼容规则

- `xverif_debug_get_schema` 默认使用 `view="mcp"`，只提供 MCP 调用投影。
- 原生 CLI/stdio 的 `schema` action 仍返回 native schema；MCP projection 只发生在 MCP server/adaptor 层。
- 不接受后静默忽略参数。多输入源只有在 handler 已实现且合同明确的情况下才可共存；否则 request schema 使用 `oneOf` 拒绝混用。

## 4. Canonical ActionContract 模型

`xdebug/specs/action_contracts.py`（或等价的结构化 source）必须以 action 名为一级 key；不能以裸参数名作为业务 schema truth。每个 action contract 包含：

| 区块 | 必须信息 |
| --- | --- |
| identity | action、资源需求、MCP 是否需要 session、请求与响应 schema kind |
| selection | `purpose`、`use_when`、`do_not_use_when`、`alternatives[{action,when}]` |
| arguments | action-specific args/limits schema、双语 description、default、effective default、recommended value、单位、表达式/路径语法、dynamic contract |
| constraints | 从 JSON Schema 条件展开的自然语言规则；包括 required group、互斥、条件必填、预算作用域、输入源选择和错误恢复提示 |
| examples | minimal MCP call、common legal calls、invalid call + corrected call；示例是内嵌 JSON，不是仓库路径 |

真正跨 action 同义的时间、采样、signal path、line limit、logic value 等才能抽成 reusable `$defs`；即使字段同名，只要语义不同，必须在 ActionContract 中有 action-specific override。

## 5. Request schema 增强要求

### 5.1 通用质量规则

1. 每个 business leaf property 有 `description` 和 `x-description-zh`；envelope metadata 例外应由 audit 显式白名单管理。
2. 每个业务 object 说明组合语义并使用 `additionalProperties:false`。仅 alias map、field-filter map 等动态对象可用 schema-valued `additionalProperties`，且必须有非空 `x-dynamic-contract` 描述键、值、表达式/匹配规则。
3. 每个 array 必须有 `items`；enum 必须解释整体语义，复杂 enum 需 enum-value description 或 constraints。
4. schema `default` 仅表示真实运行时默认；推荐值只写 `x-recommended`。依赖其他字段的默认以 `x-default-rules` 与 agent-readable constraints 同时发布。
5. 所有时间字段明确 canonical 带单位字符串、裸数字与 `time_unit` 的优先级、窗口闭区间、单端范围和 begin>end 的语义错误。
6. `line_limit` 明确只裁剪 response/XOUT evidence；`max_samples`、`max_events` 等扫描/文件预算必须说明耗尽后的 completeness 影响。

### 5.2 重点复杂合同

- `detect_abnormal.checks[]` 采用判别 `oneOf`：`unknown_xz` 只有 type；`glitch` 必填 `min_pulse_width`；`stuck` 必填 `min_duration`；每项说明检查区间和时间格式。
- `stream.query.query` 明确 string selector 与 object selector 的枚举；`match` 对 range 强制 lo/hi、比较强制 value，mask 明确公式/输入 literal，`field_scope/channel/packet_index` 明确作用域和互斥关系。
- `stream.config.load` 用一个 reusable StreamDefinition 供 inline/config 路径复用；说明 alias、路径、表达式、reset 极性、rdy/bp、SOP/EOP、field map、channel_id 与 interleaving 的依赖。
- `event.find/export` 闭合 aggregate/group_by，说明 mode、events、rst_n、scan/file/response budget；`line_limit` 仅 mode=all；export 必须明确 response-only 与 file 输出分支。
- `handshake.inspect.rules` 分别说明 wait 起算点、data-stable 的 data 前提、valid-hold 的违规定义、ready-without-valid 三种返回粒度。
- APB/AXI config 为每个 waveform mapping 发布协议角色、方向、采样语义及 reset/valid-ready 约束；config/config_path 等来源明确互斥或 source policy。
- session transport 使用 transport discriminator：TCP host/port 范围、UDS socket path、file 输入以及禁止组合都在 schema 表达。

## 6. get_schema 与 native schema action 接口

### 6.1 MCP 公共接口

扩展为：

```python
xverif_debug_get_schema(
    action: str,
    kind: str = "request",
    view: str = "mcp",
    include_examples: bool = True,
    language: str = "zh",
)
```

`kind` 为 `request|response`。`view` 为：

| view | 行为 |
| --- | --- |
| `mcp`（默认） | 返回适用于 `xverif_debug_query` 的 args/limits schema、完整 agent guide 和 examples；不含 native target/envelope。 |
| `args` | 只返回 action-specific args schema、constraints、parameter guide 和 examples。 |
| `native` | 返回当前 CLI/stdio 完整 request/response JSON Schema。 |
| `response` | 返回 response schema；当 kind 不是 response 时返回 `INVALID_ARGUMENT`。 |

`include_examples=false` 仍返回 minimal call，只隐藏 invalid examples。未知 action、未知 kind/view、kind-view 冲突必须返回稳定 `INVALID_ARGUMENT` 或 `UNKNOWN_ACTION`，并带 suggested action/correct example。

### 6.2 默认 MCP 返回形态

```json
{
  "action": "value.at",
  "kind": "request",
  "view": "mcp",
  "call_with": "xverif_debug_query",
  "purpose_en": "Read one signal value at a sampled waveform time.",
  "purpose_zh": "读取单个信号在指定采样时间的值。",
  "use_when": ["需要一个最终叶子信号在单一采样时刻的值。"],
  "do_not_use_when": ["需要原始值变化时间线。"],
  "alternatives": [{"action": "signal.changes", "when": "需要每次原始值变化。"}],
  "required_session": true,
  "fixed_arguments": {"action": "value.at"},
  "args_schema": {},
  "limits_schema": {},
  "constraints": [],
  "minimal_call": {},
  "invalid_examples": []
}
```

`args_schema` 与 `limits_schema` 是字段语义、类型、enum、default、required 和嵌套结构的唯一来源。`constraints` 只保留 JSON Schema 之外的跨字段业务语义。

### 6.3 原生 schema action

`schema.request.schema.json` 的 `args.action` 必填；`args.kind` enum 为 request/response，default request；native response 明确 `summary.action/kind`、`data.schema/schema_path`、examples 和 constraints 的结构。native action 保留从 checked-in schema 文件读取的职责，不承担 MCP wrapper 层的投影。

## 7. 生成链路、文档与质量审计

生成链路必须单向：ActionContract -> request schemas / MCP projection / action reference / catalog agent hints / skill examples。`actions.yaml` 只提供目录与注册元数据；schema 生成器不能再从任意 action 的现有同名 property 复制业务定义。

新增静态 audit，失败信息必须定位 action 与 JSON path。规则至少包括：

1. stable action contract、request schema、catalog 和 minimal MCP example 完整对应；
2. business leaf description、array items、object closure/dynamic contract、enum/default/conditional explanation 完整；
3. `args_schema`/`limits_schema` 覆盖每个业务路径；
4. MCP `args_schema` 与 native schema 的 `properties.args` 完全等价，limits 同理；
5. use/do-not-use 不能使用泛化模板；除明确无替代 action 外，至少有一个 alternatives 条目；
6. 内嵌 minimal/invalid examples 通过 schema validator，invalid example 必须被拒绝。

同步更新 action reference、MCP surface、generated examples、skill metadata 与项目 xdebug 架构说明；不保留只能靠仓库路径访问的 example 合同。

## 8. 验证矩阵

| 层级 | 验证 |
| --- | --- |
| 生成 | `sync_runtime_request_schemas.py --check`、`sync_action_schema_hints.py --check`、metadata/reference 生成 check |
| 静态 | schema validator、examples validator、ActionContract quality audit、现有 `xdebug.static` suite |
| 条件 schema | validator 扩展覆盖 `const`、`if/then/else`、判别 oneOf；每个复杂 action 具备合法和非法 fixture |
| MCP wrapper | default mcp/native/args/response views、examples 开关、语言切换、错误输入、projection 等价性、native envelope 不嵌套 |
| 运行时合同 | action catalog/schema/runtime contract；涉及真实 FSDB/NPI/MCP stdio 的 suite 整体在沙箱外运行 |
| skill | Markdown 链接、可复制 JSON、action/tool 覆盖、附属脚本和 repo/install mirror 差异检查 |

## 9. Git 交付边界

提交前运行 `git status --short`，只暂存本任务的 ActionContract、生成器、schema、examples、MCP adapter/server、测试、skill、架构说明和任务书；不得包含已有无关改动。commit message 使用中文并说明动机、公开合同变化、生成物和验证。提交后将当前目标分支推送远端，报告 commit id、分支和推送结果。

## 10. 2026-07-15 全量收口补充

- request runtime 使用 embedded third-party Draft-7 validator。checked-in JSON 文件仍声明 Draft 2020-12，但 72 个 request schema 只能使用已验证的 Draft-7 兼容子集；不得引入 `$dynamicRef`、`unevaluatedProperties`、`prefixItems`、`dependentSchemas` 等后期关键字。此约束由独立 audit 与真实 C++ validator 共同验证，不生成第二份 schema 或静默降级。
- `get_schema(view="mcp")` 返回 request parameter guide；`kind="response"` 不再隐式改写为 response view。
- response compact 主路径从 canonical basic example 生成闭合 `summary/data/meta` 结构；无法在 compact example 中稳定枚举的诊断 payload 必须保留为带 `x-dynamic-contract` 的显式扩展点，而非裸开放 object。
