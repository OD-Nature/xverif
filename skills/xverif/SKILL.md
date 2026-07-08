---
name: xverif
description: >
  当 AI agent 需要使用 xverif 验证工具体系时使用：xdebug 查询 daidir/FSDB
  事实和 RTL 因果，SDK-free xdebug wrapper 在没有 MCP SDK 或需要脚本化 LSF
  stdio-loop session 时使用，MCP xverif tools 用于交互式 AI 工具访问，xcov 查询
  VCS/Verdi coverage database，xbit 做确定性 bit/SV literal/表达式计算，xloc
  还原压缩日志位置 ID，xentry 解 entry/descriptor fragments，xsva 解析
  SVA IR，xeda-runner 安全执行 EDA 命令。
---

# xverif 工具 Skill

这是 xverif 工具体系的导航 skill。只读取当前任务需要的 reference，不要默认加载全部文档。

## 任务路由

| 任务 | 读取 |
| --- | --- |
| 查询 daidir、FSDB、波形值、driver、active driver、APB/AXI、verify、rc | [references/xdebug/overview.md](references/xdebug/overview.md) |
| 查询 xdebug action 作用、适用场景、工作原理、参数合同 | [references/xdebug/action-reference.md](references/xdebug/action-reference.md) |
| 构造 xdebug JSON request、raw CLI request、查 action/schema | [references/xdebug/json-api.md](references/xdebug/json-api.md) |
| 按流程做 xdebug debug | [references/xdebug/recipes.md](references/xdebug/recipes.md) |
| 参考 xdebug 实战示例和证据链写法 | [references/xdebug/examples.md](references/xdebug/examples.md) |
| 读取 xdebug compact/xout/JSON 字段 | [references/xdebug/response-fields.md](references/xdebug/response-fields.md) |
| 定位 xdebug 原生命令、session、socket、engine、日志问题 | [references/xdebug/troubleshooting.md](references/xdebug/troubleshooting.md) |
| 判断 xdebug UDS/TCP/file transport | [references/xdebug/transport.md](references/xdebug/transport.md) |
| 生成 nWave rc 证据 | [references/xdebug/rc-generate.md](references/xdebug/rc-generate.md) |
| 不用 MCP SDK、脚本化或必须 LSF 地运行 xdebug session | [references/sdk-free-xdebug/overview.md](references/sdk-free-xdebug/overview.md) |
| 使用 SDK-free UDS JSONL 协议 | [references/sdk-free-xdebug/uds-jsonl.md](references/sdk-free-xdebug/uds-jsonl.md) |
| 使用 SDK-free xdebug LSF backend | [references/sdk-free-xdebug/lsf.md](references/sdk-free-xdebug/lsf.md) |
| 定位 SDK-free wrapper 问题 | [references/sdk-free-xdebug/troubleshooting.md](references/sdk-free-xdebug/troubleshooting.md) |
| 使用 MCP xverif 工具、工具组、batch、raw request | [references/mcp/overview.md](references/mcp/overview.md) |
| 使用 MCP 托管的 xdebug/xcov stateful session | [references/mcp/stateful-sessions.md](references/mcp/stateful-sessions.md) |
| 使用 MCP LSF backend | [references/mcp/lsf.md](references/mcp/lsf.md) |
| 定位 MCP server、tool、session 问题 | [references/mcp/troubleshooting.md](references/mcp/troubleshooting.md) |
| 查询 VCS/Verdi coverage database | [references/xcov.md](references/xcov.md) |
| 计算 bit slice、SV literal、mask、表达式、expected value | [references/xbit.md](references/xbit.md) |
| 还原 `L_XXXXXXXX` 日志位置 ID | [references/xloc.md](references/xloc.md) |
| 解 entry/descriptor/header fragments | [references/xentry.md](references/xentry.md) |
| 解析和解释 SVA IR | [references/xsva.md](references/xsva.md) |
| 安全执行 make/vcs/simv/verdi 类 EDA 命令 | [references/xeda-runner.md](references/xeda-runner.md) |

## 入口选择

- 有 MCP client 且 MCP SDK 可用时，交互式 AI 工具调用优先用 MCP。
- MCP 场景下，xdebug 原生 action 能力从 `xverif_debug_query` 进入：先 `xverif_debug_session_open`，再把 `trace.driver`、`value.batch_at`、`event.find`、`trace.active_driver` 等 action 作为 query 参数传入。
- xdebug/MCP 调用默认优先使用 `output_format:"xout"` 或省略 `output_format`，让工具返回适合 AI 阅读的结构化文本摘要。skill 示例默认不要写 `output_format:"json"`；只有专门展示脚本字段读取、JSON response schema 或 response-fields 时才显式请求 JSON。
- `xverif_debug_raw_request` 只用于需要完整 xdebug envelope 控制或验证 raw CLI 行为；常规 xdebug debug workflow 不默认使用 raw request。
- 必须使用 LSF，且不能使用 MCP、不能安装 MCP SDK，或需要脚本/批处理直接驱动长期 xdebug `--stdio-loop` session 时，优先用 SDK-free xdebug wrapper。
- 只需要一次性完整 JSON request 时，可以用 xdebug/xcov raw CLI；raw CLI 不是 wrapper 托管的 stdio-loop session。
- 项目里存在 xeda-runner 配置时，EDA 命令必须走 `xeda-runner`；不要直接跑 `make`、`vcs`、`simv`、`urg`、`verdi` 或项目 setup。

## 通用规则

- 脚本解析或字段比较时使用 JSON；不要解析默认人类文本。
- 不确定 action 参数时，先查 `actions` 和 action-specific `schema`，不要猜字段。
- xdebug 参数错误时先读结构化错误提示：`invalid_arg` 指出错字段，`expected` / `allowed_values` 说明允许形态，`did_you_mean` 给出旧字段或错位置的替代字段，`required_any_of` 说明互斥必填组，`correct_example` 给出最小正确请求模板。默认 xout 也会显示这些字段；不要只看自由文本 `message`。
- xdebug clock sampling 默认优先用 `edge:"negedge"`；只有 posedge monitor、DUT posedge 语义或采样边界 race 证据需要时才用 `edge:"posedge"`。使用 posedge 时注意 `sample_point:"before"` 和 `"after"` 可能不同，尤其数据与 clock edge 同时间变化时；必须用 posedge 时默认推荐 `sample_point:"before"`。`edge:"dual"` 只用于 DDR、真实双沿协议或特殊 bring-up，不作为普通 valid/ready、AXI、APB 默认选择。
- xdebug `stream.*` 是重要通用能力，不限标准总线。只要查询任务能抽象成 `clock + vld + data`，并可选 `rdy`、`bp`、`sop/eop`、`channel_id`，就优先考虑 `stream.config.load` + `stream.query` / `stream.export`。适用对象包括外部接口、模块内部 valid-ready 交互、pipeline stage、FIFO/queue 出入口、仲裁请求授予、RM/scoreboard 内部任务流等。
- 对所有需要 `*.config.load` 的 xdebug action，优先复用被调试项目内已有的 xdebug 配置目录和关键信号路径文档；不要每次从 0 推导列表。若用户工作目录缺少这两项，主动询问用户是否创建，例如 `xdebug/configs/` 和 `xdebug/signals.md`，并建议把维护规则写入该项目的 `AGENTS.md`。还要主动询问用户是否使用 xwiki 维护长期项目记忆；用户确认前不要默认创建或写入 xwiki。
- 结论保留事实证据：signal/path/time/value/file:line/error code。
- 用户可见回答不要暴露本机绝对路径；用 `<xverif-root>`、`<project-root>` 或 `$XVERIF_HOME`。
- license/NPI/仿真/真实 LSF/UDS bind/file transport 实机验证可能需要在受限沙箱外运行。
- 返回 `truncated:true` 时，缩小查询或显式提高 limits；不要把 compact 输出当全量。
