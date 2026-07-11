# CLI Surface

- xdebug 使用 `tools/xdebug --json -` 和完整 `xdebug.v1` envelope。
- xcov 使用 `tools/xcov --json -` 和完整 `xcov.v1` envelope。
- session 选择位于原生 `target.session_id`；不要使用 MCP query 的顶层 `session_id` 参数壳。
- 脚本字段读取使用 JSON；人类交互默认使用 compact/xout。
- 精确 target、args、limits 和 output 字段查询 action-specific schema。
