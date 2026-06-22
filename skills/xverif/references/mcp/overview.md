# xverif MCP 总览

`tools/xverif-mcp` 是基于 FastMCP 的统一入口。交互式 AI 工具调用优先使用 MCP，除非用户无法使用 MCP SDK 或明确需要脚本化 SDK-free wrapper。

## 工具组

- xdebug：stateful backend，`xverif_debug_*`。
- xcov：stateful backend，`xverif_cov_*`。
- xbit/xentry/xloc/xberif/xsva：stateless CLI adapter。
- common：`xverif_tools`、`xverif_tool_help`、`xverif_batch`。

如果不确定哪些工具暴露，先调用 `xverif_tools`。`XVERIF_MCP_ENABLE_*` 可能关闭部分工具组。

## raw request

- `xverif_debug_raw_request` / `xverif_cov_raw_request` 是 one-shot CLI 路径。
- raw request 不走 MCP-managed session manager，也不维护 stdio-loop/LSF job。
- 需要长期 session 时使用 `xverif_debug_session_open` + `xverif_debug_query`。

## batch

`xverif_batch` 执行 NDJSON tool 请求文件，适合 open -> query -> close 的串行流程。batch 行里的 tool 参数需要嵌套在 `args` 里。
