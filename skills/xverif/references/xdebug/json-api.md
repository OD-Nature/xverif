# xdebug JSON API 速查

本文说明 xdebug 原生 `xdebug.v1` action 的 request、target、output、transport 和示例。MCP、SDK-free wrapper、raw CLI 都复用这套 action 契约。

## MCP query 入口规则

有 MCP client 且 MCP SDK 可用时，AI agent 调用 xdebug 能力应优先走 MCP 托管 session：

1. 用 `xverif_debug_session_open` 打开 design/waveform/combined session。
2. 用 `xverif_debug_query` 传 `action`、`args`、`limits`、`output` 调用本文列出的 xdebug 原生 action。
3. 常规调试不要默认用 `xverif_debug_raw_request`；raw request 是 one-shot CLI 路径，不维护 MCP session manager、stdio-loop 或 LSF job 生命周期。
4. 只有需要完整 xdebug envelope 控制，或验证 raw CLI 行为时，才使用 `xverif_debug_raw_request`。

MCP query 形态示例：

```json
{
  "session_id": "case_a",
  "action": "value.batch_at",
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  },
  "limits": {"max_items": 100},
  "output": {"verbosity": "compact"},
  "output_format": "json"
}
```

需要 SDK-free wrapper 或 raw CLI 时，再把同一 action 放进本文的原生 JSON request envelope。

本文不是最终契约。最终契约优先级：

1. `xdebug --json -` 调用 `actions`
2. `schema` action 返回的 action-specific schema
3. `xdebug/schemas/v1/actions/*.schema.json`
4. `xdebug/examples/requests/*.basic.json` 与 `xdebug/examples/responses/*.basic.json`
5. 本 reference

不确定 action 参数或返回字段时，先查 runtime `actions` / `schema`，不要猜字段。

## 请求 envelope

```json
{
  "api_version": "xdebug.v1",
  "request_id": "optional-id",
  "action": "trace.driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {},
  "limits": {},
  "output": {
    "verbosity": "compact",
    "pretty": false
  }
}
```

## Action-specific schema

所有当前公开且未移除的 action 都有独立 schema 和 basic example：

```text
xdebug/schemas/v1/actions/<action>.request.schema.json
xdebug/schemas/v1/actions/<action>.response.schema.json
xdebug/examples/requests/<action>.basic.json
xdebug/examples/responses/<action>.basic.json
```

调用 `actions` 可以在 `data.actions[]` 中读取 `request_schema`、`response_schema`、`request_examples`、`response_examples`。AI agent 需要精确契约时应使用这些 action-specific 文件；通用 `xdebug.request.schema.json` / `xdebug.response.schema.json` 只描述 envelope。

字段说明：

| 字段 | 说明 |
| --- | --- |
| `api_version` | 固定使用 `xdebug.v1` |
| `request_id` | 可选，用于调用方关联请求 |
| `action` | 动作名，例如 `trace.driver`、`value.at` |
| `target` | `daidir`、`fsdb`、两者组合，或 `session_id` |
| `args` | action 参数 |
| `limits` | 行数、事件数、深度、路径数等限制 |
| `output` | 输出控制，默认 `verbosity:"compact"` |

## target 行为矩阵

| target | 路由 |
| --- | --- |
| `{"daidir":"simv.daidir"}` | 设计侧 |
| `{"fsdb":"waves.fsdb"}` | 波形侧 |
| `{"daidir":"simv.daidir","fsdb":"waves.fsdb"}` | 联合侧，并允许回退到设计/波形 action |
| `{"session_id":"case_a"}` | 使用已打开 session 的资源集合 |

## session transport 字段

默认 transport 是 `uds`。只有 UDS socket 不可达、容器/namespace 隔离或用户明确需要跨边界连接 daemon 时，才使用 TCP。本机或登录机无法连接计算节点 TCP 端口时，使用 `file` transport。

| 字段 | 位置 | 说明 |
| --- | --- | --- |
| `transport` | `args` 或 `target` | `uds` / `tcp` / `file`，默认 `uds`，可由 `XDEBUG_TRANSPORT` 控制 |
| `bind_host` / `bind` | `args` 或 `target` | daemon listen 地址；本机 TCP 推荐 `127.0.0.1` |
| `host` | `args` 或 `target` | client 连接地址；远程/跨容器时应是 agent 可达地址 |
| `port` | `args` 或 `target` | TCP 端口；`0` 或省略表示自动分配 |
| `file_dir` | response/log | file transport 的 session 交换目录，由 xdebug 生成 |

`XDEBUG_TRANSPORT=uds|tcp|file` 只影响新建 session；JSON 中显式的 `args.transport` 或 `target.transport` 优先级更高。

file transport v2 使用以下状态目录，不依赖 file lock：

```text
file transport directory:
  requests/    client-published pending requests
  claims/      worker-claimed running requests
  responses/   unread responses
  done/        archived request/claim/response history
  failed/      client_timeout / expired / stale_claim / invalid_request
  tmp/         atomic write temp files
  heartbeat/   worker liveness files
```

普通请求默认等待 300 秒，可用 `XDEBUG_FILE_TRANSPORT_TIMEOUT_MS` 调整；ping/quit 默认等待 2 秒，可用 `XDEBUG_FILE_TRANSPORT_PING_TIMEOUT_MS` 调整。`XDEBUG_FILE_KEEP_HISTORY=1` 默认保留 `done/failed` 证据链。`XDEBUG_FILE_MAX_JSON_BYTES` 限制单个 request/response JSON 文件大小，`XDEBUG_FILE_CLAIM_TIMEOUT_MS` 控制 stale claim 判定。

`session.open` TCP 模板：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_tcp",
    "transport": "tcp",
    "bind_host": "127.0.0.1",
    "port": 0
  }
}
```

显式 session 查询模板：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {
    "session_id": "case_a",
    "transport": "tcp",
    "bind_host": "127.0.0.1",
    "port": 0
  },
  "args": {
    "signal": "top.clk",
    "time": "10ns"
  }
}
```

`session.open` file 模板：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_file",
    "transport": "file"
  }
}
```

## output 与 include

输出档位：

```json
{
  "output": {
    "verbosity": "compact",
    "pretty": false,
    "include_suggestions": false
  }
}
```

设计侧 include：

```json
{
  "args": {
    "include_source": true,
    "include_ast": true,
    "include_candidates": true,
    "include_trace": true,
    "include_expanded_queries": true,
    "include_raw_edges": true,
    "include_graph": true,
    "include_debug": true
  }
}
```

波形侧 include：

```json
{
  "args": {
    "include_raw": true,
    "include_signal_meta": true,
    "include_rows": true,
    "include_samples": true,
    "include_all_changes": true,
    "include_transactions": true,
    "include_beats": true,
    "include_accesses": true,
    "include_debug": true
  }
}
```

通用限制：

```json
{
  "args": {
    "max_items": 20,
    "max_examples": 5
  },
  "limits": {
    "max_rows": 1000,
    "max_events": 1000,
    "max_samples": 1000000,
    "max_depth": 3,
    "max_paths": 10
  }
}
```

## 设计侧示例

### trace.driver

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {"daidir": "simv.daidir"},
  "args": {"signal": "top.u.ready"}
}
```

### trace.path

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.path",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "from_signal": "top.u.full",
    "to_signal": "top.u.ready"
  },
  "limits": {
    "max_depth": 5,
    "max_paths": 10
  }
}
```

### source.context

```json
{
  "api_version": "xdebug.v1",
  "action": "source.context",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "file": "rtl/foo.sv",
    "line": 123,
    "symbol": "ready",
    "context_lines": 3
  }
}
```

## 波形侧示例

### value.at

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"session_id": "case_a"},
  "args": {
    "signal": "top.u.valid",
    "time": "100ns",
    "format": "hex"
  }
}
```

### value.batch_at

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {"session_id": "case_a"},
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  }
}
```

`value.batch_at` 部分缺失仍返回 ok；检查 `summary.missing_by_reason` 和 full 输出每个 row 的 `status/reason`。需要 xbit 切字段时给 `value.at` 或 `value.batch_at` 加：

```text
"slice_hint": {"chunk_width": 32, "count": 4}
```

响应里的 `xbit_hints.commands[]` 可直接交给 `tools/xbit`。

### rc.generate

```json
{
  "api_version": "xdebug.v1",
  "action": "rc.generate",
  "target": {"session_id": "case_a"},
  "args": {
    "config_path": "wave_view.json",
    "rc_path": "signal.rc",
    "include_preview": true
  }
}
```

`config_path` 指向 JSON 配置。配置中信号写点分路径，如 `top.u.sig[3:0]`；生成 rc 时转成 `/top/u/sig[3:0]`。支持普通 `addSignal`、`addSignal -w analog`、`addExprSig`、group/subgroup 和 user marker。不写 `openDirFile` / `activeDirFile`。

`addExprSig` 推荐：

```json
{
  "name": "aw_fire",
  "bit_size": 1,
  "notation": "UUU",
  "expr": "$valid & $ready",
  "signals": {
    "valid": "top.u_axi.awvalid",
    "ready": "top.u_axi.awready"
  }
}
```

### event.find inline

```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {"session_id": "case_a"},
  "args": {
    "expr": "valid && !ready",
    "clk": "top.clk",
    "signals": {
      "valid": "top.u.valid",
      "ready": "top.u.ready"
    },
    "time_range": {"begin": "0ns", "end": "100us"},
    "mode": "last"
  }
}
```

### event.export

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "if0",
    "expr": "valid && !ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    }
  }
}
```

### verify.conditions

```json
{
  "api_version": "xdebug.v1",
  "action": "verify.conditions",
  "target": {"session_id": "case_a"},
  "args": {
    "time": "100ns",
    "conditions": [
      {"signal": "top.u.valid", "op": "==", "value": "1"},
      {"signal": "top.u.ready", "op": "==", "value": "0"}
    ]
  }
}
```

## 联合侧示例

### trace.active_driver

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "signal": "top.u.ready",
    "requested_time": "120ns",
    "include_control": true
  }
}
```

## 错误处理

脚本必须先检查 `ok`：

```bash
tools/xdebug --json - < request.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["ok"], d.get("error"))'
```

常见错误码：

```text
MISSING_FIELD
UNKNOWN_ACTION
INVALID_TARGET
SESSION_NOT_FOUND
SIGNAL_NOT_FOUND
TIME_SPEC_INVALID
WAVE_QUERY_FAILED
INTERNAL_ENGINE_FAILED
INTERNAL_ERROR
```
