# xberif Wiki Spec

xberif wiki 是芯片验证项目的持久 LLM 记忆。根目录来自 `XBERIF_WIKI_DIR`。

## Required Structure

- `index.md`：正向总索引，按验证主题列出页面。
- `log.md`：时间顺序记录 ingest/query/lint/update/deprecate。
- `wiki/` 或根级 topic 页面：DUT、接口、workflow、testbench、sequence、checker、coverage、debug 等 concept。
- `archive/` 或 `deprecated/`：废弃页面存放区。
- `_index/backlinks.md`：可选反向索引。
- `_index/tags.md`：可选 tag 索引。

## Concept Page

普通 concept 文件是 Markdown，必须以 YAML frontmatter 开头：

```yaml
---
type: Verification Topic
title: Block Interfaces
description: One-sentence summary used by index and agents.
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
