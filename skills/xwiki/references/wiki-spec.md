# xwiki Wiki Spec

xwiki wiki 是芯片验证项目的持久 LLM 记忆。根目录来自 `XWIKI_DIR`。

## Required Structure

- `index.md`：正向总索引，按验证主题列出页面，必须有 YAML frontmatter，默认 `object_type: dv`。
- `log.md`：时间顺序记录 ingest/query/lint/update/deprecate，必须有 YAML frontmatter，默认 `object_type: dv_issue`。
- `wiki/` 或根级 topic 页面：DUT、接口、workflow、testbench、sequence、checker、coverage、debug 等 concept。
- `archive/` 或 `deprecated/`：废弃页面存放区。
- `_index/backlinks.md`：可选反向索引，也必须有 YAML frontmatter。
- `_index/tags.md`：可选 tag 索引，也必须有 YAML frontmatter。

## Markdown Frontmatter

所有 Markdown 文件都必须以 YAML frontmatter 开头：

```yaml
---
type: Verification Topic
title: Block Interfaces
description: One-sentence summary used by index and agents.
object_type: de
tags: [interface, dut]
source_refs:
  - rtl/top.sv:10-80
updated_at: 2026-06-29
---
```

必填字段：

- `type`
- `title`
- `description`
- `object_type`

`object_type` 只能使用：

- `de`：设计实现、RTL、接口、微架构、协议行为、设计参数和数据路径。
- `dv`：验证环境、sequence、checker、scoreboard、coverage、test、debug workflow 和仿真入口。
- `de_issue`：持续记录设计、RTL、spec、协议定义、性能需求或微架构侧问题和风险。
- `dv_issue`：持续记录验证环境、RM、checker、scoreboard、sequence、testbench、脚本、配置或 DV 假设侧问题和风险。

推荐字段：

- `tags`
- `source_refs`
- `updated_at`
- `confidence`

## Links

- 使用相对 Markdown 链接。
- 禁止 `file://`。
- 禁止本机绝对路径链接，例如 `/home/...` 或 `/tmp/...`。
- 新页面必须从 `index.md` 或相关 topic 页面可达。
- 修改、移动、废弃页面后必须维护入链和出链。

## Log

`log.md` 的二级标题必须使用：

- `## YYYY-MM-DD`
- `## [YYYY-MM-DD] ingest | Title`

条目应说明 action、来源、更新页面、unknowns。

## Deprecated Pages

不允许硬删除页面。废弃页面应移动到 `archive/` 或 `deprecated/`，并在 frontmatter 中包含：

```yaml
deprecated: true
deprecated_reason: Replaced by wiki/interfaces/apb.md
```
