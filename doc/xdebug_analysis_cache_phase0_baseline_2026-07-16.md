# xdebug 分析缓存 Phase 0 基线与冻结阈值

日期：2026-07-16
对应计划：`doc/xdebug_protocol_stream_cache_optimization_plan_2026-07-16.md`
状态：Phase 0 基线已建立；repository 尚未实施。

## 1. 测量方法

- 正式入口：`pytest --xverif-gate nightly --xverif-suite xdebug.analysis_cache_benchmark`。
- 执行位置：沙箱外 host，`XVERIF_TEST_EXECUTION_ENV=host`。
- 数据源：catalog 已发布的 `xdebug.apb_vip`、`xdebug.axi_vip`、
  `xdebug.stream_v1` fixture；普通 gate 未生成或替换 fixture。
- 每个协议使用 3 个独立新 engine；每个 engine 记录一次 cold 和两次后续请求。
- AXI 使用 stress fixture；stream 使用 20,000 transfer / 5,000 packet 的
  `ready_packet` 全范围查询。
- test-only `XDEBUG_TEST_ANALYSIS_PROBE_PATH` JSONL probe 记录 scanner 次数、
  entry/index 数、hit/miss/evict、resident/build estimated bytes、PID 和单调 access
  sequence。probe 不注册 public action，不进入 schema、MCP、JSON response 或 XOUT。
- RSS 使用 engine `/proc/<pid>/status` 的 `VmRSS`，记录 config load 后到 cold query
  完成后的增量。字节估算覆盖当前 APB/AXI canonical result 和 stream analysis 的
  vector/string/map 动态容量。
- `LegacyStreamAnalyzerAdapter` 固化现有 `StreamAnalyzer` 为后续差分 seam；Phase 0
  的 query/export/dynamic validate 仍原样委托旧实现，不新增 public bypass。

## 2. 实测结果

| 协议 | cold P50/P95 | 后续请求 P50/P95 | 最大 RSS 增量 | 最大估算字节 | 每 engine scanner 次数 |
|---|---:|---:|---:|---:|---:|
| APB | 62 / 68 ms | 57 / 59 ms | 2,510,848 | 1,772 | 1 / 1 / 1 |
| AXI stress | 6,688 / 6,997 ms | 340 / 359 ms | 725,323,776 | 828,131,739 | 1 / 1 / 1 |
| stream | 778 / 854 ms | 766 / 941 ms | 32,563,200 | 20,166,722 | 4 / 3 / 3 |

APB 结果对象很小，RSS 增量主要受 NPI/allocator page 粒度影响，因此
RSS/estimator 比值不用于安全系数。AXI estimator/RSS 比值约 1.14（estimator
偏保守），stream 的 RSS/estimator 最大比值约 1.615。

stream 第一个 engine 多一次 scanner，是因为除 cold + 两次重复 JSON 请求外还执行
了一次 XOUT golden；另外两个 engine 各执行三次相同查询。该结果证明当前 stream
没有跨请求 base cache，而 APB/AXI 在同一 engine/config 内只做一次 cold scan。

## 3. 正确性 oracle

- APB/AXI 继续由 `xdebug.apb_vip` / `xdebug.axi_vip` 的 VIP scoreboard、仿真日志和
  pin-handshake oracle 校验；改造前两项 suite 均通过。
- stream benchmark 固化 compact normalized JSON projection：20,000 transfers、
  5,000 complete packets、packet index 3 的 cycle/time/beat/opcode/data/seq。
- stream 同时固化 XOUT 关键行，覆盖 packet stable field、首 beat、first/last
  fields，并确认不泄漏内部 `bits/known` 表示。
- 改造前 `xdebug.contract + xdebug.stream` 共 70 项通过，`xdebug.cpp_unit` 通过。

## 4. 冻结决策

统一 cache 合同冻结为：

- estimator safety factor：`2.0`；覆盖 stream 1.615 的最大实测比值并留出余量。
- soft default：`1,073,741,824` bytes（1 GiB）。
- hard default：`2,147,483,648` bytes（2 GiB）。

2.0 safety factor 下，当前 AXI stress 估算约 1.66 GiB：允许按 oversize-entry 规则
越过 1 GiB soft budget，但仍低于 2 GiB hard limit。这样不会为了默认预算静默换
数据源或缩小分析，同时会迫使跨协议/多配置场景进入确定性 LRU。

阶段性能与内存门槛维护在
`xdebug/tests/benchmark/analysis_cache_thresholds.v1.json`：

- AXI repository：cold P95 不高于 8,050 ms，hot P95 不高于 415 ms，RSS 增量不高于
  834,122,342 bytes；hot scanner 增量必须为 0。
- APB repository：cold/hot P95 不高于 80 ms，RSS 增量不高于 4 MiB；hot scanner
  增量必须为 0。
- stream columnar：cold P95 不高于 1,000 ms，RSS 增量不高于 24,422,400 bytes，
  相对 Phase 0 至少下降 25%。
- stream cache：hot P95 不高于 400 ms；hot scanner 增量必须为 0。

wall-time 阈值只在 nightly benchmark suite 判断，不进入普通 unit/contract 的易抖动
断言。JSON/XOUT oracle 等价、hot scanner 为 0、预算/淘汰/generation 正确性仍是不可
协商功能门禁。

## 5. 证据

- 改造前 contract + stream：`.xverif-test-results/20260716-150516-zq_c4g5c/report.json`。
- 改造前 APB/AXI VIP：`.xverif-test-results/20260716-150513-pgf47y83/report.json`。
- Phase 0 benchmark（含冻结阈值门禁）：
  `.xverif-test-results/20260716-154511-3eb6kyjh/report.json`。
- Phase 0 contract + stream：
  `.xverif-test-results/20260716-153536-q5wwq0ha/report.json`（70 passed）。
- Phase 0 APB/AXI VIP：
  `.xverif-test-results/20260716-153703-1gflab78/report.json`（2 passed）。
- Phase 0 C++ unit：
  `.xverif-test-results/20260716-154306-uwhtw3k4/report.json`。
- Phase 0 static：
  `.xverif-test-results/20260716-153831-s561w76l/report.json`（13 passed）。
- Phase 0 testinfra：
  `.xverif-test-results/20260716-153831-csacarqo/report.json`（24 passed）。
- 六项 schema 生成同步、Draft-7 compatibility、156 个 schema 与 149 个 example
  检查均通过。
