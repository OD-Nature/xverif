# xdebug JSON API 速查

本文是 skill 内的 API 速查。主 skill 只保留工作流；需要字段细节时再读取本文。

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

### trace.graph

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.graph",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 3,
    "max_results": 80
  }
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
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  }
}
```

`value.batch_at` 部分缺失仍返回 ok；检查 `summary.missing_by_reason` 和 full 输出每个 row 的 `status/reason`。需要 xbit 切字段时给 `value.at` 或 `value.batch_at` 加：

```json
"slice_hint": {"chunk_width": 32, "count": 4}
```

响应里的 `xbit_hints.commands[]` 可直接交给 `tools/xbit`。

### rc.generate

```json
{
  "api_version": "xdebug.v1",
  "action": "rc.generate",
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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
