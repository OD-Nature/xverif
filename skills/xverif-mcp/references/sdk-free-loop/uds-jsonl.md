# SDK-free UDS JSONL 协议

启动 server：

```bash
XVERIF_LOOP_SOCKET=/tmp/xverif-loop.sock tools/xverif-loop-server
```

发送单个请求：

```bash
tools/xverif-loop-client --socket /tmp/xverif-loop.sock --json \
  '{"id":"1","method":"debug.session.open","params":{"name":"s0","fsdb":"waves.fsdb"}}'
```

也可从 stdin 发送 JSONL。

## 请求格式

```json
{"id":"1","method":"debug.query","params":{"session":"s0","action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}
```

成功：

```json
{"id":"1","ok":true,"result":{}}
```

失败：

```json
{"id":"1","ok":false,"error":{"code":"SESSION_LOST","message":"..."}}
```

## 方法

- `server.ping`
- `server.shutdown`
- `debug.session.open`
- `debug.session.list`
- `debug.session.close`
- `debug.query`
- `cov.session.open`
- `cov.session.list`
- `cov.session.close`
- `cov.query`

`debug.query` 和 `cov.query` 会把 `action/args/limits/output/output_format` 转给当前 managed session，并固定 target 为该 session。不要用它们发送 lifecycle raw request。

## 环境变量

- `XVERIF_LOOP_SOCKET`：socket 路径。
- `XVERIF_LOOP_BACKEND=direct|lsf`：启动模式。
- `XVERIF_LOOP_LOG_DIR`：日志根目录。
- `XVERIF_LOOP_STARTUP_TIMEOUT_SEC`：open timeout。
- `XVERIF_LOOP_REQUEST_TIMEOUT_SEC`：query timeout。
- `XVERIF_LOOP_CLOSE_TIMEOUT_SEC`：close timeout。
