---
name: xcov
description: >
  当 AI agent 需要查询 VCS/Verdi coverage database（simv.vdb/merged.vdb）、
  使用 xcov.v1 JSON request 或 xverif_cov_* MCP 工具查看 code coverage、
  functional coverage、hierarchy scope 覆盖率、coverage holes、source file/line
  到 coverage item 映射，或导出 compact coverage evidence 时使用。适用于 AI
  coverage debug evidence 查询，不负责自动解释 hole 原因或生成补测策略。
---

# xcov Coverage Query Skill

`xcov` 是面向 AI/MCP 的 VCS/Verdi coverage database 查询引擎。输入是
`xcov.v1` JSON request，默认输出 `xout`，机器解析时显式请求 JSON。

详细协议以 `experiments/xcov_npi_coverage/xocv_plan.md` 为准；用户文档见
`xcov/README.md`。

## 什么时候使用

使用 xcov：

- 用户给出 `simv.vdb`、`merged.vdb`、coverage database 路径或 xcov session。
- 需要查 line/toggle/branch/condition/fsm/assert/functional coverage。
- 需要找 coverage holes，并保留 `file/line` evidence。
- 需要按 hierarchy scope 查看 summary、children 排名或 scope search。
- 需要按源码 `file/line/window` 反查相关 coverage item。
- 需要查询 covergroup/coverpoint/cross/bin 的 functional coverage。
- 需要把大 coverage 结果导出为 `json/ndjson/csv/md` artifact。

不要用 xcov：

- 解释 hole 的根因、生成补测策略；这应由 agent 结合 RTL、xdebug、xberif 完成。
- 查询波形值或 driver；用 xdebug。
- 做 bit slice、signed/unsigned、expected value 计算；用 xbit。
- 写 exclusion 或跨 vdb compare；这些不是 xcov v1 默认能力。

## 入口选择

优先使用 MCP：

- `xverif_cov_session_open`：打开/复用 coverage database session。
- `xverif_cov_query`：通过 session 调 xcov action。
- `xverif_cov_session_close`：关闭 session。
- `xverif_cov_list_actions` / `xverif_cov_get_schema`：查机器契约。
- `xverif_cov_raw_request`：one-shot 调试完整 request。

和 xdebug 对齐的边界：

- xcov 自己管理 coverage database session、VDB/NPI handle、scope traversal 和
  query execution。
- MCP 只管理 `tools/xcov --stdio-loop` 进程、direct/LSF launcher、alias/default
  session 映射和 request 转发。
- 不要假设 MCP 保存 coverage index；重查询语义以 xcov backend 返回为准。

命令行入口：

```bash
xcov --stdio-loop
xcov --json -
tools/xcov --json -
```

`tools/xcov` 优先使用 `$XVERIF_XCOV_PYTHON`，否则使用当前可用的 Python 3.11
环境。真实 NPI 查询需要能访问 Synopsys license server；沙箱内 localhost
license 可能不可达，应在沙箱外运行。

## 常用 action

Session:

```json
{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"merged.vdb"},"args":{"name":"cov0"}}
```

Coverage holes:

```json
{
  "api_version": "xcov.v1",
  "action": "cov.holes",
  "target": {"session_id": "cov0"},
  "args": {
    "metrics": ["line", "toggle", "branch", "condition", "fsm", "assert", "functional"],
    "limits": {"max_items": 100, "overflow": "truncate"}
  }
}
```

Scope ranking:

```json
{
  "api_version": "xcov.v1",
  "action": "scope.children",
  "target": {"session_id": "cov0"},
  "args": {
    "scope": "top.u_dut",
    "metrics": ["line", "toggle", "branch"],
    "sort": {"by": "coverage_pct", "metric": "toggle", "order": "asc"},
    "limits": {"max_items": 50}
  }
}
```

Scope 语义：

- `scope.summary(scope=...)` 只返回该 scope 的一条聚合结果。
- `scope.summary` 不带 scope 时返回 top scopes。
- `scope.children(scope=...)` 默认只返回直接 child。
- `scope.children(..., recursive=true)` 才返回 descendants。
- `scope.search` 只做 scope 搜索，不带 coverage 聚合字段。
- `export.scope_tree` 导出带 coverage totals/per-metric summaries 的 tree。

Source map:

```json
{
  "api_version": "xcov.v1",
  "action": "source.map",
  "target": {"session_id": "cov0"},
  "args": {"file": "rtl/ctrl.sv", "line": 123, "window": 3}
}
```

## Query 规则

- 只支持 glob：`*` 和 `?`。
- 不支持 regex、`[]`、`{}`、negative glob、lookaround；传入时应返回
  `REGEX_NOT_SUPPORTED` 或 `INVALID_PATTERN`。
- include 先匹配，exclude 后过滤，exclude 优先。
- 所有列表型 action 必须带 limit；大结果优先 `overflow:"to_file"` 和
  `output.mode:"both"`。
- MCP `xverif_cov_query(limits=..., output=...)` 会透传到 xcov；如果
  `args.limits/output` 已存在，以 action args 为准。
- `test:"each"` 当前明确不支持；不要依赖 merged fallback。
- functional coverage 可用 `levels` 过滤：`covergroup/coverpoint/cross/bin`。
- `cov.object.get` 当前是 exact lookup，可加 `include_children/max_children`，
  不要把它当完整 object subtree index。
- export 默认只允许相对 `output.path`，写到 `.xverif/xcov_exports/`；
  绝对路径必须显式设置 `output.allow_absolute_path:true`。

## 输出读取规则

- 默认 `xout` 只给 compact evidence；需要脚本字段时设
  `output.response_format:"json"` 或 MCP `output_format="json"`。
- 需要确认 request 形状时用 `xverif_cov_get_schema`；当前 P0 action 都有
  action-specific request/response schema。
- 先看 `summary.matched_count/returned/truncated/output_path`。
- coverage item 标准字段：`metric/type/name/full_name/covered/coverable/missing/count/status/evidence.file/evidence.line`。
- `covered()` 和 `count()` 不是同义词；coverage pct 用 `covered/coverable`。
- `excluded/unreachable/illegal` 必须作为 status 显式保留，不要静默丢弃。

## MCP 注意事项

- `XVERIF_MCP_ENABLE_COV=0` 会隐藏 xcov 工具。
- `XVERIF_MCP_BACKEND=direct|lsf` 同时适用于 xdebug/xcov stateful backend。
- `XVERIF_XCOV_BIN` 覆盖 `tools/xcov`。
- `XVERIF_XCOV_PYTHON` 覆盖 xcov Python runtime。
- `XVERIF_XCOV_VERDI_HOME` 覆盖 Verdi 安装路径。
- `XVERIF_XCOV_LOG_DIR` 覆盖 xcov 日志目录，默认 `~/.xverif/xcov`。
- `XVERIF_XCOV_LOG=0` 关闭日志。

xcov 日志参考 xdebug：public action log 在
`sessions/<session_id>/logs/actions.ndjson`，backend lifecycle/transport log
在 `backend/sessions/<session_id>/logs/`。日志只记录 request/response 摘要，
不会写完整 coverage `items` 大数组。

若 `xverif_cov_query` 返回 `SESSION_LOST`，不要自动 retry；先重新
`xverif_cov_session_open`，或缩小 query/limit 后再试。
