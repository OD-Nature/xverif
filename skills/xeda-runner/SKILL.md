---
name: xeda-runner
description: >
  当任务明确需要执行 make、VCS、simv、Verdi、URG 等 EDA 命令时使用。
  这是有副作用的执行型 skill，不用于普通设计、波形或 coverage 事实查询。
---

# xeda-runner

只有任务确实要求执行 EDA 命令时启用。读取 [执行参考](references/execution.md)，使用项目预配置白名单和环境初始化，不绕过 runner 直接执行受管 EDA 命令。

- 执行前确认目标、工作目录、参数和预期产物。
- NPI、VCS、VIP、license 和真实 EDA 动作在沙箱外运行。
- 不自动降级命令、fixture、backend 或测试层级。
- 返回命令、退出码、关键输出、产物和阻塞原因。
