# MCP Surface

- xdebug：`xverif_debug_session_open(name, fsdb=None, daidir=None, run_manifest=None)` → `xverif_debug_query(session_id, action, args, limits, output_format)` → `xverif_debug_session_close`。
- xcov：`xverif_cov_session_open(name, vdb, run_manifest=None)` → `xverif_cov_query(session_id, action, args, limits, output_format)` → `xverif_cov_session_close(session_id)`。
- action 参数只放内层 `args`；不传原生 `api_version/target/output` envelope。
- 不确定时使用 `xverif_tools`、action catalog 和 schema discovery。
- session/transport/LSF/timeout 排障转 `xverif-admin`，不自动 reopen 或 fallback。
- `run_manifest` 可选；提供时必须是已发布的对应 `*.run-manifest.v1`，资源路径相对
  manifest 文件，校验不匹配会返回 `RESOURCE_PROVENANCE_MISMATCH`，不会启动后端。
