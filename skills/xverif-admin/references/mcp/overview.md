# xverif MCP 总览

`tools/xverif-mcp` 是基于 FastMCP 的统一入口。交互式 AI 工具调用优先使用 MCP，除非用户无法使用 MCP SDK 或明确需要脚本化 SDK-free wrapper。

项目接入优先使用 `tools/xverif-mcp-auto`：它读取机器级
`~/.config/xverif/eda.toml`，没有配置时扫描常见安装根目录，自动设置匹配的
`VERDI_HOME`、`VCS_HOME`、PLI 基础库和 `XVERIF_EDA_PROFILE`。NPI library path 由
`tools/xdebug`/`tools/xcov` wrapper 单次注入；自动模式只接受唯一
profile；多版本机器使用项目 `.xverif-eda.toml` 的 `preferred_profile` 消歧，
不得在失败后切换 profile。`--doctor` 只输出非敏感选择证据。

Codex 通过 `make install-codex-rtl` 安装通用按需入口，在任意数字电路工程运行
`codex-rtl`；普通 `codex` 不加载 xverif。Claude Code 使用各项目的 `.mcp.json`。
两者都调用 `tools/xverif-mcp-auto`，不要把 Claude 的 `.mcp.json` 当作 Codex 配置。
若 MCP 客户端不继承 license 变量，在 EDA 环境 shell 中执行一次
`tools/xverif-mcp-auto --init`；它创建 `~/.config/xverif/eda.toml` 并设为 `0600`，
不把 license 写入项目或日志。

## 工具组

- xdebug：stateful backend，`xverif_debug_*`。
- xcov：stateful backend，`xverif_cov_*`。
- xbit/xentry/xloc/xsva：stateless CLI adapter。
- common：`xverif_tools`、`xverif_tool_help`、`xverif_batch`。

如果不确定哪些工具暴露，先调用 `xverif_tools`。`XVERIF_MCP_ENABLE_*` 可能关闭部分工具组。

连通性检查使用 `xverif_ping`。它不访问 backend、session、NPI 或 license，适合确认 MCP server 本身是否可调用。

## xdebug 入口

- xdebug MCP 不暴露原生 envelope raw request。
- 常规 xdebug 调试使用 `xverif_debug_session_open` + `xverif_debug_query`。
- action 发现和 schema 查询使用 `xverif_debug_list_actions` / `xverif_debug_get_schema`。
- 需要完整原生 `xdebug.v1` envelope、验证 CLI 行为或做一次性脚本时，改用 `xverif`。
- xcov MCP 也不暴露原生 envelope raw request；完整 `xcov.v1` envelope 同样改用 `xverif`。
- xdebug 参数错误时，MCP 默认 xout 会显示 backend 的 `invalid_arg`、`did_you_mean`、`required_any_of` 和 `correct_example`。优先按这些字段修正请求；不要因为第一次参数写错就切换到其它 transport。

## batch

`xverif_batch` 执行 NDJSON tool 请求文件，适合 open -> query -> close 的串行流程。batch 行里的 tool 参数需要嵌套在 `args` 里。
