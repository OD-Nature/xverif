---
status: accepted
---

# Fixture 指纹默认使用工具兼容版本身份

数据库 Fixture 指纹默认纳入 VCS、Verdi、FSDB/PLI 的主次版本和影响数据库兼容性的关键 ABI，完整 patch/build 版本保存为 provenance 但不默认触发重建；个别已证明依赖精确工具构建的 fixture 可以在 catalog 中声明 exact tool identity。工具身份完全不匹配时缓存失效，不尝试用其它工具或旧资产 fallback。

## Considered Options

- 选择：兼容版本进入指纹，完整版本进入 provenance，允许 fixture 显式收紧。
- 拒绝：完整 build 字符串总是进入指纹；无语义差异的补丁也会造成大规模重复仿真。
- 拒绝：工具版本不进入指纹；可能复用数据库格式或 ABI 不兼容的资产。

## Consequences

- testinfra 提供统一 tool identity normalizer，fixture builder 不各自解析版本文本。
- manifest 同时保存 fingerprint 使用的 compatibility identity 和完整去敏 provenance。
- 兼容规则必须有 contract test；未知版本格式不能猜测兼容，应在 prepare/preflight 明确 ERROR。
