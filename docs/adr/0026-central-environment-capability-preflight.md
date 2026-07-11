---
status: accepted
---

# 在 suite 执行前集中探测环境能力

xverif catalog 通过具名 capability 声明 suite 的环境依赖，例如 `vcs`、`npi`、`fsdb`、`svt_axi_vip`、`svt_apb_vip`、`lsf`、`mcp_process` 和外部真实数据。pytest plugin 在执行任何 suite 前集中进行只读 preflight，生成版本化 environment snapshot，并结合当前 gate 的 required/optional 身份一次性判定 ERROR 或 SKIP；suite 不再各自探测环境或选择替代路径。

## Considered Options

- 选择：统一 capability schema、集中 preflight 和环境快照。
- 拒绝：suite 执行时自行探测；错误出现晚、结果不一致，也容易形成隐式 fallback。
- 拒绝：只依赖环境变量；配置存在不等于工具、文件、license 或 transport 真正可用。

## Consequences

- plan/collect-only 只解析声明，不运行外部探测；实际 run 的 preflight 才验证当前环境。
- preflight probe 必须只读、有 timeout、去敏并可单测；不得提交真实 job、生成 fixture 或消费长期 license。
- required capability 缺失时在 suite 启动前报告 ERROR；optional capability 缺失时报告有明确原因的 SKIP。
- capability 不可用时不得切换 fake backend、其它 transport、不同数据库或较低测试层级。
