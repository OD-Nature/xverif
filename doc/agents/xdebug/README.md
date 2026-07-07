# xdebug 代码架构说明书

本目录是 xdebug 的外部维护材料，面向需要修改 xdebug 代码、schema、action、session、transport、log、MCP 适配或测试体系的 agent 和工程师。

## 阅读顺序

1. [architecture.md](architecture.md)：先建立分层视图。
2. [action-development.md](action-development.md)：添加或修改 action 前必读。
3. [schema-validation.md](schema-validation.md)：任何 public contract 变化前必读。
4. [sessions.md](sessions.md)、[protocols.md](protocols.md)、[logging.md](logging.md)：涉及 session、通信、排障时必读。
5. [shared-components.md](shared-components.md)：复用统一组件前必读。
6. [coding-standards.md](coding-standards.md)、[tests.md](tests.md)：编码和提交流程检查。

## 适用场景

- 新增、删除、重命名或修改 xdebug action。
- 修改 request/response schema、examples、`actions.yaml` 或 action contract notes。
- 修改 frontend dispatcher、engine service、design/waveform/combined handler。
- 修改 session 生命周期、transport、stdio-loop、MCP/SDK-free wrapper 行为。
- 修改 log、error code、XOUT/JSON 输出形状。
- 诊断 schema、runtime、docs 或 skill 之间的一致性问题。

## 维护规则

- 代码结构变化后，同步更新本目录相关页面和 [log.md](log.md)。
- 添加或修改 action 时，至少检查 [action-development.md](action-development.md)、[schema-validation.md](schema-validation.md)、[tests.md](tests.md)。
- 修复环境误判时，简要追加根目录 `AGENTS.md`；如果误判涉及 xdebug 架构、session、transport、log 或测试体系，也更新本目录相关页面。
- 本目录描述 repo 内当前实现，不作为愿景文档。未来计划应放在独立 plan/report 文件，确认实现后再合并进本说明书。

## 文件索引

- [architecture.md](architecture.md)：架构分层和主要代码路径。
- [action-development.md](action-development.md)：新增/修改 action 的完整流程。
- [shared-components.md](shared-components.md)：统一组件和复用边界。
- [protocols.md](protocols.md)：JSON、stdio-loop、engine、transport、MCP/SDK-free 协议。
- [logging.md](logging.md)：日志系统、路径、字段和排障顺序。
- [sessions.md](sessions.md)：session 系统、生命周期和错误处理。
- [schema-validation.md](schema-validation.md)：schema source of truth 和校验链路。
- [coding-standards.md](coding-standards.md)：编码要求。
- [tests.md](tests.md)：测试矩阵和提交前要求。
- [log.md](log.md)：维护日志。
