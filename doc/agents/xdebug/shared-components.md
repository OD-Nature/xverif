# xdebug 统一组件

本页列出 xdebug 中应该优先复用的统一组件。新增功能前先确认是否已有组件能覆盖，不要在 action handler 内临时重写一套。

## Request Envelope

路径：

- `src/api/request_envelope.*`
- `src/api/request_parser.*`
- `src/api/request_validator.*`

职责：

- 表达统一请求形状。
- 解析 JSON stdin/file。
- 提供 action、target、args、limits、output 的稳定访问入口。

要求：

- handler 不直接解析原始 stdin。
- 不要用字符串拼接方式检查 JSON 字段。

## Action Registry

路径：

- `src/api/action_registry.*`
- `src/api/action_registry_init.*`
- `src/api/action_catalog.*`
- `src/engine/service/engine_action_registry.*`

职责：

- 维护 action 名称到 handler 的映射。
- 提供 action catalog、help、contract audit 的运行时事实来源。

要求：

- action 注册必须和 `actions.yaml` 保持一致。
- 删除 action 时同步 schema、examples、docs、MCP、tests。

## Resource Resolver

路径：

- `src/api/resource_resolver.*`

职责：

- 根据 `target.daidir`、`target.fsdb`、`target.session_id` 判断资源类型。
- 为 dispatcher/engine adapter 提供资源上下文。

要求：

- 不要在各 action 中自行判断 daidir/fsdb/session 的优先级。
- public session 选择统一走 `target.session_id`。

## Response Builder 与 XOUT Renderer

路径：

- `src/api/response.*`
- `src/api/response_builder.*`
- `src/api/text_response_builder.*`
- `src/api/xout_renderer.*`
- `src/core/output/`

职责：

- 构建 JSON response。
- 渲染 compact/full/debug XOUT。
- 统一 summary、data、findings、evidence、errors 的输出形状。

要求：

- 新 response 字段必须考虑 JSON 和 XOUT 两种消费者。
- 默认输出 compact，避免返回全量 trace/timeline/source。

## Common Blocks 与 AI Response

路径：

- `src/core/ai/common_blocks.*`
- `src/core/ai/ai_response.*`

职责：

- 复用 AI 可读 summary、evidence、suggested actions、diagnostics 等块。

要求：

- 重复出现的提示、诊断和建议不要散落在多个 handler。
- 用户可见建议必须锚定事实，不输出泛泛建议。

## Runtime Schema Validator

路径：

- `src/core/schema/runtime_schema_validator.*`

职责：

- 运行时加载 action-specific schema 并校验 request。

要求：

- 禁止绕过 validator 接受 public request。
- validator 报错应保留 action、字段路径和原因。

## Logic Value 与 Time Handling

路径：

- `src/waveform/value/logic_value.*`
- `src/waveform/common/time_spec.*`
- `src/waveform/common/clock_sampling.*`
- `src/core/npi/time_contract.*`

职责：

- 统一四态值、位宽、unknown、格式化。
- 统一时间字符串、FSDB time、clock edge、sample point、time range。

要求：

- 不在 action handler 中手写四态比较或时间单位换算。
- clock sampling 行为变化必须配套 tests 和文档。

## Transport/File Exchange

路径：

- `src/core/transport/file_exchange.*`
- `src/engine/session/session_transport.*`
- `src/engine/session/client.*`

职责：

- 支持 UDS、TCP、file transport。
- file transport 管理 requests、claims、responses、done、failed、tmp、heartbeat 状态目录。

要求：

- 不让 agent 手工读写 file transport 内部目录。
- transport 切换必须显式，不做静默 fallback。

## Process Runner

路径：

- `src/core/process/process_runner.*`

职责：

- 管理子进程启动、timeout、stdout/stderr 捕获和退出状态。

要求：

- 所有外部进程调用必须保留错误上下文。
- stdout/stderr 隔离不可破坏 JSON 输出。

## Session Catalog

路径：

- `src/session/session_catalog.*`
- `src/engine/session/session_registry.*`
- `src/engine/session/session_manager.*`

职责：

- 记录 frontend/backend session 映射和生命周期。

要求：

- session close/kill/gc 必须清理 registry 和 backend 资源。
- SESSION_LOST 后不得继续复用旧 session。
