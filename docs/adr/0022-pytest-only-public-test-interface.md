---
status: accepted
---

# 迁移完成后只保留 pytest 公开测试入口

全量迁移完成后删除顶层和各组件 Makefile 中的所有公开测试 target；开发者、自动化调用者和 agent 直接使用仓库 pytest plugin 的稳定命令行合同。Makefile 不保留测试薄别名、历史 target 兼容层或失败时转调旧脚本的 fallback，README、skill 和 AGENTS.md 同步只描述 pytest 入口。fixture builder 所需的内部 leaf target 可以保留，但不承担 suite 选择、gate、结果判定或公开入口职责。

## Considered Options

- 选择：删除所有 Makefile 测试 target，只公开 pytest plugin。
- 拒绝：保留少量常用 Make 薄别名；使用方便，但仍形成第二组需要维护和解释的入口名称。
- 拒绝：保留全部历史 target 作为别名；兼容面最大，也最容易让过期组合长期存在。

## Consequences

- leaf Makefile 可以继续服务 fixture builder 的内部实现，但不能作为用户测试入口或自行选择/汇总 suite；plugin 通过 catalog runner adapter 调用必要 leaf 命令。
- 迁移提交必须同步删除 Makefile `.PHONY` 测试项、README 命令、skills 示例、CI 调用和 agent 文档中的旧入口。
- 不提供旧命令 fallback；调用已删除 target 应明确失败，迁移说明给出唯一 pytest 等价命令。
- 源码 build/clean/install 等非测试 Make target 不受影响。
