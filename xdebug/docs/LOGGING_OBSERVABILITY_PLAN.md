# xdebug 日志观测与防回归计划

更新时间：2026-06-19

本文是 xdebug / xverif 日志系统改造的执行依据。目标是在不污染
stdout/stderr、不破坏现有 JSON API 合同的前提下，把日志从“action 失败后查一查”
提升为能定位 MCP、stdio-loop、dispatcher、transport、backend engine、NPI/FSDB
整条链路问题的稳定证据系统。

## 当前代码核对结论

现有日志系统已经有基础骨架：

- `xdebug/src/core/logging/action_log.cpp` 已提供 action、lifecycle、transport 三类
  NDJSON 事件接口。
- `Dispatcher::dispatch()` 已记录 public action begin/end，并在失败时记录 compact
  request/response。
- backend engine server 已记录 NPI 初始化、设计/波形加载、endpoint 写入、UDS/TCP
  bind/listen 等生命周期事件。
- README 中已经定义了日志只写文件、不污染 stdout/stderr 的方向。

但当前实现仍有明显缺口：

- `request_id` 主要存在于 summary/context 中，没有作为顶层字段贯穿全链路。
- `stdio_loop.cpp` 的 invalid JSON、validate failed、ready、quit、stdin EOF 等协议事件
  不持久化落盘。
- dispatcher direct UDS connect/write/read/parse/timeout 路径缺少 transport root-cause log。
- engine `SIGSEGV` / `SIGABRT` handler 走了复杂 JSON log、stdio/file IO、NPI cleanup，
  不满足 crash-safe 约束。
- action 参数摘要只记录 `arg_keys`，复杂 debug action 失败时看不到关键
  `signal/time/scope/window`。
- `append_event()` 使用 `std::ofstream(..., std::ios::app)`，异常静默吞掉；缺少跨进程
  atomic append、log health、sidecar、rotation。
- Python MCP / LSF 层的 `stderr_tail`、ready timeout、stdout pollution、job id、cleanup
  主要留在内存或返回值里，没有统一结构化落盘。

## 目标链路

最终日志应能串起以下链路：

```text
MCP tool call
  -> stdio-loop protocol
    -> public dispatcher
      -> transport / session registry
        -> backend engine / NPI / FSDB
```

遇到真实问题时，日志必须能回答：

1. 请求是谁发的，`trace_id/request_id` 是什么，关键参数是什么。
2. 失败发生在 MCP、stdio-loop、dispatcher、transport、session registry、backend
   engine、NPI 还是 FSDB。
3. 对应 stdout/stderr tail、exit code、pid、LSF job id、session id、backend lifecycle
   和 crash marker 在哪里。

## 日志字段合同

所有结构化日志继续使用 NDJSON，一行一个 JSON object。新增字段只能向后兼容地增加，
不能删除现有字段。

基础字段：

```json
{
  "ts": "2026-06-19T12:00:00.000+0800",
  "event_id": "unique-event-id",
  "pid": 12345,
  "trace_id": "mcp-20260619-...",
  "request_id": "case0-17",
  "span_id": "engine-handle-...",
  "parent_span_id": "mcp-call-...",
  "layer": "mcp|public|backend",
  "component": "xverif-mcp|xdebug|engine|waveform|xcov",
  "session_id": "case0",
  "alias": "case0",
  "action": "value.at",
  "phase": "begin|end|error|crash",
  "ok": false,
  "elapsed_ms": 3812,
  "context": {}
}
```

字段规则：

- `request_id` 必须顶层化，不能只埋在 `context.request`。
- MCP 发起请求时生成或传递 `trace_id`，并写入 stdio-loop request。
- C++ dispatcher、backend transport、backend lifecycle 都从 request 中继承
  `trace_id/request_id`。
- `span_id` 用于本层事件；`parent_span_id` 用于把 MCP call、stdio request、dispatcher
  action、engine request 串起来。
- 没有 session 的事件写入 `adhoc`，但仍应保留 `trace_id/request_id`。

## Action 参数摘要 allowlist

成功事件默认只记录 compact summary；失败事件必须记录 action-specific allowlist 参数，
并保留裁剪后的 compact request/response。

第一批 allowlist：

| action | 必须记录的参数 |
| --- | --- |
| `value.at` | `signal`, `time`, `radix`, `format` |
| `value.batch_at` | `signals`, `time`, `radix`, `format`, `limit` |
| `event.find` | `signal`, `start`, `end`, `edge`, `limit` |
| `trace.active_driver` | `signal`, `time`, `max_depth`, `max_nodes`, `direction` |
| `trace.expand` | `signal`, `time`, `max_depth`, `max_nodes`, `direction` |
| `axi.*` | `interface`, `start`, `end`, `id`, `addr`, `channel`, `limit` |
| `apb.*` | `interface`, `start`, `end`, `addr`, `kind`, `limit` |
| `scope.*` | `scope`, `pattern`, `depth`, `limit` |

非 allowlist 的大字段继续走 `sanitize_for_log()`，不得把完整业务 payload 原样写入主
NDJSON。

## 阶段一：最短排障链路

阶段一优先解决最常见、最高收益的问题。

### 1. 顶层化 `trace_id/request_id`

- 扩展 C++ `base_event()` / log API，使事件支持顶层 correlation 字段。
- 从 request envelope 自动提取 `trace_id/request_id/span_id/parent_span_id`。
- dispatcher begin/end、transport event、backend lifecycle event 都保留这些字段。
- Python MCP 每个 tool call 生成 `trace_id`，query request 使用稳定 `request_id`。

### 2. stdio-loop 持久日志

新增 `stdio.ndjson`：

- 默认路径：`~/.xdebug/sessions/adhoc/logs/stdio.ndjson`。
- 能识别 session 后，同步写 `~/.xdebug/sessions/<session_id>/logs/stdio.ndjson`。
- 事件包括：
  - `loop.ready`
  - `loop.invalid_json`
  - `loop.validate_failed`
  - `request.begin`
  - `request.end`
  - `loop.quit`
  - `loop.stdin_eof`
  - `loop.stdout_write_failed`

stdio-loop 日志不得写 stdout/stderr。stdout 必须继续只承载 JSONL 协议。

### 3. dispatcher transport 日志

direct UDS 路径写 `transport.ndjson`：

- `socket.connect.begin`
- `socket.connect.ok`
- `socket.connect.failed`
- `socket.write.failed`
- `socket.read.timeout`
- `socket.read.failed`
- `socket.response_parse_failed`
- `socket.request.end`

fallback / spawn 路径写：

- `fallback.invoke.begin`
- `fallback.invoke.end`
- `fallback.invoke.failed`

每条事件至少包含 `request_id`、`action`、`session_id`、`socket_path` 或 fallback 摘要、
`timeout_ms`、errno/message、elapsed。

### 4. crash-safe marker

`SIGSEGV` / `SIGABRT` 不再走 JSON log、`fclose()`、`npi_end()`、复杂 allocator 或 stdio。

实现要求：

- server 启动时预打开 crash marker fd。
- signal handler 只调用 async-signal-safe 的 `write()` 和 `_exit()`。
- marker 内容使用单行纯文本，包含最小字段：

```text
signal_exit sig=11 pid=12345 session_id=case0 current_action=value.at request_id=case0-17
```

`SIGTERM` / `SIGINT` 可以走温和退出，但也应避免在 signal handler 内做复杂清理；优先设置
退出标志，让主循环完成 cleanup。

## 阶段二：日志写入可靠性

### 1. atomic append

`append_event()` 改为：

- `open(O_APPEND|O_CLOEXEC)`。
- 单次 `write()` 写完整 NDJSON line。
- 必要时对同一路径使用 `flock`。
- 写失败不影响 action 返回。

### 2. log health

新增 `log_health.ndjson`，记录日志系统自身问题：

- 目录创建失败。
- open/write/fsync 失败。
- 事件过大。
- sidecar 写失败。
- rotation 失败。

如果 health log 也不可写，action 仍不得失败；允许在 response `meta.log_warning` 中追加
非破坏性提示。

### 3. huge payload sidecar

主 NDJSON 不再把超大 context 整段替换为一句泛化字符串。超过阈值时：

- 主事件保留 envelope、summary、error、payload hash 和 sidecar 路径。
- 大 request/response 写入 `logs/actions_payload/<event_id>.request.json` /
  `logs/actions_payload/<event_id>.response.json`。

### 4. session manifest log map

`session.json` 增加 `logs` 对象：

```json
{
  "logs": {
    "public_actions": ".../actions.ndjson",
    "public_stdio": ".../stdio.ndjson",
    "backend_lifecycle": ".../lifecycle.ndjson",
    "backend_transport": ".../transport.ndjson",
    "backend_debug": ".../debug.log",
    "backend_crash_marker": ".../crash.marker",
    "mcp_session": ".../session.ndjson",
    "mcp_stdio": ".../stdio.ndjson",
    "mcp_lsf": ".../lsf.ndjson"
  }
}
```

### 5. rotation / retention

最小实现：

- `XDEBUG_LOG_MAX_BYTES`：单个日志文件大小上限。
- `XDEBUG_LOG_MAX_FILES`：保留滚动文件数量。
- 达到上限时按 `.1`, `.2` 滚动。

默认值应保守，不影响现有小规模使用。

### 6. environment snapshot

engine 启动早期写入 `lifecycle.ndjson` 的 `env.snapshot`，至少包含 hostname、cwd、
argv0、构建时间、EDA/LSF 环境摘要和 `LD_LIBRARY_PATH` hash。路径类字段必须经过已有
redaction 机制，长环境变量只能记录 hash 或摘要。

## 阶段三：MCP / LSF 结构化日志

新增 Python MCP logging 模块，默认路径：

- `~/.xverif/mcp/logs/server.ndjson`
- `~/.xverif/mcp/sessions/<alias>/session.ndjson`
- `~/.xverif/mcp/sessions/<alias>/stdio.ndjson`
- `~/.xverif/mcp/sessions/<alias>/lsf.ndjson`

记录范围：

- MCP tool call begin/end。
- `McpSessionManager.open/query/close/list`。
- `XdebugLoopSession.open/query/abort/close`。
- `JsonlProcess.start/wait_ready/request/read_json_response/terminate`。
- stdout pollution、ready timeout、response timeout、process exited before ready。
- stderr tail、pid、return code、job name、job id。
- LSF `bsub` argv hash、queue、resource、job id parse、bkill cleanup。

示例事件：

```json
{
  "tool": "xverif_debug_query",
  "alias": "case0",
  "trace_id": "mcp-20260619-...",
  "request_id": "case0-17",
  "backend": "xdebug",
  "launcher": "lsf",
  "pid": 12345,
  "lsf_job_id": "987654",
  "phase": "request.end",
  "elapsed_ms": 3812,
  "ok": false,
  "stderr_tail": ["..."]
}
```

## Redaction 与 bundle

新增配置：

- `XDEBUG_LOG_PATH_MODE=full|basename|hash`，默认 `full`。
- `XDEBUG_LOG_REDACT=0|1`，默认 `0`。
- `XVERIF_MCP_LOG_DIR`，默认 `~/.xverif/mcp`。

后续新增 CLI：

- `xdebug log tail --session <id>`
- `xdebug log doctor --session <id>`
- `xdebug log bundle --session <id> --out debug_bundle.tgz`

`bundle` 对外分享默认启用路径脱敏；本地排障默认保留完整路径。

## 针对性防回归测试

新增测试目标：`make -C xdebug log-test`。

该目标只跑日志相关快速测试，作为修改日志字段、路径、stdio-loop、dispatcher transport、
MCP launcher 后的最小防回归入口。

### C++ log unit tests

扩展 `xdebug/tests/unit/test_action_log.cpp`：

- 每条 log 必含 `ts/event_id/pid/layer/component/session_id/phase/ok`。
- `request_id` 是顶层字段，不能只存在于 `context.request`。
- `value.at` 摘要包含 `signal/time/radix`。
- `trace.active_driver` 摘要包含 `signal/time/max_depth/max_nodes/direction`。
- 成功事件只记录 compact summary。
- 失败事件记录 allowlist、`request_compact`、`response_compact`。
- heavy payload 不进入主 NDJSON。
- huge payload 生成 sidecar，主 NDJSON 保留 sidecar 路径和 hash。
- `session.json` 包含 `logs` map。

新增并发 append unit：

- N 个进程同时写同一个 NDJSON。
- 测试逐行 parse，断言无半行、交错、非法 JSON。

新增 log health unit：

- 模拟不可写目录或 open/write 失败。
- action 不失败；可写 health log 时出现 `log_health.ndjson` 事件。

### stdio-loop tests

扩展 `xdebug/tests/session/test_stdio_loop_lifecycle.py`：

- malformed JSON 返回 stdout error，同时 `stdio.ndjson` 有 `loop.invalid_json`。
- unsupported api version / validate failed 不进 dispatcher，但 `stdio.ndjson` 有
  `loop.validate_failed`。
- 正常 request 有 `request.begin` / `request.end`，并带 `request_id`。
- `stdio.quit` 有 `loop.quit`。
- stdin EOF 有 `loop.stdin_eof`。
- 保留 `stdout_is_jsonl_only` 断言，确认日志不污染 stdout。

### transport tests

扩展现有 UDS timeout 测试：

- fake hung socket 触发 read timeout。
- 读取 backend/public transport log，断言有 connect/write/read timeout 事件。
- 验证事件包含 `socket_path`、`timeout_ms`、`request_id`、`action`。

新增 fake socket cases：

- connect failed。
- peer close before response。
- engine 返回 invalid JSON。
- 非 UDS / fallback path。

每个 case 都断言 action response 仍保持现有合同，同时 transport root cause 落盘。

### crash marker tests

新增受控 crash 测试：

- 使用 test hook 或 mock action 触发 `SIGABRT`。
- 断言退出码为 `134`。
- 断言 crash marker 存在，并包含 signal、pid、session_id、current action、request_id。
- 不要求 crash 路径生成合法 JSON lifecycle event。

### MCP / LSF tests

扩展 `xverif_mcp/tests/test_stdio_loop_session_lifecycle.py`：

- fake process exit before ready：`session.ndjson` 记录 open failed、rc、stderr tail。
- fake ready timeout：`session.ndjson` 记录 timeout。
- fake crash mid-query：记录 request begin/end、SESSION_LOST、cleanup。
- fake stdout pollution：`stdio.ndjson` 记录污染摘要和 request id。
- fake LSF ready timeout：`lsf.ndjson` 记录 bsub argv hash、queue、resource、job name/job id、
  cleanup/bkill。

## 回归入口与执行约束

保留现有回归入口：

- `make -C xdebug schema-test`
- `make -C xdebug unit-test`
- `make -C xdebug contract-test`
- `make -C xdebug combined-test`
- `make -C xdebug test-session`
- `make -C xdebug test-mcp-direct`
- `make -C xdebug test-mcp-fake-lsf`
- `make -C xdebug test-realdata-smoke`
- `make -C xdebug test-vip`
- `make -C xdebug test-nightly`

新增快速入口：

```bash
make -C xdebug log-test
```

执行约束：

- 纯编译、纯 unit、fake process、isolated HOME 的日志测试可以在普通环境执行。
- 涉及仿真、Verdi/VCS/NPI license、真实 FSDB/daidir、真实 LSF、backend engine 实机启动、
  Unix domain socket 或 file transport 实机验证的命令，统一放到 Codex 沙箱外执行。
- 沙箱内出现 license 连接、UDS bind、`SESSION_UNHEALTHY: child_exited` 等环境型失败时，
  不据此判断功能回归。

## 文档与 skill 同步

实现完成后同步更新：

- `xdebug/README.md`：日志路径、排障顺序、`log-test`。
- `skills/xverif/SKILL.md`：agent 使用 xverif 工具和日志排障的最短路径。
- `skills/xverif/references/xdebug/troubleshooting.md`：xdebug 原生日志路径和 bundle/doctor/tail 说明。
- `skills/xverif/references/mcp/troubleshooting.md`、`skills/xverif/references/sdk-free-xdebug/troubleshooting.md`：
  MCP / SDK-free wrapper 日志路径和 ready timeout、stdout pollution、job id 排障方式。
- `xverif_mcp/README.md`：MCP / LSF 日志路径、ready timeout、stdout pollution、job id
  排障方式。

## 实施顺序

1. 先落地阶段一和对应 targeted tests。
2. 跑 `make -C xdebug log-test`，再跑 `unit-test` / `contract-test`。
3. 涉及 backend / NPI / FSDB 的变更按授权在沙箱外跑 `test-session`、
   `combined-test`、`test-realdata-smoke` 或 `test-vip`。
4. 阶段二实现 atomic append、health、sidecar、rotation。
5. 阶段三实现 MCP / LSF structured log 和 log bundle/tail/doctor。
6. 最后同步 README、skill、MCP README，并更新测试状态文档。
