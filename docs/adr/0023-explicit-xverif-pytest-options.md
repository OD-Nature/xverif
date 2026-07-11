---
status: accepted
---

# 通过显式 xverif pytest 选项公开 gate 与资产操作

xverif pytest plugin 使用稳定的 `--xverif-*` 命令行选项表达 catalog gate、无副作用计划、fixture prepare/validation、changed-only 和诊断重跑；标准入口包括 `pytest --xverif-gate <fast|regression|nightly>`、`--xverif-plan`、`--xverif-prepare <fixture-id>`、`--xverif-fixture-validation`、`--xverif-changed <base>` 和 `--rerun-failed <report>`。pytest markers 只用于必要的测试意图或第三方兼容，不作为 gate 事实源。

## Considered Options

- 选择：显式、版本化的 xverif pytest options。
- 拒绝：只用 `-m` marker 表达式；会把 catalog 正交属性和 gate 查询复制回测试文件与命令行。
- 拒绝：多份 pytest.ini 和测试目录表示 gate；配置漂移且难以输出统一 execution plan。

## Consequences

- 无 gate/operation 的裸 `pytest` 行为必须明确，不能隐式猜测高成本门禁。
- `--xverif-plan` 与 `--collect-only` 不得准备 fixture、探测 license 或启动外部进程。
- 所有选项冲突、未知 gate、未知 fixture 和非法组合在 collection 前给出 schema 化 usage error。
- README、skills、CI 和 AGENTS.md 只使用这些公开选项，不再维护 marker/Makefile 等价命令表。
