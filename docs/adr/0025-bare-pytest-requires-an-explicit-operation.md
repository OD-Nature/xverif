---
status: accepted
---

# 裸 pytest 必须要求显式 xverif gate 或操作

在仓库根目录运行未携带 `--xverif-gate`、plan、prepare、fixture-validation 或诊断重跑操作的裸 `pytest` 时，plugin 在 collection 前返回清晰 usage error，并列出合法命令。它不默认运行 fast、regression 或其它测试集合，避免调用者把默认子集误认为完整测试，或无意触发高成本环境动作。

## Considered Options

- 选择：裸 pytest 拒绝执行并要求显式操作。
- 拒绝：默认 fast；便捷但容易被误认为全仓通过。
- 拒绝：默认 regression；语义较完整，但在普通环境中可能意外启动 NPI/MCP 和大量外部进程。

## Consequences

- CI、README、skills、agent 规则和开发脚本必须始终写出明确 gate/operation。
- usage error 在任何 fixture prepare、license probe、外部进程或 test collection 副作用之前发生。
- plugin 帮助文本是公开入口索引，必须从 catalog/gate schema 生成或校验，防止文档漂移。
