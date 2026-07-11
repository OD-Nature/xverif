---
name: xverif-mcp
description: >
  当 AI agent 需要通过 MCP tools 使用 xverif 工具体系时使用：调用
  xverif_debug_*、xverif_cov_*、xverif_batch、xverif_bit_*、xverif_entry_*、
  xverif_loc_*、xverif_sva_*，或使用 SDK-free loop wrapper 脚本化
  xdebug/xcov stdio-loop/LSF session。不要用于原生 CLI envelope；CLI 调用使用 xverif-cli。
---

# xverif MCP Skill

这是 xverif MCP tool 参数和托管 session skill。两边都保留完整 API 说明；本 skill 的所有常规示例都必须带 MCP tool 参数壳，不能把原生 `xdebug.v1` / `xcov.v1` envelope 当作普通 MCP query。

## 任务路由

| 任务 | 读取 |
| --- | --- |
| 使用 MCP xverif 工具、工具组、batch | [references/mcp/overview.md](references/mcp/overview.md) |
| 使用 MCP 托管的 xdebug/xcov stateful session | [references/mcp/stateful-sessions.md](references/mcp/stateful-sessions.md) |
| 使用 MCP LSF backend | [references/mcp/lsf.md](references/mcp/lsf.md) |
| 定位 MCP server、tool、session 问题 | [references/mcp/troubleshooting.md](references/mcp/troubleshooting.md) |
| 不用 MCP SDK、脚本化或必须 LSF 地运行 xdebug/xcov session | [references/sdk-free-loop/overview.md](references/sdk-free-loop/overview.md) |
| 使用 SDK-free UDS JSONL 协议 | [references/sdk-free-loop/uds-jsonl.md](references/sdk-free-loop/uds-jsonl.md) |
| 使用 SDK-free LSF backend | [references/sdk-free-loop/lsf.md](references/sdk-free-loop/lsf.md) |
| 定位 SDK-free wrapper 问题 | [references/sdk-free-loop/troubleshooting.md](references/sdk-free-loop/troubleshooting.md) |
| 查询 daidir、FSDB、波形值、driver、active driver、APB/AXI、verify、rc | [references/xdebug/overview.md](references/xdebug/overview.md) |
| 查询 xdebug action 作用、适用场景、工作原理、参数合同 | [references/xdebug/action-reference.md](references/xdebug/action-reference.md) |
| 构造 xdebug MCP query、查 action/schema | [references/xdebug/json-api.md](references/xdebug/json-api.md) |
| 按流程做 xdebug debug | [references/xdebug/recipes.md](references/xdebug/recipes.md) |
| 参考 xdebug MCP 示例和证据链写法 | [references/xdebug/examples.md](references/xdebug/examples.md) |
| 读取 xdebug compact/xout/JSON 字段 | [references/xdebug/response-fields.md](references/xdebug/response-fields.md) |
| 定位 xdebug backend、session、socket、engine、日志问题 | [references/xdebug/troubleshooting.md](references/xdebug/troubleshooting.md) |
| 判断 xdebug UDS/TCP/file transport | [references/xdebug/transport.md](references/xdebug/transport.md) |
| 生成 nWave rc 证据 | [references/xdebug/rc-generate.md](references/xdebug/rc-generate.md) |
| 查询 VCS/Verdi coverage database | [references/xcov.md](references/xcov.md) |
| 计算 bit slice、SV literal、mask、表达式、expected value | [references/xbit.md](references/xbit.md) |
| 还原 `L_XXXXXXXX` 日志位置 ID | [references/xloc.md](references/xloc.md) |
| 解 entry/descriptor/header fragments | [references/xentry.md](references/xentry.md) |
| 解析和解释 SVA IR | [references/xsva.md](references/xsva.md) |

## 入口选择

- xdebug 常规 MCP workflow：先 `xverif_debug_session_open`，再 `xverif_debug_query(session_id, action, args, limits, output)`，最后 `xverif_debug_session_close`。
- xcov 常规 MCP workflow：先 `xverif_cov_session_open`，再 `xverif_cov_query(session, action, args, limits, output)`，最后 `xverif_cov_session_close`。
- xdebug/xcov 都提供 `session_list/doctor/close/kill/gc` 对称工具；SESSION_LOST 或 partial cleanup 时先 list tombstone/doctor，再精确 kill/gc，不自动 reopen。
- MCP query 参数壳和原生 action 参数必须分清：xdebug 外层是 `session_id/action/args/limits/output/output_format`，xcov 外层是 `session/action/args/limits/output/output_format`；内层 `args` 才是 xdebug/xcov action 参数。
- xdebug MCP 不暴露原生 envelope raw request。常规调试只使用 `xverif_debug_session_open` + `xverif_debug_query`；需要完整原生 `xdebug.v1` envelope 时改用 `xverif-cli`。
- debug/cov query 禁止 native lifecycle action；coverage health 使用 `xverif_cov_session_doctor`，不得把 `session.status` 塞进 query。
- `xverif_batch` 每行是 MCP tool 调用壳：`tool` 指工具名，外层 `args` 指该 MCP tool 的参数；如果该 tool 自己也有 `args`，需要嵌套第二层。
- SDK-free loop wrapper 是没有 MCP SDK 或需要脚本化 stdio-loop/LSF 时的旁路托管入口，仍按 MCP/session 托管语义维护；不要把它当原生 CLI raw JSON。
- 默认优先使用 `output_format:"xout"` 或省略 `output_format`；只有脚本字段读取、JSON schema 验证或 envelope 调试时才请求 JSON/envelope。

## 通用规则

- MCP server及 LSF job环境必须显式传递与 `VERDI_HOME` 一致的
  `XVERIF_EDA_PROFILE=verdi-2018|verdi-2023`；2018 xcov走 native worker，
  2023走 Python backend，不自动 fallback。
- 脚本解析或字段比较时使用 JSON；不要解析默认人类文本。
- 不确定 action 参数时，先用 MCP tool help、`xverif_tools`、action-specific schema 查询，不要猜字段。
- xdebug 参数错误时先读结构化错误提示：`invalid_arg`、`expected`、`allowed_values`、`did_you_mean`、`required_any_of`、`correct_example`。
- xdebug clock sampling 默认优先用 `edge:"negedge"`；只有 posedge monitor、DUT posedge 语义或采样边界 race 证据需要时才用 `edge:"posedge"`。
- xdebug `stream.*` 是重要通用能力，不限标准总线。只要查询任务能抽象成 `clock + vld + data`，并可选 `rdy`、`bp`、`sop/eop`、`channel_id`，就优先考虑 `stream.config.load` + `stream.query` / `stream.export`。
- 对所有需要 `*.config.load` 的 xdebug action，优先复用被调试项目内已有的 xdebug 配置目录和关键信号路径文档；缺失时主动询问用户是否创建，并询问是否使用 xwiki 维护长期项目记忆。
- 结论保留事实证据：signal/path/time/value/file:line/error code。
- 用户可见回答不要暴露本机绝对路径；用 `<xverif-root>`、`<project-root>` 或 `$XVERIF_HOME`。
- license/NPI/仿真/真实 LSF/MCP stdio-loop/UDS bind/file transport 实机验证可能需要在受限沙箱外运行。
- 返回 `truncated:true` 时，缩小查询或显式提高 limits；不要把 compact 输出当全量。
