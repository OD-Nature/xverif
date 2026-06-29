# xdebug 总览

xdebug 是 xverif 的 daidir/FSDB 事实查询入口，用 JSON request 查询设计、波形和 combined 因果证据。设计事实来自 `daidir`，波形事实来自 `fsdb`，两者同时存在时可做 active-driver、协议异常和源码 evidence join。

## 何时使用

- 用户给出 `daidir`、`fsdb`、`session_id`、信号路径、时间点、APB/AXI/handshake/debug 现象。
- 需要查某个 signal 的值、变化、driver、load、依赖路径、源码证据、协议 finding。
- 需要把波形异常时间点连接到当前生效 RTL driver：优先用 `trace.active_driver`。
- 需要生成 nWave `signal.rc` 证据视图：用 `rc.generate`。

不要用 xdebug 做 bit 计算、entry decode、日志位置还原或项目持续记忆管理；分别用 xbit、xentry、xloc、独立 xberif skill。

## 入口

优先使用 MCP 或 SDK-free wrapper。MCP 场景下，本文所有 xdebug 原生 action 从 `xverif_debug_query` 进入：

1. 用 `xverif_debug_session_open` 打开 design/waveform/combined session。
2. 用 `xverif_debug_query` 传 `action`、`args`、`limits`、`output`。
3. 常规 debug 不默认用 `xverif_debug_raw_request`；raw request 不维护 MCP 托管的 stdio-loop/LSF session。

需要直接命令时使用仓库 wrapper：

```bash
xdebug --json -
tools/xdebug --json -
```

机器解析必须请求 JSON。默认 `xout` 适合人读或 AI 摘要，不适合脚本字段比较。

## target 决策

| target | 能力 |
| --- | --- |
| `{"daidir":"simv.daidir"}` | 设计侧：driver/load/query、graph、source、expr、FSM/counter/sequential |
| `{"fsdb":"waves.fsdb"}` | 波形侧：scope、value、list、event、APB、AXI、verify、signal、handshake、anomaly、rc |
| `{"daidir":"simv.daidir","fsdb":"waves.fsdb"}` | combined：波形时间点和 RTL 因果 join |
| `{"session_id":"case_a"}` | 复用已打开 session |

## session 规则

- stateful 查询先 `session.open`，后续用 `target.session_id`。
- session name 必须匹配 `^[A-Za-z][A-Za-z0-9_]{0,63}$`。
- 同名 live session 返回 `SESSION_ID_EXISTS`；同名 stale session 返回 `SESSION_STALE`，需要显式 close/gc 后重开。
- 不要依赖 auto-open 或隐式复用。

## 高频 action

| 意图 | 首选 action | 备注 |
| --- | --- | --- |
| 多信号单点查值 | `value.batch_at` | 比多次 `value.at` 更合适 |
| 单信号查值 | `value.at` | 需要精确 time |
| 找事件/边沿 | `event.find` | 不要先导出全量 changes |
| 验证窗口条件 | `window.verify` | 保留 pass/fail/evidence |
| 查 driver | `trace.driver` | 设计侧 |
| 查当前生效 driver | `trace.active_driver` | 需要 daidir + fsdb + time |
| 查源码证据 | `source.context` | 控制上下文行数 |
| APB/AXI 异常 | `apb.config.load` / `axi.config.load` 后 query/analysis | 先注册信号映射 |
| 生成波形证据 | `rc.generate` | 见 rc reference |
