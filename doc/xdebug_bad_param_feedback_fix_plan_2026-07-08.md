# xdebug Action 错误参数两层提示与 xverif 文档同步修复计划

## Summary

修复 70 个 xdebug action 在错误参数下的反馈质量，并同步更新 xverif Markdown 文档到最新 JSON 入口合同。按两层处理：

- Schema 层：修 JSON shape 错误，包括缺 required、类型错、未知字段、enum、oneOf/anyOf、旧字段迁移。
- Handler 语义层：修 action runtime 语义错误，包括 time/time_range、clock/signal/config/session/resource、窗口顺序、参数问题被 session 遮蔽等。

目标是：AI 调错参数时，错误响应必须直接显示正确字段路径、修正原因和一个可复制的正确请求示例；xverif skill/docs 中所有 JSON 入口说明与最新 schema/runtime 合同一致。

## Execution Bootstrap

- 第一项任务：把本计划原文写入 `doc/xdebug_bad_param_feedback_fix_plan_2026-07-08.md`。
- 第二项任务：创建 goal，objective 使用该计划书内容，后续实施以该 goal 为准。
- 进入实施后再修改源码、schema、tests、skill docs 和 mirror。

## Public Error Contract

- 所有参数错误统一返回可恢复错误，不返回 `INTERNAL_ERROR`，不静默 `OK`。
- JSON error 至少包含：
  - `code`
  - `message`
  - `recoverable:true`
  - `invalid_arg`
  - `expected`
  - `received_type` 或 `received`
  - `schema_path`，若来自 schema 层
  - `allowed_values`，若是 enum
  - `required_any_of`，若是 oneOf/anyOf 条件 required
  - `did_you_mean`，若是旧字段或常见错层级
  - `correct_example`，必须是当前 action 的最小可执行正确请求片段
- xout/message 必须同步输出：
  - 错误字段完整路径，例如 `args.limit`
  - 正确替代路径，例如 `use args.query.limit instead of args.limit`
  - 合法组合，例如 `provide args.name or args.clock + args.signals`
  - 一个正确示例，例如 `{"args":{"name":"if0","query":{"limit":10}}}`
- 旧字段继续拒绝，不兼容执行；但必须提示迁移路径和正确示例。

## Key Changes

- Schema 层：
  - 增强 `RuntimeSchemaValidator` 的错误归因：message 不再只输出 `unexpected instance type` / `additional property` / `anyOf failed`，而是合并 `invalid_arg`、`expected`、`received_type`、`allowed_values`、`did_you_mean`、`correct_example`。
  - 为 action schema 增加或生成 `x-error_hints`，覆盖常见迁移：
    - `args.limit -> args.query.limit`
    - `args.num -> args.query.index`
    - `args.name -> args.stream` for `stream.*`
    - `args.depth -> limits.max_depth`
    - `args.at -> args.time`
    - `begin/end/start/to/from -> args.time_range.begin/end`
  - 为条件 required 增加 `required_any_of` 和正确示例：
    - `event.find/export`: `args.name` 或 `args.clock + args.signals`
    - `apb/axi.config.load`: `args.config` 或 `args.config_path`
    - `stream.config.load`: `args.streams` / `args.config` / `args.config_path` / `args.file`
    - `axi.export`: `args.time_range`
    - `list.delete`: `args.signal` 或 `args.index`
  - 保持 action-specific schema 为 source of truth；生成脚本同步 hints，避免手工漂移。

- Handler 语义层：
  - 新增共享错误构造 helper，handler runtime 参数错误统一返回 `invalid_arg/expected/received_type/did_you_mean/correct_example`。
  - 修复硬错误：
    - `session.doctor target.session_id` number 返回 `INVALID_REQUEST`
    - `session.list target.session_id` number 必须拒绝
    - `window.verify` / `counter.statistics` 反向 `time_range` 必须失败
    - `axi.channel_stall` 非法 `args.channel` 不应被 `SESSION_REQUIRED` 遮蔽
  - 统一 time/time_range 错误：
    - `Invalid time 'abc'` 必须带 `invalid_arg=args.time_range.begin` 或对应字段
    - `end < begin` 必须返回稳定错误，并带 `invalid_arg=args.time_range.end`
  - 资源类错误补参数路径和示例：
    - clock not found -> `invalid_arg=args.clock`
    - signal not found -> `invalid_arg=args.signal`
    - config/list/stream not found -> `invalid_arg=args.name` 或 `args.stream`

- xout/message：
  - 扩展 `TextResponseBuilder::emit_error`，渲染 `invalid_arg`、`expected`、`received_type`、`allowed_values`、`required_any_of`、`did_you_mean`、`correct_example`。
  - 默认 xout 中必须出现一个 `correct_example` 小节；如果完整示例太长，只展示最小 args/limits/output/target 片段。
  - MCP raw/query 默认 xout 也能看到同一组修正提示。

- xverif Markdown 文档同步：
  - 全量检查并更新 `skills/xverif/**/*.md` 中的 xdebug JSON 入口说明、示例和参数字典。
  - 示例统一使用最新合同：
    - MCP query 使用 `session_id` 参数。
    - native/raw JSON 使用 `target.session_id`。
    - 时间窗口使用 `args.time_range.begin/end`。
    - APB/AXI query 使用 `args.query.index/limit`。
    - stream action 使用 `args.stream`，不使用 `name`。
    - active-driver chain 深度使用 top-level `limits.max_depth`。
    - 输出路径使用 `args.output.path`。
    - 默认不写 `output_format:"json"`，除非专门展示 JSON 字段读取。
  - 新增错误响应阅读说明：AI 调错参数时优先看 `invalid_arg`、`did_you_mean`、`required_any_of`、`correct_example`。
  - 更新 repo 内 skill 后同步到 `~/.codex/skills/xverif` 和 `~/.claude/skills/xverif`。

- 报告与架构文档：
  - 更新 `doc/xdebug_bad_param_feedback_review_2026-07-08.md`，追加修复决策和最终验证结果。
  - 更新 xdebug 架构文档，明确 schema 层和 handler 层都要提供正确示例。
  - 更新 xverif skill：AI 调错参数时优先读 `invalid_arg/did_you_mean/required_any_of/correct_example`。

## Test Plan

- Schema/contract：
  - `make -C xdebug schema-test`
  - `make -C xdebug contract-test`
  - 新增 bad-param contract 测试，覆盖 70 个 action 每个至少 2 类错误输入。
  - 测试断言：错误 response 必须有 `error.code/message/recoverable`，并按类别有 `invalid_arg/expected/correct_example`；enum 有 `allowed_values`；oneOf/anyOf 有 `required_any_of`；旧字段有 `did_you_mean`。

- Focused regression：
  - `session.doctor target.session_id=123` -> `INVALID_REQUEST`, `invalid_arg=target.session_id`, 有正确 target 示例。
  - `session.list target.session_id=123` -> `INVALID_REQUEST`, 不允许 OK。
  - `window.verify` / `counter.statistics` 反向 `time_range` -> 失败并指向 `args.time_range.end`，有正确窗口示例。
  - `event.find/export` 缺 `name` 或 `clock+signals` -> 返回 `required_any_of` 和 inline/config 两种正确示例之一。
  - `stream.config.load` 缺配置来源 -> 返回四种合法来源和最小 `streams` 示例。
  - `apb/axi.query args.limit` -> 返回 `did_you_mean=args.query.limit` 和正确 query 示例。
  - `trace.active_driver_chain args.depth` -> 返回 `did_you_mean=limits.max_depth` 和正确 limits 示例。
  - `stream.query args.name` -> 返回 `did_you_mean=args.stream` 和正确 stream query 示例。
  - `axi.channel_stall args.channel=zz` -> 参数错误优先于 session/resource 遮蔽，且有合法 channel 示例。

- Docs/examples validation：
  - `rg -n '"output_format": "json"' skills/xverif` 确认只保留专门 JSON 输出示例。
  - `rg -n '"num"|"limit"|'"'"'name"'"'"'|'"'"'depth"'"'"' skills/xverif/references/xdebug` 人工确认没有旧字段误导。
  - 抽取 `skills/xverif` 中 xdebug JSON 示例并用 action-specific schema 校验。
  - `diff -qr skills/xverif ~/.codex/skills/xverif`
  - 若 Claude mirror 存在：`diff -qr skills/xverif ~/.claude/skills/xverif`

- Runtime/full checks：
  - `make -C xdebug unit-test`
  - `make -C xdebug test-fast`
  - 沙箱外 `make -C xdebug test-regression`
  - MCP bad-param smoke：确认默认 xout 包含字段路径、修正提示和 `correct_example`。
  - `git diff --check`

## Assumptions

- 不接受旧字段兼容执行；只做拒绝并提示迁移。
- `correct_example` 是本轮新增的核心合同：所有参数错误都应尽量给出最小正确示例。
- JSON error 是机器可读 source of truth，xout/message 是 AI 默认可读层，两者必须同步表达同一修正方向。
- 本轮只修错误参数反馈和 xverif Markdown 入口说明，不改变正常 action 成功响应语义。
- 真实 NPI/VCS/FSDB/license/LSF 相关验证按仓库规则在沙箱外运行。

## Implementation Status

2026-07-08 已实施：

- 已创建 goal，并按本计划作为实施目标推进。
- 已增强 schema 层坏参提示、handler 层语义错误 enrichment、JSON/xout 错误字段透出。
- 已修复本计划列出的重点硬错误和迁移提示：`session.* target.session_id` 类型、反向 `time_range`、APB/AXI query 旧字段、stream `name`、active-driver chain `depth`、`axi.channel_stall.channel`。
- 已同步 xverif skill、xdebug 架构说明书和审计报告。
- 已补充 contract 覆盖，验证结果记录在 `doc/xdebug_bad_param_feedback_review_2026-07-08.md`。
