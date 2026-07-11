---
status: accepted
---

# 对 suite 使用分阶段 timeout 并清理完整进程树

每个 xverif suite 必须在 catalog 中声明或继承 `prepare`、`execute`、`cleanup` 三个阶段的 timeout。阶段超时由 pytest plugin 报告为 `ERROR` 且 `error_layer=timeout`，记录具体阶段；plugin 终止该 suite 拥有的完整本地进程组或 LSF job，cleanup 使用独立上限，不能无限等待或通过重试恢复。

## Considered Options

- 选择：分阶段 timeout 与统一进程树/job 清理。
- 拒绝：整个 pytest run 只有全局 timeout；不能定位准备、执行或清理卡死，也会连带终止无关并行 suite。
- 拒绝：各 runner 自行管理 timeout；继续保留分散、不可比较的超时和清理合同。

## Consequences

- 自定义 pytest item 必须建立明确 process ownership，保存进程组、launcher 和可选 job identity，而不记录不必要的完整唯一 ID。
- timeout 报告包含阶段、预算、实际耗时、最后日志和 cleanup 结果；不把 timeout 伪装成断言 FAIL。
- cleanup timeout 后仍未确认终止的资源报告 unresolved，gate 保持 ERROR，不切换 transport/backend 或静默遗留。
- xdist worker 异常退出时，controller 负责资源 token 回收与 orphan audit。
