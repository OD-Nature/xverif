---
status: accepted
---

# 将数据库 Fixture 缓存放在仓库本地

xverif 的内容寻址数据库 Fixture 统一存放在仓库内的 `.xverif-test-cache/`，并从版本控制中排除；测试清单和 fixture manifest 解析该统一根目录，不再把各 fixture 源码目录下分散的 `out/` 作为长期资产位置。该选择强调项目隔离、路径可见和开发者可理解性，不提供用户级缓存的隐式 fallback。

## Considered Options

- 选择：仓库本地 `.xverif-test-cache/`。
- 拒绝：默认 `$XDG_CACHE_HOME` 用户级共享缓存；可以跨 worktree 复用，但资产来源和项目归属更隐蔽。
- 拒绝：继续使用各 fixture 的 `out/`；迁移较少，但无法形成统一资产目录和生命周期。

## Consequences

- 不同 clone/worktree 默认各自准备 fixture，不跨工作区自动复用。
- 缓存目录必须加入 `.gitignore`，不得提交大型 FSDB、daidir、VDB 或工具生成文件。
- catalog/runner 必须通过统一缓存 API 查找资产，测试不得硬编码 `.xverif-test-cache/` 内部布局。
- 源码 clean、fixture clean、容量回收和完整重建的边界由后续决策明确。
