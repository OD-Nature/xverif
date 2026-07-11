# xdebug Log 系统

xdebug 的 log 是工具可观测性合同的一部分。任何 session、transport、engine、runtime 错误都应能从结构化日志中定位阶段和原因。

## 日志原则

- stdout 保留给 JSON/XOUT 结果。
- stderr 可用于人类可读错误，但不能成为机器合同。
- 结构化日志使用 ndjson，便于 grep、jq、agent 读取。
- error response 应给出 error code，log 应给出 phase、context、路径和底层错误。

## 常见日志类型

### Action log

用途：

- 记录 public action 请求、响应、错误、耗时、resource、session。

常见位置：

- 有 session：`~/.xdebug/sessions/<session_id>/logs/actions.ndjson`
- 无 session 或解析失败：`~/.xdebug/sessions/adhoc/logs/actions.ndjson`

使用场景：

- JSON parse/validate 失败。
- action 返回错误但 stdout 信息不够。
- 需要确认 request 是否到达 frontend。

### Lifecycle log

用途：

- 记录 engine 启动、ready、NPI/FSDB 初始化、crash、restart、quit、gc。

常见位置：

- `~/.xdebug/engine/sessions/<hashed-session>/logs/lifecycle.ndjson`

使用场景：

- `SESSION_UNHEALTHY`
- `child_exited`
- engine ready timeout
- NPI/FSDB 初始化失败

### Transport log

用途：

- 记录 UDS/TCP/file transport 的 bind、connect、ping、query、timeout、endpoint。

常见位置：

- `~/.xdebug/engine/sessions/<hashed-session>/logs/transport.ndjson`

使用场景：

- `SESSION_TRANSPORT_FAILED`
- UDS socket 不可达
- TCP connect refused/timeout
- file transport request expired/stale claim

### Daemon debug log

用途：

- 记录 engine daemon 的文本细节。

常见位置：

- 对应 engine session 目录下的 `debug.log`

使用场景：

- 结构化 lifecycle/transport 还不够定位时。
- 需要底层库或子进程输出上下文时。

## 排障顺序

1. 看 action response 的 error code 和 message。
2. 查 action log，确认 request envelope、action、target、session、耗时。
3. 查 lifecycle log，确认 engine 是否启动、ready、crash。
4. 查 transport log，确认 bind/connect/ping/query 阶段。
5. 查 daemon debug log，补充底层细节。
6. 若涉及沙箱、网络、license、文件系统，做 sandbox-vs-host 对照。

## 字段要求

新增 log event 时应包含：

- `timestamp`
- `phase`
- `event`
- `session_id` 或 backend session key
- `action`
- `status`
- `error_code`
- `message`
- `elapsed_ms`
- endpoint/path 等资源上下文

禁止：

- 写入 token、cookie、license 内容。
- 在用户可见回答中暴露不必要的本机绝对路径。
- 只写自由文本、不写结构化字段。

## 修改 log 的测试

- C++ log helper 变化：跑相关 unit test，例如 action log/file exchange/process runner。
- session lifecycle 变化：跑 `pytest --xverif-gate regression --xverif-suite xdebug.session`。
- transport 变化：跑 session/MCP focused tests。
- 如果测试需要真实 LSF/license/VIP，按根目录 `AGENTS.md` 规则在沙箱外执行。
