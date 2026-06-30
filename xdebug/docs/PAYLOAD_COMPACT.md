# xdebug 业务 Payload 压缩策略

xdebug 默认返回 compact JSON。compact 的目标不是保留所有中间过程，而是保留 AI 下一步调试决策需要的事实：结论、少量证据、异常摘要和可复查位置。

每个 action 的 compact 主路径都由 action-specific response schema 和 compact example 固化。schema 位于 `schemas/v1/actions/<action>.response.schema.json`，示例位于 `examples/responses/<action>.basic.json`。full/debug 或 `include_*` 返回可以包含额外字段，但不应移除 compact schema 中的关键 `summary` / `data` 结构。

## 输出档位

- `output.verbosity="compact"`：默认模式，只保留 summary、findings、examples、关键 graph/path 和 file/line evidence。
- `output.verbosity="full"`：尽量保留旧的大 payload，供旧脚本迁移或人工查看完整结构。
- `output.verbosity="debug"`：保留 full 内容，并允许输出过程型调试字段。

compact 默认不应出现下面这些大字段，除非请求里显式传入对应 `include_*`，或使用 `full/debug`：

- `expanded_queries`
- `parse_steps`
- `raw_edges`
- `all_samples`
- `all_events`
- `all_changes`
- `normal_transactions`
- `timeline`
- `source_text`
- `module_body`

## 通用控制字段

细节通过 `args` 里的 include 开关恢复：

```json
{
  "output": {"verbosity": "compact"},
  "args": {
    "include_source": false,
    "include_ast": false,
    "include_candidates": false,
    "include_trace": false,
    "include_expanded_queries": false,
    "include_raw_edges": false,
    "include_graph": false,
    "include_rows": false,
    "include_samples": false,
    "include_all_changes": false,
    "include_transactions": false,
    "include_beats": false,
    "include_accesses": false,
    "include_debug": false,
    "max_items": 20,
    "max_examples": 5
  }
}
```

旧的 `limits.max_rows`、`limits.max_events` 继续兼容。compact 模式下，除非显式请求完整明细，否则实现应优先使用较小默认值。

## 设计侧动作

### trace.driver / trace.load / trace.query

compact 默认回答四件事：谁驱动或加载信号、关键依赖是谁、证据在哪里、置信度如何。

默认形态：

```json
{
  "summary": {
    "signal": "top.u.ready",
    "mode": "driver",
    "result_count": 1,
    "confidence": "high",
    "truncated": false
  },
  "data": {
    "drivers": [
      {
        "signal": "top.u.ready",
        "kind": "continuous_assign",
        "rhs_signals": ["top.u.valid", "top.u.full"],
        "condition_signals": ["top.u.full"],
        "file": "rtl/foo.sv",
        "line": 123,
        "confidence": "high"
      }
    ]
  }
}
```

默认隐藏：

- 完整 assignment object
- normalized expression AST
- source text
- 低置信候选全集

需要时用 `include_source`、`include_ast`、`include_candidates` 恢复。

### trace.expand

compact 默认只保留图结构：

```json
{
  "summary": {
    "root_signal": "top.u.ready",
    "node_count": 12,
    "edge_count": 18,
    "truncated": false
  },
  "data": {
    "graph": {
      "nodes": [],
      "edges": []
    }
  }
}
```

默认隐藏：

- `trace`
- `expanded_queries`
- `raw_edges`
- dedup/relation/aggregate 详细统计

需要时用 `include_trace`、`include_expanded_queries`、`include_raw_edges`、`include_debug`。

### trace.path

compact 默认只返回路径答案：

```json
{
  "data": {
    "found": true,
    "paths": [
      {
        "signals": ["a", "b", "c"],
        "edges": [
          {"from": "a", "to": "b", "file": "rtl/foo.sv", "line": 10}
        ]
      }
    ]
  }
}
```

完整 graph 只在 `include_graph=true` 返回。

### source.context

compact 默认只返回定位事实：`file`、`line`、`symbol`、`context_kind`。源码文本需要 `include_source=true`；`context_lines` 默认最多 3。

## 波形侧动作

### value.at

compact 默认形态：

```json
{
  "data": {
    "signal": "top.u.valid",
    "time": "100ns",
    "value": "'h1",
    "known": true
  }
}
```

raw value object 和 signal metadata 需要 `include_raw` 或 `include_signal_meta`。

### value.batch_at / list.value_at

compact 默认返回 map，避免每个信号重复 time/session/format：

```json
{
  "summary": {
    "time": "100ns",
    "signal_count": 3,
    "x_or_z_count": 1
  },
  "data": {
    "values": {
      "top.u.valid": "1",
      "top.u.ready": "0",
      "top.u.data": "8'h12"
    }
  }
}
```

### event.find / event.export

compact 默认返回 count、first、last 和少量 examples。完整 rows 需要 `include_rows=true`。

### axi.query / axi.analysis

compact 默认返回 summary 和异常 findings。完整 transactions、beat rows 需要 `include_transactions=true` 或 `include_beats=true`。

### apb.query

compact 默认返回 error/slow access findings。完整 access rows 需要 `include_accesses=true`。

### signal.changes / statistics / trend / stability

`signal.changes` compact 默认返回 summary、row count、first/last/final value，不返回大量 `data.changes[]`；需要 rows 时显式传 `include_rows=true` 或 `include_all_changes=true`，并用 `mode:"head"|"tail"` 与 `limit` 控制方向和规模。只需要聚合信息时用 `aggregate_only=true`。

`signal.statistics` 有 `clock` 时返回 clock-sampled high/low cycles 和 activity；无 `clock` 时返回 raw value-change 统计，并通过 `sampling_mode` 标清语义。clock 模式下多 bit `first`/`final`/`min`/`max` 是 bit-string value object。完整 samples 需要 `include_samples=true`。

`counter.statistics` 按 clock edge 和 `vld` 条件统计最多 64 bit `cnt`，compact 默认返回 sample/valid 数、min/max/average、min/max 出现次数和首次时间。`cnt` 可以是单信号或 `{hi,lo}` 拼接。

### verify.conditions / expr.eval_at / window.verify

compact 默认返回 verdict 与 failed/unknown 条目。全部通过时应尽量极简。

### handshake.inspect / detect_anomaly

compact 默认只返回 findings/anomalies。timeline、cycle rows、正常扫描数据和 raw samples 需要显式 include 或 debug 输出。
