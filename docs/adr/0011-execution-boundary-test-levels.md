---
status: accepted
---

# 按执行边界定义测试层级并把 contract 作为测试意图

xverif 的测试层级固定为 `static`、`unit`、`component`、`integration`、`system`，表示被测边界和跨进程/组件程度；`contract` 不再是层级，而是可附着在多个层级上的测试意图。这样 schema/example 检查、CLI runtime 合同和 MCP protocol 合同可以共享 `intent: contract`，同时保留完全不同的执行边界与环境成本。

## Considered Options

- 选择：五个执行边界层级，加独立 contract 意图。
- 拒绝：把 contract 保留为层级；会继续混合静态检查、CLI 进程和 MCP 系统链路。
- 拒绝：只保留 unit/integration/e2e；过于粗糙，无法为 xverif 的 component engine 和异构系统门禁提供稳定边界。

## Consequences

- catalog 的 `level` 是单值枚举；`intent` 是可多值标签集合。
- `static` 不启动被测二进制或外部服务；`unit` 隔离单元；`component` 运行一个主要组件；`integration` 验证多个仓库组件协作；`system` 覆盖对外入口到真实或等价 backend 的完整链路。
- 现有 `contract` pytest marker 需要拆成 level 与 intent，不能机械一对一迁移。
- gate 可以按执行边界控制并行、环境和预算，也可以按 intent 要求合同覆盖。
