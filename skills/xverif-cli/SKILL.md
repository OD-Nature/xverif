---
name: xverif-cli
description: >
  当 AI agent 需要通过命令行或原生 JSON envelope 使用 xverif 工具体系时使用：
  直接调用 tools/xdebug、tools/xcov、tools/xbit、tools/xentry、tools/xloc、
  tools/xsva、xeda-runner，构造 xdebug.v1/xcov.v1 request，编写 shell 脚本
  或离线批处理。不要用于 MCP tool 参数；MCP 调用使用 xverif-mcp。
---

# xverif CLI Skill

这是 xverif 命令行和原生 JSON API skill。所有可复制请求示例都使用 CLI/raw JSON 形态；如果用户通过 MCP tool 调用 xverif，改用 `xverif-mcp`。

## 任务路由

| 任务 | 读取 |
| --- | --- |
| 查询 daidir、FSDB、波形值、driver、active driver、APB/AXI、verify、rc | [references/xdebug/overview.md](references/xdebug/overview.md) |
| 查询 xdebug action 作用、适用场景、工作原理、参数合同 | [references/xdebug/action-reference.md](references/xdebug/action-reference.md) |
| 构造 xdebug 原生 JSON request、查 action/schema | [references/xdebug/json-api.md](references/xdebug/json-api.md) |
| 按流程做 xdebug debug | [references/xdebug/recipes.md](references/xdebug/recipes.md) |
| 参考 xdebug CLI/raw JSON 示例和证据链写法 | [references/xdebug/examples.md](references/xdebug/examples.md) |
| 读取 xdebug compact/xout/JSON 字段 | [references/xdebug/response-fields.md](references/xdebug/response-fields.md) |
| 定位 xdebug 原生命令、session、socket、engine、日志问题 | [references/xdebug/troubleshooting.md](references/xdebug/troubleshooting.md) |
| 判断 xdebug UDS/TCP/file transport | [references/xdebug/transport.md](references/xdebug/transport.md) |
| 生成 nWave rc 证据 | [references/xdebug/rc-generate.md](references/xdebug/rc-generate.md) |
| 查询 VCS/Verdi coverage database | [references/xcov.md](references/xcov.md) |
| 计算 bit slice、SV literal、mask、表达式、expected value | [references/xbit.md](references/xbit.md) |
| 还原 `L_XXXXXXXX` 日志位置 ID | [references/xloc.md](references/xloc.md) |
| 解 entry/descriptor/header fragments | [references/xentry.md](references/xentry.md) |
| 解析和解释 SVA IR | [references/xsva.md](references/xsva.md) |
| 安全执行 make/vcs/simv/verdi 类 EDA 命令 | [references/xeda-runner.md](references/xeda-runner.md) |

## 入口选择

- xdebug CLI：`tools/xdebug --json -` 或 `xdebug --json -`，request 必须是完整 `xdebug.v1` envelope。
- xcov CLI：`tools/xcov --json -`，request 必须是完整 `xcov.v1` envelope。
- stateful CLI 查询先调用 `session.open`，后续原生 request 用 `target.session_id` 选择 session。
- 默认优先使用 xout/compact 输出；只有脚本字段读取、schema 校验或用户明确要求时才请求 JSON。
- 不要把 MCP tool 参数直接写进 CLI request：`xverif_debug_query.session_id`、`xverif_cov_query.session`、`xverif_batch.tool/args` 都不是原生 envelope 字段。
- xdebug/xcov SDK-free loop wrapper 不属于本 skill；没有 MCP SDK 或需要脚本化 stdio-loop/LSF 托管时使用 `xverif-mcp`。
- 项目里存在 xeda-runner 配置时，EDA 命令必须走 `xeda-runner`；不要直接跑 `make`、`vcs`、`simv`、`urg`、`verdi` 或项目 setup。

## 通用规则

- 脚本解析或字段比较时使用 JSON；不要解析默认人类文本。
- 不确定 action 参数时，先用 CLI 查 `actions` 和 action-specific `schema`，不要猜字段。
- xdebug 参数错误时先读结构化错误提示：`invalid_arg`、`expected`、`allowed_values`、`did_you_mean`、`required_any_of`、`correct_example`。
- xdebug clock sampling 默认优先用 `edge:"negedge"`；只有 posedge monitor、DUT posedge 语义或采样边界 race 证据需要时才用 `edge:"posedge"`。
- xdebug `stream.*` 是重要通用能力，不限标准总线。只要查询任务能抽象成 `clock + vld + data`，并可选 `rdy`、`bp`、`sop/eop`、`channel_id`，就优先考虑 `stream.config.load` + `stream.query` / `stream.export`。
- 对所有需要 `*.config.load` 的 xdebug action，优先复用被调试项目内已有的 xdebug 配置目录和关键信号路径文档；缺失时主动询问用户是否创建，并询问是否使用 xwiki 维护长期项目记忆。
- 结论保留事实证据：signal/path/time/value/file:line/error code。
- 用户可见回答不要暴露本机绝对路径；用 `<xverif-root>`、`<project-root>` 或 `$XVERIF_HOME`。
- license/NPI/仿真/真实 LSF/UDS bind/file transport 实机验证可能需要在受限沙箱外运行。
- 返回 `truncated:true` 时，缩小查询或显式提高 limits；不要把 compact 输出当全量。
