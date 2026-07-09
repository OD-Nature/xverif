# xdebug JSON API 速查

本文说明 xdebug 原生 `xdebug.v1` action 的 request、target、output、transport 和示例。MCP、SDK-free wrapper、raw CLI 都复用这套 action 契约。

## MCP query 入口规则

有 MCP client 且 MCP SDK 可用时，AI agent 调用 xdebug 能力应优先走 MCP 托管 session：

1. 用 `xverif_debug_session_open` 打开 design/waveform/combined session。
2. 用 `xverif_debug_query` 传 `action`、`args`、`limits`、`output` 调用本文列出的 xdebug 原生 action。
3. 常规调试不要默认用 `xverif_debug_raw_request`；raw request 是 one-shot CLI 路径，不维护 MCP session manager、stdio-loop 或 LSF job 生命周期。
4. 只有需要完整 xdebug envelope 控制，或验证 raw CLI 行为时，才使用 `xverif_debug_raw_request`。
5. `xverif_debug_raw_request` 默认 `output_format` 是 `xout`，返回值是文本；需要脚本读取字段时显式请求 JSON。

MCP query 形态示例：

默认优先使用 xout 输出；以下示例省略 `output_format`，等价于让 MCP 使用默认的 `output_format:"xout"`。只有脚本需要稳定读取 JSON 字段，或专门验证 JSON response/schema 时，才显式写 `output_format:"json"`。JSON 片段展示 MCP tool 调用壳；直接调用 `xverif_debug_query` 时传外层 `args` 对象，写 `xverif_batch` 时整段 JSON 可作为一行请求。

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "value.batch_at",
    "args": {
      "time": "100ns",
      "clock": "top.u.clk",
      "signals": [
        "top.u.valid",
        "top.u.ready",
        "top.u.data"
      ],
      "format": "hex"
    },
    "output": {
      "verbosity": "compact"
    }
  }
}
```

需要 SDK-free loop wrapper 时读 `references/sdk-free-loop/`。只有 `xverif_debug_raw_request` 才把完整原生 xdebug request envelope 放进 MCP 参数 `request` 字段；常规 query 不写 `api_version` / `target`。

本文不是最终契约。最终契约优先级：

1. `xverif_debug_list_actions` 与 `xverif_debug_get_schema`
2. raw/native `actions` 和 `schema` action
3. `xdebug/schemas/v1/actions/*.schema.json`
4. `xdebug/examples/requests/*.basic.json` 与 `xdebug/examples/responses/*.basic.json`
5. 本 reference

不确定 action 参数或返回字段时，先查 runtime `actions` / `schema`，不要猜字段。

## 参数错误恢复

xdebug 有两层参数错误提示：

1. schema 层：字段缺失、类型错误、非法 enum、`additionalProperties:false` 禁止的多余字段、`anyOf` 必填组不满足。
2. action handler 层：schema 允许但语义非法的参数，例如反向 `time_range`、不存在的 signal/config、handler 内部枚举或时间解析失败。

两层错误都应尽量返回可恢复字段：

| 字段 | 用法 |
| --- | --- |
| `invalid_arg` | 直接指出错误字段路径，例如 `args.limit`、`args.time_range.end` |
| `expected` | 说明期望类型、范围或语义 |
| `allowed_values` | enum 或有限取值列表 |
| `did_you_mean` | 常见错字段的正确字段，例如 `args.query.limit` |
| `required_any_of` | 至少提供其中一组字段 |
| `correct_example` | 可复制的最小正确 request 模板 |

AI agent 调用失败时先按这些字段修 request。不要仅凭 `message` 猜测，也不要静默 fallback 到旧字段、旧 transport 或其它 action。

## 原生 envelope 对照

常规 MCP query 不写 `api_version`、`target` 或原生 `request_id`。完整原生 envelope 只放在 `xverif_debug_raw_request` 的 `request` 字段里，用于验证 CLI 行为或特殊 one-shot 控制：

```json
{
  "tool": "xverif_debug_raw_request",
  "args": {
    "request": {
      "api_version": "xdebug.v1",
      "request_id": "optional-id",
      "action": "trace.driver",
      "target": {
        "daidir": "simv.daidir",
        "fsdb": "waves.fsdb"
      },
      "args": {
        "signal": "top.u.ready"
      },
      "limits": {},
      "output": {
        "verbosity": "compact",
        "pretty": false
      }
    }
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

原生 envelope 字段说明：

| 字段 | 说明 |
| --- | --- |
| `api_version` | 固定使用 `xdebug.v1` |
| `request_id` | 可选，用于调用方关联请求 |
| `action` | 动作名，例如 `trace.driver`、`value.at` |
| `target` | `daidir`、`fsdb`、两者组合，或 `session_id`；MCP 常规 query 不写该字段 |
| `args` | action 参数 |
| `limits` | 行数、事件数、深度、路径数等限制 |
| `output` | 输出控制，默认 `verbosity:"compact"` |

## MCP 与原生 target 映射

| 原生 target | MCP 常规入口 |
| --- | --- |
| `{"daidir":"simv.daidir"}` | `xverif_debug_session_open(name, daidir="simv.daidir")` |
| `{"fsdb":"waves.fsdb"}` | `xverif_debug_session_open(name, fsdb="waves.fsdb")` |
| `{"daidir":"simv.daidir","fsdb":"waves.fsdb"}` | `xverif_debug_session_open(name, daidir="simv.daidir", fsdb="waves.fsdb")` |
| `{"session_id":"case_a"}` | `xverif_debug_query(session_id="case_a", action=..., args=...)` |

## session transport 字段

MCP 托管 session 由 wrapper 用 UDS 打开 backend session；`xverif_debug_session_open` 不暴露原生 `transport`、`bind_host`、`host` 或 `port` 参数。下面字段只适用于原生 CLI、SDK-free loop 或 `xverif_debug_raw_request(request=...)`。只有 UDS socket 不可达、容器/namespace 隔离或用户明确需要跨边界连接 daemon 时，才考虑 TCP。除非用户明确要求或项目文档明确指定，不要使用 `file` transport；遇到 `SESSION_UNHEALTHY child_exited`、旧 session 冲突或 UDS 问题时，不要把 `file` transport 当 fallback。

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

trace XOUT 源码窗口可用 `XDEBUG_TRACE_SOURCE_CONTEXT_LINES` 控制上下文行数（默认 3），并用 `XDEBUG_TRACE_SOURCE_MERGE_THRESHOLD_LINES` 控制同文件近距离源码块合并阈值（默认 10）。

`session.open` TCP 模板：

```json
{
  "tool": "xverif_debug_raw_request",
  "args": {
    "request": {
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
  }
}
```

MCP 显式 session 查询模板只用 `xverif_debug_query` 的 `session_id` 参数选择已打开 session；不要把 session 选择写到 action 的 `args.session_id`。

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "value.at",
    "args": {
      "signal": "top.clk",
      "time": "10ns",
      "clock": "top.clk"
    }
  }
}
```

file transport 是显式例外路径；需要时先读 `transport.md` 并保留用户要求或项目约束上下文，不在常规 JSON API 示例里提供可复制 fallback 模板。

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
    "include_beats": true,
    "include_debug": true
  }
}
```

限制字段要以 action-specific schema 为准。不要把 `args.limit` 当成所有 action 的通用字段；例如 APB/AXI query 使用 `args.query.limit`，active-driver 链深度使用 top-level `limits.max_depth`。常见形态如下：

```json
{
  "args": {
    "limit": 20
  },
  "limits": {
    "max_rows": 1000,
    "max_depth": 3,
    "max_paths": 10
  }
}
```

## 设计侧示例

### trace.driver

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "trace.driver",
    "args": {
      "signal": "top.u.ready"
    }
  }
}
```

### source.context

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "source.context",
    "args": {
      "file": "rtl/foo.sv",
      "line": 123,
      "symbol": "ready",
      "context_lines": 3
    }
  }
}
```

## 波形侧示例

### value.at

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "value.at",
    "args": {
      "signal": "top.u.valid",
      "time": "100ns",
      "clock": "top.clk",
      "format": "hex"
    }
  }
}
```

### value.batch_at

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "value.batch_at",
    "args": {
      "time": "100ns",
      "clock": "top.clk",
      "signals": [
        "top.u.valid",
        "top.u.ready",
        "top.u.data"
      ],
      "format": "hex"
    }
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
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "rc.generate",
    "args": {
      "config_path": "wave_view.json",
      "output": {
        "path": "signal.rc"
      }
    }
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
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "event.find",
    "args": {
      "expr": "valid && !ready && wait_count >= 512",
      "clock": "top.clk",
      "signals": {
        "valid": "top.u.valid",
        "ready": "top.u.ready",
        "wait_count": "top.u.dbg_wait_count"
      },
      "time_range": {
        "begin": "0ns",
        "end": "100us"
      },
      "mode": "last"
    }
  }
}
```

`event.find` / `event.export` 表达式支持 `!`、`&&`、`||`、`==`、`!=`、`<`、`<=`、`>`、`>=`。任一侧包含 X/Z 时，比较结果为 unknown，不会作为命中事件。

### event.export

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "event.export",
    "args": {
      "name": "if0",
      "expr": "valid && !ready",
      "time_range": {
        "begin": "0ns",
        "end": "100us"
      }
    }
  }
}
```

### verify.conditions

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "verify.conditions",
    "args": {
      "time": "100ns",
      "clock": "top.clk",
      "conditions": [
        {
          "signal": "top.u.valid",
          "op": "==",
          "value": "1"
        },
        {
          "signal": "top.u.ready",
          "op": "==",
          "value": "0"
        }
      ]
    }
  }
}
```

## 联合侧示例

### trace.active_driver

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "trace.active_driver",
    "args": {
      "signal": "top.u.ready",
      "time": "120ns",
      "include_control": true
    }
  }
}
```

## 错误处理

脚本或 batch 调用必须先检查返回对象的 `ok`。直接 CLI 场景使用 `xverif-cli`；MCP 中如果需要脚本读取 JSON 字段，才显式设置 `output_format:"json"`，然后读取返回 dict 的 `ok`、`error`、`summary` 和 `data`。

常见错误码：

```text
MISSING_FIELD
UNKNOWN_ACTION
INVALID_TARGET
SESSION_NOT_FOUND
SIGNAL_NOT_FOUND
TIME_SPEC_INVALID
TIME_RANGE_INVALID
WAVE_QUERY_FAILED
INTERNAL_ENGINE_FAILED
INTERNAL_ERROR
```

参数错误示例：

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "apb.query",
    "args": {
      "name": "apb0",
      "direction": "read",
      "limit": 10
    }
  }
}
```

该请求会返回 `invalid_arg:"args.limit"`、`did_you_mean:"args.query.limit"` 和 `correct_example`。修正后应写成：

```json
{
  "tool": "xverif_debug_query",
  "args": {
    "session_id": "case_a",
    "action": "apb.query",
    "args": {
      "name": "apb0",
      "direction": "read",
      "query": {
        "limit": 10
      }
    }
  }
}
```
