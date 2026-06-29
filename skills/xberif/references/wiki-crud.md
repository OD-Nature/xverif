# xberif Wiki CRUD

## Read

1. 确认 `XBERIF_WIKI_DIR` 已定义。
2. 先读 `index.md`。
3. 按候选主题读取 concept 页面。
4. 需要反向关系时读 `_index/backlinks.md`；没有该文件时用 `rg` 在 wiki 内查引用。
5. 需要 tag 聚合时读 `_index/tags.md`；没有该文件时扫描 frontmatter。
6. `rg` 命中后必须回到 Markdown 页面本身，不要只引用搜索片段。

## Create

- 创建新的 concept Markdown。
- frontmatter 至少包含 `type`、`title`、`description`。
- 新事实必须能指向 raw source、evidence 或明确标成未确认。
- 更新 `index.md`，让页面可达。
- 更新相关页面的出链。
- 如果存在 `_index/backlinks.md`，同步反向索引。
- 追加 `log.md`。
- 运行校验脚本。

## Update

- 先读旧页面，保留稳定 frontmatter 和标题。
- 将新材料合并到已有概念，不要创建近似重复页面。
- 如果新材料推翻旧结论，写明 contradiction/resolution。
- 无法确认的信息写入未确认信息，不要经验补全。
- 更新 index、backlinks、tags 和 log。
- 运行校验脚本。

## Deprecate

不允许硬删除。删除只能通过移动到 `archive/` 或 `deprecated/` 实现：

1. 移动页面。
2. frontmatter 增加 `deprecated: true` 和 `deprecated_reason`。
3. 更新所有指向旧路径的链接。
4. 更新 `index.md`、`_index/backlinks.md`、`_index/tags.md`。
5. 在 `log.md` 记录 deprecate/move。
6. 运行校验脚本。
