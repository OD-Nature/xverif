---
status: accepted
---

# 使用顶层单一 YAML 测试清单并进行 schema 校验

xverif 使用一份顶层 YAML catalog 集中登记所有稳定 suite，并用版本化 schema 严格校验字段、枚举和引用；fixture 特有的信号映射、预期事务和资源路径继续保存在 suite 附近的 manifest，由 catalog 以显式引用连接。Python orchestrator 是 catalog 的消费者，Makefile 和其它入口不得复制 suite 文件列表或门禁选择逻辑。

## Considered Options

- 选择：顶层单一 YAML catalog，加严格 schema 校验。
- 拒绝：分布式 suite manifest 自动发现；局部维护方便，但难以一次审查完整覆盖、重复项和门禁归属，且发现规则会成为另一套隐式事实源。
- 拒绝：Python 代码 registry；类型表达强，但容易把选择逻辑和副作用混进声明层，diff 也不如数据清单直接。

## Consequences

- catalog 只保存 suite 身份、正交分类、runner、fixture 引用、成本和门禁所需元数据，不吸收 fixture 业务细节。
- catalog schema 自身必须有 validation test；未知字段、重复 suite ID、失效引用和非法枚举直接失败。
- 所有门禁先从 catalog 解析为可审查 execution plan，再执行 runner。
- fixture manifest 可以继续使用适合局部数据的 YAML 或 JSON，但必须由统一 loader 校验引用和版本。
