# xdebug Agent 使用指南

xdebug 用于从设计数据库、波形数据库，或两者联合视图中获取结构化 JSON 事实。

## 第一原则

先查 compact，再按需打开细节。

```json
{
  "output": {"verbosity": "compact"}
}
```

只有在 compact 结果缺少继续推理所需字段时，才使用具体 `include_*`。`full/debug` 主要用于维护工具或排查工具本身。

## Target 选择

- `target.daidir`：设计因果关系，如 driver/load、graph、path、source、FSM/counter/sequential。
- `target.fsdb`：波形事实，如 value、event、protocol transaction、window、anomaly、handshake。
- 两者同时提供：把波形现象连接到设计因果。

如果只提供一个资源，xdebug 会回退到对应的原 xtrace 或 xwave 能力边界。

## 信号发现

xdebug 负责 exact resolve 和事实查询。候选信号名应先用外部 `rg` 或 grep 在 RTL/日志中发现，再把精确路径传给 xdebug。

不要把 broad fuzzy search 当作 xdebug 的第一步。

## 推荐调试流程

1. 用 `value.at`、`signal.statistics`、`counter.statistics`、`signal.changes` 或 `window.verify` 确认波形症状：周期统计用 `signal.statistics`，counter min/max/average 用 `counter.statistics`，跳变时间线用 `signal.changes`，窗口保持用 `window.verify`。
2. 对精确信号执行 `trace.driver` 或 `trace.load`。
3. 用 `trace.expand` 或 `trace.path` 连接关键依赖。
4. 只有在最终取证时，对 `source.context` 打开 `include_source=true`。
5. 只有 compact findings 不够时，才请求 `include_trace`、`include_rows` 或 `include_transactions`。

## Payload 纪律

默认不要请求：

- `expanded_queries`
- `all_samples`
- `all_events`
- `all_changes`
- `normal_transactions`
- `timeline`
- `source_text`
- `module_body`

优先使用：

- `summary`
- `findings`
- `examples`
- `evidence.file`
- `evidence.line`
- top abnormal items

## 恢复更多证据

如果 compact 输出被截断，用精确 include 开关和限制重试：

```json
{
  "args": {
    "include_rows": true,
    "max_items": 100
  }
}
```

如果 `SIGNAL_NOT_FOUND`，先在外部确认层级路径再重试。如果时间解析失败，使用明确时间如 `100ns`，或先做 time resolve。

## 工具问题排障

xdebug 会静默写结构化日志，不会污染 JSON 输出。遇到工具自身问题时按这个顺序看日志：

1. public action log：`~/.xdebug/sessions/<session_id>/logs/actions.ndjson`
2. 无 session 或 JSON parse/validate 失败：`~/.xdebug/sessions/adhoc/logs/actions.ndjson`
3. 后端生命周期：`~/.xdebug/engine/sessions/<hashed-session>/logs/lifecycle.ndjson`
4. 后端连接请求：`~/.xdebug/engine/sessions/<hashed-session>/logs/transport.ndjson`
5. daemon 文本细节：对应 session 目录下的 `debug.log`

重点看 `phase` 字段。启动服务、NPI 初始化、FSDB 打开、wait ready、connect/ping、自动 restart、gc/kill 都会形成 lifecycle 或 transport event。
