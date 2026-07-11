# xdebug Schema 与合同校验

xdebug public API 以 action-specific schema 为 source of truth。任何文档、skill、runtime、MCP wrapper 都必须服从 schema。

## Source of Truth

核心文件：

- `xdebug/specs/actions/actions.yaml`
- `xdebug/schemas/v1/actions/*.request.schema.json`
- `xdebug/schemas/v1/actions/*.response.schema.json`
- `xdebug/examples/requests/*.json`
- `xdebug/examples/responses/*.json`

辅助生成/校验：

- `xdebug/tools/sync_runtime_request_schemas.py`
- `xdebug/tools/sync_action_schema_hints.py`
- `xdebug/tools/validate_schema.py`
- `xdebug/tools/validate_examples.py`
- `xdebug/tools/audit_action_schema_coverage.py`
- `xdebug/tools/check_action_contract.py`

## Request Schema 要求

每个 public action 必须有独立 request schema。

要求：

- `action` enum 只包含该 action。
- `target`、`args`、`limits`、`output` 的字段边界清晰。
- required/anyOf 表达真实必填语义。
- enum 与 runtime 分支一致。
- 默认 `additionalProperties:false`。
- 合同字段不使用多个同义别名。

常见标准字段：

- session：`target.session_id`
- 单点时间：`args.time`
- 时间窗口：`args.time_range.begin/end`
- 数量限制：以 action-specific schema 为准。通用窗口/统计常用 `args.line_limit`；APB/AXI query 使用 `args.query.line_limit` / `args.query.index`；active-driver 链深度使用 top-level `limits.max_depth`。
- stream 名称：`args.stream`
- AXI/APB direction：以 action-specific schema 为准；query action 当前只接受 `read/write`，cursor/analysis 等 action 可按各自 schema 接受 `all`。
- 导出路径：`output.path`

特殊收紧合同：

- `list.export` 输入格式只允许 `args.format:"u64bin"`；manifest/response 可使用版本化 `u64bin.v1`。
- `stream.export.args.kind` 只允许 `transfer`、`packet`、`packet_beats`，不能写 `beats`。
- `apb.query` / `axi.query` 不接受旧 `args.num`、`args.limit` 或猜测的顶层数量字段。

## Response Schema 要求

每个 public action 必须有 response schema。

要求：

- 覆盖 compact/default response 的稳定字段。
- 错误响应字段稳定。
- summary/data/findings/evidence 的类型明确。
- 新增字段后同步 example。

## 参数错误提示合同

xdebug 参数错误有两层：

- schema 层：request schema 校验失败，包括 missing required、wrong type、bad enum、additionalProperties、anyOf/oneOf 不满足。
- action handler 层：schema 已通过但运行语义非法，包括反向 time_range、不存在的 signal/config、handler 内部枚举、time parse 失败等。

两层都应尽量返回可恢复字段，并让 JSON 和 XOUT 都能看到：

- `invalid_arg`：错误字段路径。
- `expected`：期望类型、范围或语义。
- `received_type`：实际 JSON 类型。
- `allowed_values`：合法 enum。
- `did_you_mean`：常见错字段的正确字段路径。
- `required_any_of`：至少提供其中一组参数。
- `correct_example`：最小正确请求模板。

新增或修改 action 时，如果发现 AI 容易把参数写错，应优先通过 action-specific schema、handler 语义错误 enrichment 和 `correct_example` 修复，而不是在文档里继续保留旧 alias。

## actions.yaml 同步

`actions.yaml` 中的 `required_args`、schema 路径、example 路径、requires、handler_kind 必须和 runtime 一致。

修改后运行：

```bash
~/miniconda3/bin/python xdebug/tools/sync_runtime_request_schemas.py
~/miniconda3/bin/python xdebug/tools/sync_action_schema_hints.py
```

检查模式：

```bash
~/miniconda3/bin/python xdebug/tools/sync_runtime_request_schemas.py --check
~/miniconda3/bin/python xdebug/tools/sync_action_schema_hints.py --check
```

## 基础校验

```bash
pytest --xverif-gate fast --xverif-suite xdebug.static
pytest --xverif-gate regression --xverif-suite xdebug.action_runtime_catalog
```

`schema-test` 覆盖 schema 文件和 examples。

`contract-test` 覆盖 action inventory、runtime action 输出、schema coverage、clock sampling static guard 等。

## Docs/Skill 校验

修改 skill 或 docs 中的 JSON 示例后，应抽取 Markdown fenced JSON，并用 action-specific schema 校验。

要求：

- JSON 示例必须带 `api_version` 和 `action`。
- 示例字段必须被对应 schema 接受。
- enum 值必须合法。
- docs 中不保留旧 alias 作为推荐字段。

## Runtime 校验

runtime 不应接受 schema 明确禁止的 public 字段。若短期保留旧 alias：

- 必须标 deprecated。
- 不得作为文档推荐合同。
- 必须有测试覆盖 warning 或兼容边界。

## 常见漂移

- docs 写 required，schema 未 required。
- schema required，example 缺字段。
- runtime 接受 alias，docs 推荐 alias。
- MCP wrapper 参数名与 native xdebug target/args 不一致。
- `x-arg_contract_notes` 与 required/anyOf 不一致。
- 通用 include 示例列出 action schema 不支持的字段。
