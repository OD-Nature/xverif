---
status: accepted
---

# 正式测试 gate 不自动重试失败 suite

xverif 的 fast、regression、nightly 和 fixture-validation 均以首次执行结果作为 gate 结论，不自动重试，也不允许重跑成功覆盖首次失败。pytest plugin 提供显式 `--rerun-failed <report>` 诊断入口，复用原报告中的 suite 集合、seed、fixture 指纹和可复现环境摘要，并生成独立关联报告。

## Considered Options

- 选择：无自动 retry，显式诊断重跑且不改写原结果。
- 拒绝：失败自动重试一次并允许 gate 通过；可能掩盖资源泄漏、竞态和 session 清理缺陷。
- 拒绝：suite 自定义 retry 次数；结果语义不一致，也会鼓励把不稳定性配置化隐藏。

## Consequences

- 每次执行和诊断重跑都有独立 run identity；报告用父子关系关联，但结果不可合并成一次通过。
- suite 必须声明或继承 timeout，卡死不能用 retry 作为恢复策略。
- flaky 判定来自跨 run 的历史分析，不来自单次 gate 内自动重试。
- 调试命令必须保持 seed 和 fixture identity；无法复现环境差异时要明确报告，不能静默换 backend 或数据源。
