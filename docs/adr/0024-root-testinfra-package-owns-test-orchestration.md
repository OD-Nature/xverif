---
status: accepted
---

# 由根级 testinfra package 拥有全仓测试基础设施

xverif 新增仓库根级 `testinfra/` Python package，统一拥有 pytest plugin、顶层 catalog 及 schema、fixture cache/build framework、外部 runner adapters、xdist 资源调度、execution plan 和报告生成。xdebug、xcov、xverif_mcp、xbit、xentry、xloc、xsva、xwaveform 等组件继续拥有各自测试逻辑和 fixture 定义，但不各自维护编排基础设施。

## Considered Options

- 选择：根级 testinfra package 作为全仓基础设施 owner。
- 拒绝：扩展 `xdebug/tests/runner/`；当前资产可复用，但会让其它组件从属于 xdebug 的测试实现。
- 拒绝：由 xverif_mcp 统管；MCP 只是被测组件和能力域之一，不应拥有全仓门禁。

## Consequences

- 仓库使用一份根级 pytest 配置加载 plugin 和 catalog；组件级 pytest.ini 中的公共 marker、路径和 addopts 迁移后删除。
- testinfra 不包含 xdebug/xcov 业务断言；它只表达 suite、资源、执行和报告公共合同。
- 组件可以提供 leaf runner adapter 或 fixture semantic probe，但必须通过 testinfra 注册的稳定接口被 catalog 引用。
- testinfra 自身必须有不依赖 EDA 的 unit/contract tests，并进入 fast gate。
