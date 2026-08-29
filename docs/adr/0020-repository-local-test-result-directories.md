---
status: accepted
---

# 将测试报告与日志保存到仓库本地独立结果目录

xverif 每次测试运行将终端摘要以外的 JUnit、版本化 JSON、suite stdout/stderr 和附加 artifact 写入 `.xverif-test-results/<run-id>/`；该根目录加入版本控制忽略，并与 `.xverif-test-cache/` 数据库输入资产严格分离。pytest 终端输出始终给出当前 run 目录，CI 可以原样上传该目录。

## Considered Options

- 选择：仓库本地独立 results 根目录。
- 拒绝：只写 `<repo>/tmp`；难以定位、保留和关联提交，清理行为也依赖宿主机。
- 拒绝：与 fixture cache 共用根目录；输入资产和运行证据的不可变性、保留与清理策略不同。

## Consequences

- run 目录在执行开始时原子创建，完成后写最终状态；并行 worker 只能写各自 suite 子目录或由 controller 汇总。
- 提供独立 `results-clean`，不得由源码 `make clean` 或 `fixture-clean` 隐式删除。
- 默认保留策略必须按成功/失败、容量和时间明确配置；活动运行和被诊断重跑引用的父报告不得回收。
- 报告内使用相对 artifact 路径，使整个 run 目录可移动和上传。
