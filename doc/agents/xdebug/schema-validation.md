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
- 数量限制：`args.limit` 或 action-specific schema 明确允许的字段。
- stream 名称：`args.stream`
- AXI direction：`read/write/all`
- 导出路径：`output.path`

## Response Schema 要求

每个 public action 必须有 response schema。

要求：

- 覆盖 compact/default response 的稳定字段。
- 错误响应字段稳定。
- summary/data/findings/evidence 的类型明确。
- 新增字段后同步 example。

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
make -C xdebug schema-test
make -C xdebug contract-test
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
