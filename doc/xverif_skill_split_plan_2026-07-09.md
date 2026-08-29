# xverif Skill 分离计划：`xverif-cli` 与 `xverif-mcp`

## Summary

将当前混合型 `skills/xverif` 拆成两个独立 skill：

- `skills/xverif-cli`：专注原生命令行与 JSON envelope，讲 `tools/xdebug --json -`、`tools/xcov --json -`、`tools/xbit`、`tools/xentry`、`tools/xloc`、`tools/xsva` 等 CLI 参数。
- `skills/xverif-mcp`：专注 MCP tool 参数，讲 `xverif_debug_query`、`xverif_cov_query`、`xverif_batch`、stateless MCP tools、MCP session、MCP raw request 壳子。
- 两边都保留完整 API 说明、action 能力说明、字段说明、错误响应说明和 recipes；区别只在入口参数形态：CLI 版给原生 CLI/raw JSON，MCP 版给 MCP tool 壳子。
- 删除旧 `skills/xverif`，并删除已安装 mirror 中的旧 `xverif`，避免 agent 同时加载旧入口和新入口。
- SDK-free xdebug/xcov loop wrapper 归入 `xverif-mcp`，作为“没有 MCP SDK 或需要脚本化 stdio-loop/LSF 时的旁路托管入口”。

## Implementation Order

- 第一项任务：把本计划写入 `doc/xverif_skill_split_plan_2026-07-09.md`。
- 第二项任务：创建 goal，objective 使用该计划书内容，后续实施以该 goal 为准。
- 进入 goal 后再修改 skill 目录、Makefile、安装 mirror 和相关维护文档。
- 本计划实施期间如果发现旧 `skills/xverif` 引用无法直接删除，必须先记录到计划文档并中止确认，不自行保留兼容入口。

## Key Changes

- 新建 `skills/xverif-cli/`：
  - `SKILL.md` 名称为 `xverif-cli`，描述明确触发场景：用户要求 CLI、raw JSON、shell 脚本、离线批处理、直接运行 `tools/*`。
  - 完整保留 xdebug/xcov API 说明：action reference、JSON API、recipes、examples、response fields、troubleshooting、transport、rc.generate、coverage 查询等。
  - 所有可复制 xdebug/xcov 示例使用原生 envelope：`api_version/action/target/args/limits/output`。
  - xdebug session 选择固定写 `target.session_id`；不出现 MCP `session_id` 顶层参数作为调用示例。
  - xcov session/query 示例使用 `xcov.v1` 原生 JSON；不混入 `xverif_cov_query(session=...)`。
  - stateless 工具文档保留 CLI 形态：`tools/xbit ...`、`tools/xentry ...`、`tools/xloc ...`、`tools/xsva ...`。

- 新建 `skills/xverif-mcp/`：
  - `SKILL.md` 名称为 `xverif-mcp`，描述明确触发场景：用户通过 MCP tools 调 xverif，或需要 MCP session、batch、LSF backend、SDK-free loop wrapper。
  - 完整保留 xdebug/xcov API 说明：action 能力、参数、返回字段、错误提示、recipes、examples、coverage 查询和排障说明都要有。
  - xdebug 常规 workflow 使用 `xverif_debug_session_open -> xverif_debug_query -> xverif_debug_session_close`。
  - MCP query 示例必须带 MCP tool 参数壳：`session_id/action/args/limits/output/output_format`，并明确这是外壳；其中 `args` 才是 xdebug action 参数。
  - MCP raw request 单独说明：`xverif_debug_raw_request` / `xverif_cov_raw_request` 才把完整原生 JSON 放进 `request` 字段。
  - `xverif_batch` 单独强调两层 `args`：外层是 MCP tool 参数，内层是 xdebug/xcov action 参数。
  - stateless 工具文档保留 MCP 形态：`xverif_bit_*`、`xverif_entry_*`、`xverif_loc_*`、`xverif_sva_*`。
  - SDK-free wrapper 目录改为通用 `references/sdk-free-loop/`，覆盖 xdebug 和 xcov；说明它是 MCP 侧的旁路托管入口，不是 CLI raw JSON，也不是 xdebug file transport fallback。

- 删除/迁移旧入口：
  - 删除 repo 内 `skills/xverif/`。
  - 更新 `Makefile`：新增 `install-xverif-cli-skill`、`install-xverif-mcp-skill`；`install-all-skill` 自动安装两者。
  - 不保留 `install-xverif-skill` 别名，避免继续误导旧入口。
  - 实施同步时删除 `~/.codex/skills/xverif` 和 `~/.claude/skills/xverif`，再安装 `xverif-cli` / `xverif-mcp`。

- 文档与维护引用：
  - 更新相关维护文档中指向 `skills/xverif` 的链接，改为按语义指向 `skills/xverif-cli` 或 `skills/xverif-mcp`。
  - 注意 `doc/agents/xdebug/*` 中“docs/skill/MCP 同步”的表述，避免只指向旧路径。
  - 历史审计报告可保留旧路径原文；新计划、新维护规则和新 skill 文档不能继续推荐旧入口。

## Test Plan

- 结构检查：
  - `test -f doc/xverif_skill_split_plan_2026-07-09.md`
  - `test -f skills/xverif-cli/SKILL.md`
  - `test -f skills/xverif-mcp/SKILL.md`
  - `test ! -e skills/xverif`
  - `find skills/xverif-cli skills/xverif-mcp -maxdepth 3 -type f | sort`

- 内容边界检查：
  - `rg -n "xverif_debug_query|xverif_cov_query|xverif_batch|xverif_debug_raw_request" skills/xverif-cli` 应只出现在“不要用于 CLI”或入口对照说明中，不作为主示例。
  - `rg -n '"api_version"|"target":' skills/xverif-mcp` 可出现在 raw request、SDK-free、原生合同对照中；常规 MCP query 示例必须额外带 MCP tool 壳。
  - `rg -n "target.session_id" skills/xverif-mcp` 只能用于解释 MCP 到原生映射或 raw request。
  - `rg -n "session_id" skills/xverif-cli` 确认 CLI 示例中 session 选择位于 `target.session_id`。
  - `rg -n "output_format.*json|\"output_format\": \"json\"" skills/xverif-cli skills/xverif-mcp` 确认只在专门讲 JSON 字段读取时出现。

- 完整 API 覆盖检查：
  - 两边都必须包含 xdebug action reference、API/request、recipes、examples、response fields、troubleshooting。
  - 两边都必须包含 xcov coverage API 说明。
  - 两边都必须包含 xbit/xentry/xloc/xsva 的入口说明；CLI 版是命令行，MCP 版是 tool 参数。
  - MCP 版每个 xdebug/xcov 可复制示例必须能看出 MCP 外壳和 action `args` 的边界。

- 安装与 mirror：
  - `make install-xverif-cli-skill`
  - `make install-xverif-mcp-skill`
  - `diff -qr skills/xverif-cli ~/.codex/skills/xverif-cli`
  - `diff -qr skills/xverif-mcp ~/.codex/skills/xverif-mcp`
  - 若 Claude mirror 存在，同步检查 `~/.claude/skills/xverif-cli` 和 `~/.claude/skills/xverif-mcp`
  - `test ! -e ~/.codex/skills/xverif`
  - `test ! -e ~/.claude/skills/xverif`

- 文档质量：
  - `git diff --check`
  - `rg -n "skills/xverif|/xverif/" Makefile AGENTS.md doc skills` 检查旧路径残留；历史报告中的旧路径可保留，但新维护说明不能继续引用旧入口。
  - 抽查 xdebug/xcov CLI JSON 示例仍能通过现有 schema；MCP 示例不按 raw schema 校验，而按 tool 参数壳人工检查。

## Assumptions

- 最终只保留两个新 skill：`xverif-cli` 和 `xverif-mcp`；旧 `xverif` repo 目录与安装 mirror 都删除。
- 两边都要有完整 API 文档，不做“CLI 详写、MCP 简写”的轻量分裂。
- 差异只体现在入口参数和示例壳子：CLI 是原生命令/JSON envelope，MCP 是 MCP tool 参数壳或 raw request 的 `request` 壳。
- SDK-free loop wrapper 虽然直接驱动 `tools/xdebug --stdio-loop` / `tools/xcov --stdio-loop`，但归入 `xverif-mcp`，因为它和 MCP 共享 session/stdio-loop/LSF 托管语义。
- 本轮是 skill/docs/Makefile 变更，不修改 xdebug/xcov runtime；源码测试只需要文档/安装/示例边界检查，除非实施时发现 schema 示例校验脚本需要调整。
