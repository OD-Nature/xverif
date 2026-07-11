---
status: accepted
---

# 将每个外部 suite 收集为独立 pytest item

pytest plugin 为 catalog 中的 shell、C++、Make/VCS、MCP 和真实数据 suite 创建自定义 collector/item；每个 suite 拥有稳定 node ID、独立 timeout、工作目录、环境要求、日志附件、退出码解释和测试结果。不得用一个通用参数化 Python 测试函数压扁所有外部 runner，也不得把非 Python suite 留在 pytest 编排之外。

## Considered Options

- 选择：每个外部 suite 对应自定义 pytest item。
- 拒绝：单个参数化 Python wrapper；实现简单，但 suite identity、日志、错误层和中断清理不清晰。
- 拒绝：pytest 只管理 Python tests；与 pytest 作为唯一编排入口的决定冲突。

## Consequences

- collection 必须是无副作用的；只有 item execution 可以启动外部 runner。
- item 适配器统一处理 timeout、signal、中断、stdout/stderr 捕获、artifact 路径和结构化结果，但 suite-specific 命令由 catalog 声明。
- runner 返回的 fixture unavailable、environment unavailable、test assertion failure 和 infrastructure error 必须映射成不同 pytest 结果/报告字段。
- pytest node ID 必须来自稳定 suite ID，而不是临时路径或完整命令字符串。
