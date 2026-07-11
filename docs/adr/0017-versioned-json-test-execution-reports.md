---
status: accepted
---

# 输出终端、JUnit 和版本化 JSON 测试报告

xverif pytest plugin 同时提供 pytest 终端结果、JUnit XML 和版本化 JSON execution report；每个 suite 的原始 stdout/stderr 与附加 artifact 独立落盘。JSON 报告记录 catalog/gate 版本、execution plan、选择原因、required/optional、suite 正交属性、fixture 指纹、环境能力、资源 claim、耗时、结果、error layer、命令摘要和 artifact 相对路径。

## Considered Options

- 选择：终端、JUnit 与版本化 JSON 并存，原始日志按 suite 隔离。
- 拒绝：只使用终端和 JUnit；CI 集成足够，但 fixture、环境和 runner 诊断信息不足。
- 拒绝：直接建设 HTML/dashboard；投入过早，且仍需要稳定机器数据格式作为底座。

## Consequences

- JSON schema 必须版本化并有 contract test；报告不得依赖解析人类终端文本。
- 命令和环境只记录去敏摘要，不写 token、cookie、license 内容、完整唯一 ID 或不必要的绝对私有路径。
- failed/error suite 的 artifact 路径必须可从终端和 JUnit 定位到 JSON 与原始日志。
- 报告位置与自动重试语义已由 ADR-0018、ADR-0020 明确；具体保留默认值记录在统一迁移计划中。
