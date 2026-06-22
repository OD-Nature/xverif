# xcov coverage 查询

xcov 查询 VCS/Verdi coverage database（`simv.vdb`、`merged.vdb`）。它负责 coverage evidence，不负责自动解释 hole 根因或生成补测策略。

## 何时使用

- 查询 line/toggle/branch/condition/fsm/assert/functional coverage。
- 查 coverage holes，并保留 file/line evidence。
- 按 hierarchy scope 查看 summary、children、scope search。
- 按源码 file/line/window 反查 coverage item。
- 导出 coverage evidence 为 json/ndjson/csv/md。

## 入口

优先 MCP：

- `xverif_cov_session_open`
- `xverif_cov_query`
- `xverif_cov_session_close`
- `xverif_cov_list_actions`
- `xverif_cov_get_schema`
- `xverif_cov_raw_request`

命令行：

```bash
tools/xcov --json -
tools/xcov --stdio-loop
```

真实 NPI coverage 查询需要 Synopsys license；受限沙箱内 license 可能不可达。

## 常用请求

open：

```json
{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"merged.vdb"},"args":{"name":"cov0"}}
```

holes：

```json
{"api_version":"xcov.v1","action":"cov.holes","target":{"session_id":"cov0"},"args":{"metrics":["line","toggle","branch","condition","fsm","assert","functional"],"limits":{"max_items":100}}}
```

source map：

```json
{"api_version":"xcov.v1","action":"source.map","target":{"session_id":"cov0"},"args":{"file":"rtl/ctrl.sv","line":123,"window":3}}
```

## 读取规则

- 先看 `ok`。
- 看 `summary.matched_count/returned/truncated/output_path`。
- coverage item 关注 `metric/type/name/full_name/covered/coverable/missing/status/evidence.file/evidence.line`。
- coverage pct 用 `covered/coverable`，不要用 hit count 代替覆盖率。
- 保留 `excluded/unreachable/illegal` 状态，不要误判为普通 hole。

## 排障

- license/NPI 错误：在沙箱外确认 Verdi/NPI 和 license server。
- action 参数不确定：先用 `xverif_cov_list_actions` 和 `xverif_cov_get_schema`。
- 大结果：设置 limit，必要时 `overflow:"to_file"` 或 output path。
- MCP/LSF/session 问题：读 MCP 或 SDK-free 对应 troubleshooting。
