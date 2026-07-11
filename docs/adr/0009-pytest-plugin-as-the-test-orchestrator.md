---
status: accepted
---

# 以 pytest plugin 作为统一测试编排入口

xverif 使用仓库自有 pytest plugin 读取顶层 YAML catalog、解析门禁查询、准备 execution plan，并通过 pytest 的 collection、selection、execution 和 reporting 协议统一运行测试。pytest 是公开编排入口和结果协议，YAML catalog 仍是 suite 身份与属性的唯一事实源；后续 ADR-0022 进一步决定迁移后删除所有 Makefile 测试 target，不保留薄别名。

## Considered Options

- 选择：pytest plugin 统一编排 Python 与非 Python suite。
- 拒绝：独立 `tools/xverif-test` CLI；更自然地覆盖异构 runner，但会形成 pytest 之外的另一套用户入口。
- 拒绝：Makefile 作为主要编排器；难以提供一致 collection、selection、结构化报告和 fixture 生命周期。

## Consequences

- plugin 必须把 C++、shell、Make/VCS、MCP 和真实数据 runner 映射为可独立收集、执行和报告的 pytest item，不能只覆盖 Python tests。
- `pytest --collect-only` 和计划模式必须能在不启动 NPI/VCS/VIP/license/外部进程的条件下展示选中 suite 及原因。
- plugin 不得把测试执行和 fixture prepare 混在普通 collection 中；显式 prepare 仍是独立动作或显式选项。
- 需要定义稳定的外部 suite item、日志、超时、退出码、SKIP/ERROR/FAIL 和中断清理合同。
