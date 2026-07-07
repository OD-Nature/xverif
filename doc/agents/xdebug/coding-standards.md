# xdebug 编码要求

本页定义修改 xdebug 代码时的工程要求。原则是：schema 优先、合同稳定、输出可解析、错误可诊断、测试分层。

## API 合同

- schema 是 public contract，不从 runtime 反向猜合同。
- action 参数只能使用 schema 允许字段。
- 不引入同义字段，除非有明确迁移计划和 deprecated 说明。
- 删除或收紧字段时，同步 runtime、schema、examples、docs、skill、MCP、tests。
- 错误码是机器合同，不能只依赖 message 文本。

## JSON 处理

- 使用 nlohmann/json 和现有 request/response helper。
- 不用 ad hoc string parsing 解析 JSON。
- 不手写 JSON 字符串拼接 response。
- 字段读取要区分 missing、null、wrong type、empty value。

## 输出纪律

- 默认 compact-first。
- full/debug 只用于维护工具或排查工具本身。
- 大列表、timeline、trace、source_text 必须受 include 和 limit 控制。
- XOUT 与 JSON 输出都要保持结构稳定。

## 时间和值语义

- 时间解析复用统一 time helper。
- clock sampling 复用统一 sampling helper。
- 四态值和 bit 表示复用 `LogicValue` 等统一组件。
- 不在局部 handler 里写特殊时间单位或四态比较。

## Session 和 Transport

- public session 选择使用 `target.session_id`。
- SESSION_LOST/SESSION_TRANSPORT_FAILED 后不复用旧 session。
- transport 不静默 fallback。
- file transport 只作为显式例外路径。

## Logging

- 结构化日志必须包含 phase 和 error context。
- stdout 不输出调试噪声。
- 不记录敏感凭据。
- 环境问题要能从 lifecycle/transport/action log 追踪。

## C++ 代码风格

- 优先使用现有 helper 和 domain service。
- handler 保持薄层：读参数、调用 service、整理 response。
- 复杂逻辑下沉到可单测 helper。
- 避免跨 domain 直接依赖，例如 waveform helper 不直接承担 design trace 语义。
- 新增文件同步 Makefile source list。

## Python 工具风格

- Python 脚本优先使用 `~/miniconda3/bin/python` 运行。
- 校验脚本应支持 check 模式，避免无意修改 tracked 文件。
- 脚本输出要能被 CI/agent 清楚判断成功失败。

## 文档要求

- docs 描述当前实现，不写未实现愿景。
- public 示例必须可执行或可 schema 校验。
- 复杂行为要说明 source of truth 和测试入口。
- 修改 xdebug 架构或 action 流程时，同步本目录相关页面。

## 提交前检查

源码修改提交前：

1. `git status --short`
2. 根据影响面选择 tests。
3. 确认 schema/examples/docs/skill/MCP 是否需要同步。
4. 确认本目录说明书是否需要同步。
5. commit message 用中文写明验证结果。
