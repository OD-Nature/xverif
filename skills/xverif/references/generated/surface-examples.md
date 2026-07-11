# 生成的 Surface 示例

Canonical source: `skills/xverif/specs/examples.yaml`。

## CLI

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "time": "100ns",
    "clock": "top.clk",
    "signals": [
      "top.u.valid",
      "top.u.ready",
      "top.u.full"
    ]
  }
}
```

## MCP

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
        "top.u.full"
      ]
    }
  }
}
```

## SDK-free loop

```json
{
  "method": "debug.query",
  "params": {
    "session": "case_a",
    "action": "value.batch_at",
    "args": {
      "time": "100ns",
      "clock": "top.clk",
      "signals": [
        "top.u.valid",
        "top.u.ready",
        "top.u.full"
      ]
    }
  }
}
```
