# xdebug：按一次 Debug 流程取证

xdebug 是 daidir/FSDB 确定性事实入口。本文件覆盖高频决策链，不是全量 API 手册。每个阶段能力不足时，读取 [全量 xdebug action 索引](../generated/xdebug-actions.md)，再查询 runtime action catalog、action-specific schema 和 checked-in example；不要猜参数。

## 1. 建立资源、scope 和 config

- `daidir` 提供 scope、driver、load、source 和静态依赖；`fsdb` 提供值、事件、窗口和协议；combined session 支持 active driver。
- 用 `scope.roots` 找根，再用 `scope.list` 确认 hierarchy、真实信号和最终 leaf path。
- packed struct/aggregate 必须落实到 payload leaf；不能把 aggregate knownness 当最终结论。
- 记录 clock/reset、valid/ready/data、payload fields、state/counter、channel/id/opcode。
- 更完整的 scope/design/source/graph 能力见 [全量 action 索引](../generated/xdebug-actions.md)。

## 2. 定位异常时间和保存现场

| 问题 | action | 使用边界 |
| --- | --- | --- |
| 已知时间，只查一个信号 | `value.at` | 快速确认单一状态、计数或控制信号 |
| 已知时间，查一组相关信号 | `value.batch_at` | 默认现场快照；检查每个 row 的 status/reason 和 missing summary |
| 查看单信号在受限窗口怎样变化 | `signal.changes` | 用于缩小范围，不先导出全量变化 |
| 查看活动率、变化次数、持续特征 | `signal.statistics` | 用于宏观定量筛选 |
| 不知道异常时间，找首次/下一次条件命中 | `event.find` | 边沿、组合条件、阈值、状态转换；X/Z 比较为 unknown |
| 已知单点，同时验证多个条件 | `verify.conditions` | 单点事实证明 |
| 验证条件在 clock-edge 窗口持续成立 | `window.verify` | 输出 pass/fail/unknown；不代替事件搜索 |

推荐递进：`signal.statistics/changes` → `event.find` → `value.batch_at` → `verify.conditions/window.verify`。更多 value/signal/event/list/verify action 见 [全量 action 索引](../generated/xdebug-actions.md)。

## 3. 解释异常、采样和握手

- `detect_abnormal`：X/Z、glitch、异常短脉冲和 stuck 的 raw waveform smoke。合法 idle/backpressure 不能仅凭 stuck 判为 bug。
- `sampled_pulse.inspect`：解释 raw valid pulse 是否被指定 clock edge 采到，并保留 payload 在邻近边沿的现场。
- `handshake.inspect`：解释 valid/ready、backpressure 和 stall；可复用接口的连续分析优先进入 stream workflow。
- 其它 anomaly/handshake/protocol action 见 [全量 action 索引](../generated/xdebug-actions.md)。

## 4. 从信号追到 RTL 根因

1. `trace.driver` 静态查可能驱动来源。
2. `trace.load` 查消费位置和影响范围，决定下一批观察信号。
3. `source.context` 获取候选 file:line 周围源码。
4. `event.find` 定位异常时间，`value.batch_at` 保存控制现场。
5. 有 daidir + fsdb + signal + time 时用 `trace.active_driver` 查当前真正生效 driver。
6. 单级仍未到根因时用 `trace.active_driver_chain`；递归深度写顶层 `limits.max_depth`，不能写 `args.depth`。
7. 回到 `value.at/batch_at` 验证链上的控制条件。

保留 `resolved`、`control_only`、`unresolved`；control evidence 不能冒充最终 data driver。更多 trace/source/graph action 见 [全量 action 索引](../generated/xdebug-actions.md)。

## 5. Stream 是通用数据流能力

`stream.*` 不限 AXI/APB。任何能表示为 `clock + vld + data`，可选 `rdy/bp/sop/eop/channel_id` 的 pipeline、FIFO、command/response、descriptor、packet、credit/backpressure 或自定义 valid-ready 都优先考虑 stream。

流程：确认 leaf paths → `stream.config.load` → `stream.config.list` 验证 → `stream.query` 查 transfer/stall/packet/field match → finding 时间补 `value.batch_at` → `trace.active_driver` 解释 backpressure/control → `window.verify` 证明。

APB/AXI action 只在需要协议专属 transaction、channel 或 violation 语义时使用。完整 stream/APB/AXI action 见 [全量 action 索引](../generated/xdebug-actions.md)。

## 6. 宏观波形和多模态观察

需要观察长时间趋势、多信号相对关系、burst、stall 分布或状态阶段时，使用 [waveform render workflow](../workflows/waveform-render.md)：`list.create/list.add` → `list.export` → `xwaveform render` → 查看 JPG 和 stats JSON → 形成假设 → 回到确定性 action 验证。

图片不是唯一证据。需要交付 nWave 可复查视图时使用 `rc.generate`，不要手写 RC。其它产物/export action 见 [全量 action 索引](../generated/xdebug-actions.md)。

## 7. 保存并复用 config

- `stream/event/APB/AXI config.load` 的稳定映射必须优先从项目已有 config 加载。
- 首次推导的稳定配置不能只留在 session：优先保存到现有目录；无约定时建议 `xdebug/configs/`，并在 `xdebug/signals.md` 记录 clock/reset、leaf path、字段含义、采样和时间约定。
- config 不保存临时 session id、一次性 finding 或临时输出路径。
- 保存后用对应 `*.config.list` 验证，后续 workflow 复用配置。
- 当前任务未授权写项目文件时先询问；不得静默写到其它路径。xwiki 只在获得授权时保存稳定知识。

## Common failures

- 参数不确定：查询 action schema，读取 `invalid_arg/expected/allowed_values/did_you_mean/required_any_of/correct_example`。
- 响应 truncated/partial：缩小查询或使用该 action 明确支持的 limits/export。
- session/transport/LSF/timeout：转 `xverif-admin`，不自动 retry/reopen/fallback。

## 深入参考

- [原生 JSON API](../xdebug/json-api.md)
- [完整 response fields](../xdebug/response-fields.md)
- [现有 recipes](../xdebug/recipes.md)
- [已校验 examples](../xdebug/examples.md)
- [能力 overview](../xdebug/overview.md)
- [历史手工 action reference](../xdebug/action-reference.md)：仅用于补充说明；全量性由生成索引保证。
- [RC 生成](../xdebug/rc-generate.md)
- transport 和 runtime troubleshooting 已迁移到 `xverif-admin`。
