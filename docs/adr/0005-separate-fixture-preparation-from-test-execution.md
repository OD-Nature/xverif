---
status: accepted
---

# 严格分离数据库 Fixture 准备与测试执行

普通测试执行只消费通过指纹和完整性验证的数据库 Fixture，缺失或失效时明确失败并返回可执行的准备命令；它不得隐式启动 VCS、获取仿真 license 或把 required suite 静默记为 SKIP。只有显式 fixture prepare 命令或调用者显式提供的 `--prepare-missing` 才能构建缺失资产，完整门禁应先集中准备一次，再让测试 suite 复用。

## Considered Options

- 选择：准备与测试分离，隐式生成禁止，显式 opt-in 可准备缺失资产。
- 拒绝：cache miss 时自动仿真；调用成本和 license 副作用不可预测，模糊了测试边界。
- 拒绝：cache miss 时跳过；会让 required 覆盖缺失仍表现为绿色。

## Consequences

- suite 运行结果必须区分测试失败与 fixture 不可用，后者仍使 required gate 失败，但诊断层次不同。
- fixture prepare 可以串行管理 license 和共享缓存；测试执行可以在资产就绪后独立并行。
- 门禁定义必须显式列出准备阶段，不能依赖 suite 内部临时调用 `make clean run/fixture`。
- 可选外部数据 suite 是否允许 SKIP 由门禁策略单独决定，不能由测试代码自行降级。
