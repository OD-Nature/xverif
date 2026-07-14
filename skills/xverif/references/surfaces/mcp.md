# MCP Surface

- xdebug：`xverif_debug_session_open(name, fsdb=None, daidir=None, run_manifest=None)` → `xverif_debug_query(session_id, action, args, limits, output_format)` → `xverif_debug_session_close`。
- xcov：`xverif_cov_session_open(name, vdb, run_manifest=None)` → `xverif_cov_query(session_id, action, args, limits, output_format)` → `xverif_cov_session_close(session_id)`。
- action 参数只放内层 `args`；不传原生 `api_version/target/output` envelope。
- 不确定时使用 `xverif_tools`、action catalog 和 schema discovery。

## Schema discovery

`xverif_debug_get_schema(action, kind="request", view="mcp")` 默认返回可直接用于 MCP
query 的投影：`args_schema`、`limits_schema`、递归 `parameter_guide`、展开的
`constraints`、`minimal_call`、内嵌 examples、适用/禁用边界、替代 action 与 response
guide。不要把它返回的 native schema 再套入 `xverif_debug_query.args`。

- `view="mcp"`：默认；用于构造 query tool 的内层 args/limits。
- `view="args"`：只查看 action-specific args 合同。
- `view="native"`：查看 CLI/stdio 完整 envelope，仅在原生调用时使用。
- `kind="response", view="response"`：查看 response schema 和主要字段/完整性解释。
- session/transport/LSF/timeout 排障转 `xverif-admin`，不自动 reopen 或 fallback。
- `run_manifest` 可选；提供时必须是已发布的对应 `*.run-manifest.v1`，资源路径相对
  manifest 文件，校验不匹配会返回 `RESOURCE_PROVENANCE_MISMATCH`，不会启动后端。
- xdebug 完成仿真后可用 `xdebug/tools/publish_run_manifest.py --fsdb waves.fsdb
  --output run-manifest.json` 原子发布 manifest；MCP session 元数据中的
  `resource_identity` 同时报告路径摘要、stat 快照和声明的 manifest 摘要，不能把路径摘要当作内容摘要。
