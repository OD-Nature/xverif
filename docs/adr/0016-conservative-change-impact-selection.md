---
status: accepted
---

# 只在本地与快速预检中使用保守的变更影响选择

xverif catalog 显式记录 suite 的 source ownership、fixture fingerprint inputs、依赖关系和全局触发路径，pytest plugin 可以据 Git diff 为本地开发与快速预检选择受影响 suite。正式 `regression` 和 `nightly` 始终执行各自完整 catalog 查询，不使用 changed-only 裁剪；无法证明影响范围的变更按规则扩大到完整快速集或 regression，而不是猜测性少跑。

## Considered Options

- 选择：changed-only 仅用于非最终门禁，采用保守扩大语义。
- 拒绝：完全不做影响选择；最稳妥但放弃本地反馈速度优化。
- 拒绝：所有 gate 都按影响裁剪；依赖图遗漏会直接造成正式回归漏测。

## Consequences

- impact mapping 是 catalog schema 的受校验部分，未知路径和全局基础设施路径必须有明确扩大规则。
- changed-only 的 execution plan 必须展示每个 suite 被选择或排除的理由。
- regression/nightly 结果不得标记为完整通过，除非实际执行了完整 gate 查询集。
- fixture 生成输入变化同时选择对应 fixture-validation 与消费该 fixture 的测试 suite。
