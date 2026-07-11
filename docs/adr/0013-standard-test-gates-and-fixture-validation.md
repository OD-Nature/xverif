---
status: accepted
---

# 定义三个测试 gate 和独立 fixture validation 门禁

xverif 对开发者公开 `fast`、`regression`、`nightly` 三个标准测试 gate，并把 `fixture-validation` 作为独立资产门禁。`fast` 只选择 static/unit/component 且禁止 EDA、NPI 和外部进程；`regression` 运行全部 required deterministic suites，可消费有效数据库缓存；`nightly` 在 regression 上增加 slow、VIP 和 optional realdata；`fixture-validation` 显式重建并验证数据库 Fixture builder，不属于普通产品测试 gate。

## Considered Options

- 选择：三个产品 gate 加一个独立资产门禁。
- 拒绝：只保留 test/full-test 两级并堆叠开关；入口少，但环境、成本和覆盖边界继续隐式变化。
- 拒绝：只提供组件自定义查询；灵活但缺少稳定的全仓交付标准。

## Consequences

- nightly 默认复用有效 fixture，不因为成本等级高就自动重新仿真。
- fixture-validation 的失败表示资产生成合同或工具环境问题，不冒充 xverif 产品断言失败。
- gate 必须由一个明确公开入口解析并输出最终选择结果，不得额外夹带 catalog 外命令；后续 ADR-0022 决定不保留 `make test`、`make full-test` 等兼容入口。
- gate 的精确查询、预算、required/optional 覆盖和 fixture-validation 触发条件由 catalog/schema 持续校验。
