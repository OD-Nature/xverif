# 调用表面选择

先选能力，再选表面。

1. 当前 agent 已配置 xverif MCP 时优先 [MCP](../surfaces/mcp.md)。
2. 一次性 shell、脚本和完整 envelope 使用 [CLI](../surfaces/cli.md)。
3. 没有 MCP SDK或必须脚本化/托管 LSF stdio-loop 时才使用 [SDK-free loop](../surfaces/sdk-free-loop.md)，并读取 `xverif-admin`。
4. MCP、CLI 和 SDK-free 只改变外层包装，不改变 action 语义。精确字段查询 runtime tool/action schema。
5. 不因调用失败自动切换表面、transport、backend 或数据源。

CLI 使用 `target.session_id`；MCP query 使用顶层 `session_id`；action 参数只放内层 `args`。
