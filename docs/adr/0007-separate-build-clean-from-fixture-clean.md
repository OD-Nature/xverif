---
status: accepted
---

# 分离源码构建清理与数据库 Fixture 清理

源码 `make clean` 只删除源码构建和普通测试临时产物，保留 `.xverif-test-cache/`；数据库 Fixture 由独立显式操作清理，完整清理则组合源码 clean 与 fixture clean。这样 clean build 仍能验证从零编译，又不会把每次全量门禁变成重复 VCS 仿真。后续 ADR-0022/0023 将 fixture 清理的最终公开入口确定为 pytest plugin 选项，而不是 Makefile 测试入口。

## Considered Options

- 选择：源码 clean、fixture clean、完整 clean 三种职责明确的清理语义；公开命令由统一 pytest 接口收口。
- 拒绝：`make clean` 总是删除 fixture；会抵消内容寻址复用的主要收益。
- 拒绝：只依赖自动回收、不提供 fixture clean；损坏恢复和显式重建缺少可靠入口。

## Consequences

- full/regression 门禁可以执行 clean build，同时继续消费已验证的数据库 Fixture。
- 需要验证 fixture builder 本身时，门禁必须显式执行 `fixture-clean` 或指定 `--rebuild-fixtures`，不能借源码 clean 暗示重建。
- 文档和 CI 必须避免继续使用含糊的“clean test”描述，明确是 clean build 还是 fixture rebuild。
