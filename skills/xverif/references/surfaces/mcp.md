# MCP Surface

- xdebug：`xverif_debug_session_open` → `xverif_debug_query(session_id, action, args, limits, output_format)` → `xverif_debug_session_close`。
- xcov：`xverif_cov_session_open` → `xverif_cov_query(session_id, action, args, limits, output_format)` → `xverif_cov_session_close(session_id)`。
- action 参数只放内层 `args`；不传原生 `api_version/target/output` envelope。
- 不确定时使用 `xverif_tools`、action catalog 和 schema discovery。
- session/transport/LSF/timeout 排障转 `xverif-admin`，不自动 reopen 或 fallback。
