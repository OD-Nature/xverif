---
status: accepted
---

# 以生成输入变更驱动 Fixture 重建并周期性全量验证

`fixture-validation` 根据 catalog 中声明的 fingerprint inputs 只重建受 RTL/TB/filelist、生成脚本、关键工具选项或 fixture schema 变化影响的数据库 Fixture，并设置周期性全量重建作为环境漂移兜底。新资产必须在隔离 staging 目录生成，完整性与语义探针通过后原子发布到 `.xverif-test-cache/`，失败生成不得覆盖最后一份有效资产。

## Considered Options

- 选择：变更驱动的增量重建，加周期性全量验证。
- 拒绝：每次 nightly 重建全部 fixture；重复消耗时间与 license，混淆产品测试和仿真准备。
- 拒绝：只允许人工触发；容易让生成合同长期腐化而不被发现。

## Consequences

- catalog 必须为每个可生成 fixture 声明完整 fingerprint inputs，变更检测不能只依赖目录或 mtime。
- 周期性全量 fixture-validation 的频率由 CI 计划定义，不改变普通 nightly 的复用合同。
- 原子发布前至少验证 manifest、指纹、FSDB 可读性、daidir 完整性和 fixture-specific semantic probe。
- 同一指纹的并发 prepare 必须去重并加锁，其他消费者继续读取已发布的不可变资产。
