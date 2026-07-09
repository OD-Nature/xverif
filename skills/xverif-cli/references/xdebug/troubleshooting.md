# xdebug 排障

## 日志位置

- public actions：`~/.xdebug/sessions/<session_prefix>_<hash>/logs/actions.ndjson`
- stdio-loop：同目录 `stdio.ndjson`
- engine lifecycle/transport/crash：`~/.xdebug/engine/sessions/<hashed-session>/logs/`
- health：各 logs 目录下的 `log_health.ndjson`

常用命令：

```bash
xdebug log doctor --session <id> --json
xdebug log tail --session <id> --lines 40
xdebug log bundle --session <id> --out debug_bundle.redacted.tgz --redact
```

## 定位顺序

1. 看 `actions.ndjson`：action、target、elapsed_ms、最终 error。
2. stdout/ready/invalid JSON 问题看 `stdio.ndjson`。
3. `session.open`、`SESSION_UNHEALTHY`、`INTERNAL_ENGINE_FAILED` 看 engine `lifecycle.ndjson`。
4. socket/TCP/ping/daemon 连接问题看 `transport.ndjson`。
5. crash 或异常退出看 `crash_marker.ndjson` 和 `log_health.ndjson`。

## 常见错误

- `SESSION_DEAD` / `SESSION_UNHEALTHY`：session 不可复用，先 close/gc，再重新 open。
- `INTERNAL_ENGINE_FAILED`：看 lifecycle 是否 NPI init、design load、FSDB open 或 daemon ready 失败。
- `socket.connect.failed`：确认 socket_path、transport、namespace、文件是否存在。
- `socket.read.timeout`：检查查询是否过大、daemon 是否卡住、timeout 是否过短。
- invalid JSON / stdout pollution：看 `stdio.ndjson` 的 `stdout.pollution`、`ready.stdout_non_json`。
- license/NPI 连接失败：在沙箱外复跑，确认 Verdi/NPI 环境和 license server。

## 路径脱敏

对外共享日志默认使用：

```bash
xdebug log bundle --session <id> --out debug_bundle.redacted.tgz --redact
```

可用 `XDEBUG_LOG_PATH_MODE=basename|hash` 或 `XDEBUG_LOG_REDACT=1` 控制路径字段。
