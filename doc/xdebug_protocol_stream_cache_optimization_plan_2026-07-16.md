# xdebug APB / AXI / Stream 缓存优化计划

日期：2026-07-16
状态：决策已确认，尚未实施
范围：`xdebug` engine 内 APB、AXI、stream 的分析结果缓存、查询索引、内存预算、失效合同与 stream transfer 列式存储。

## 1. 目标与非目标

### 目标

1. APB、AXI 继续保持“同一 session/config 首次完整扫描，后续 action 复用”的行为，并补齐跨协议预算、LRU、精确 key、失效和诊断。
2. stream 通过显式 `cache_scope: full|range` 决定基础分析范围；默认 `full`，AI 可为一次性窄窗口显式选择 `range`。
3. `stream.query`、`stream.export`、`stream.validate(dynamic:true)` 复用同一基础分析，不再各自扫描 FSDB。
4. Address、ID、Handshake、channel 等索引首次使用时创建、独立记账和优先淘汰，不复制 transaction、packet 或 payload。
5. 除新增的 stream request 参数和新的内存限制错误外，保持既有 JSON/XOUT、排序、局部编号、filter、时间和完整性语义。
6. 用正式 catalog suite、独立 oracle、schema discovery 和内部 probe 证明正确性与收益；不以主观“更快/更省”作为合入依据。

### 非目标

1. 不构建 APB、AXI、stream 共用的原始 FSDB sample tape。
2. 不改变 `ClockSampleScanner` / `ClockExpressionSampleScanner` 的 edge、before/after、same-timestamp 或 raw-value 语义。
3. 不跨 engine/session 复用缓存，不持久化到 SQLite，不做隐式磁盘 spill。
4. 不重构 AXI `writes/reads/all` canonical layout，不实现 transaction arena、payload sidecar 或 outstanding delta/checkpoint。
5. 不实现 APB `ApbRef`、stream 自定义四态 packing/interning、PMR allocator 或其它 profile 尚未证明必要的压缩。
6. 不新增 `cache.status`、`cache.clear`、`cache_enabled` 或自动 scope promotion。
7. 不在本计划顺便改变 APB/AXI 地址字符串的既有解析语义。

## 2. 已核对的现状

| 领域 | 当前行为 | 本计划处理 |
|---|---|---|
| APB | `ApbAnalyzer::results_` 按 name 缓存完整扫描结果；地址查询线性扫描并重复解析；cursor 只有位置、无 close。 | 保留 canonical layout；接入统一 repository/LRU；增加 numeric metadata、完整 AddressIndex 和 generation cursor。 |
| AXI | `AxiAnalyzer::results_` 按 name 缓存；地址/ID 多为线性扫描；HandshakeIndex 已惰性创建；cursor 只有位置。 | 保留 canonical layout和 outstanding 表示；接入统一 repository/LRU；增加独立 Address/Id/Handshake index 和 generation cursor。 |
| stream | query/export/dynamic validate 各自创建 `StreamAnalyzer` 并扫描；当前 cycle/packet index 从请求窗口局部 0 开始。 | 增加 full/range base cache；仅缓存 transfer 的完整 field value；保留 summary/stall 所需的最小 sample 元数据。 |

额外约束：engine 始终单线程；stream `mode:replace` 可覆盖同名配置；APB/AXI 当前拒绝同名 config load；session 层已把 FSDB metadata 变化判为 `FsdbChanged`。

## 3. 总体架构

### 3.1 Engine-owned AnalysisRepository

engine 进程拥有唯一 `AnalysisRepository`：

```text
AnalysisRepository
  BudgetCoordinator              // 跨协议 soft/hard byte accounting 与 LRU
  ApbEntryStore                  // typed canonical entries
  AxiEntryStore
  StreamEntryStore               // full/range entries
  LazyIndexStore                 // 独立 index objects
  CursorStore                    // cache key + generation + direction + position
  TestProbe                      // test-only，不注册 public action
```

- action handler 只能调用 repository 的 `ensure_apb/ensure_axi/ensure_stream`，不能维护旁路扫描判断。
- analyzer/tracker 只负责构建和查询领域结果，不负责 LRU、环境变量、session 或 FSDB 生命周期。
- repository 随 engine 退出销毁；不跨进程共享。
- engine 为单线程模型：不实现 condition variable、并行 builder 等待或多线程 cache 锁。保留 `building/ready` 状态，只用于重入保护和禁止发布半成品。

### 3.2 Cache key 与语义 fingerprint

所有 key 至少包含：

- protocol/stream 类型；
- session identity；
- session 打开时记录的 FSDB `dev/inode/size/mtime`；
- 带版本号的规范化语义 config；
- stream entry 的 `cache_scope`；range entry 还包括规范化后的闭区间 begin/end。

语义 fingerprint：

- 包含 signal path、表达式、clock edge/sample point、reset、field、packet、channel/interleaving 等所有影响分析的字段。
- 不包含 config name、description、JSON 字段顺序或 config 文件路径。
- key 使用强摘要，同时保留规范化内容做等值确认，不能只依赖 hash。
- fingerprint 规范化规则改变时升级版本，旧 entry 自然不再命中。

### 3.3 Immutable canonical entry 与独立 lazy index

- canonical entry 发布后严格不可变。
- lazy index 是独立 cache object，key 包含 canonical key、generation、index kind。
- index 淘汰不触发 FSDB 重扫；后续从 canonical entry 重建。
- canonical entry 淘汰/失效时，其全部 index 一并释放。
- 第一次使用某类 selector 时建立该类型完整索引，不做次数阈值或 selector-local 自动升级。
- address+ID 使用已有 bucket 交集/过滤，不建立第三套冗余组合索引。

### 3.4 Cursor 生命周期

APB/AXI cursor 不长期 pin entry，也不新增公开 `cursor.close`：

- cursor 保存 `cache key + generation + direction + position`，不保存 transaction pointer。
- 只有当前 action 执行期间使用 request-scoped guard。
- LRU 淘汰后，下一次 cursor action 重新构建相同 key，并从原位置继续。
- config fingerprint 改变或 session 失效时清除 cursor。
- 指针只在当前 action 内短期存在，不能进入跨 entry 全局容器。

### 3.5 FSDB 与 config 失效

1. engine/session 退出释放全部 entry/index/cursor。
2. FSDB metadata 变化使 session stale/unhealthy；清理 cache/cursor 后拒绝继续使用旧 NPI handle。必须显式 reopen session，不能只清缓存后重扫。
3. stream config replace 使用同目录临时文件完整写入、`fsync`、原子 `rename`；成功后才通知 repository。
4. 新旧 stream 语义 fingerprint 相同则复用 entry；仅 description 等非语义变化不重扫。
5. 语义 fingerprint 不同则立即失效旧 entry/index/cursor generation。
6. config 写入或 rename 失败时保留原 config 与原 cache。

## 4. 预算、淘汰与内存错误合同

### 4.1 两级预算

- `XDEBUG_ANALYSIS_CACHE_MAX_BYTES`：soft budget。`0` 表示不主动做预算 LRU，但仍受 hard limit 保护。
- `XDEBUG_ANALYSIS_CACHE_HARD_MAX_BYTES`：hard memory limit，必须为正整数，不允许 `0`。
- 两者在 engine 启动时严格解析一次；非法文本、负数、尾随字符、溢出或 `soft > hard` 均使启动失败，不得静默使用默认值。
- session 运行期间修改环境变量不生效，必须 reopen。
- soft/hard 默认值与 estimator 安全系数由 Phase 0 实测后冻结；不得凭经验猜值。

hard limit 的确定性计量口径为：

```text
resident canonical/index estimated bytes
+ current build working-set estimated bytes
```

构建前先淘汰冷对象获得空间；构建中在 column/vector/index 扩容点更新估算。所有加法使用饱和运算，不能因整数溢出绕过 hard limit。NPI/共享库等非 analysis 内存不直接纳入合同，但用实际 RSS 校准安全系数。

### 4.2 确定性 LRU

1. 先淘汰最冷 lazy index，再淘汰最冷 canonical entry；APB/AXI/stream 不设置隐藏权重。
2. 使用单调递增 access sequence，不使用 wall clock。
3. index 命中同时刷新 index 与 owning canonical；同一请求内多次读取合并为一次逻辑 access。
4. canonical entry 被淘汰后，下次请求自动重扫并正常返回；记录 `cache_miss_after_evict`。
5. 不做 negative cache；任何失败都回滚半成品、index 和 byte accounting。

### 4.3 Soft budget 超限

- 单个 canonical entry 超过 soft budget仍可准入；先淘汰其他 index/entry，并允许它作为唯一 canonical 暂时超出 soft budget。
- oversize index 也可准入；owning canonical 与当前 index形成最低驻留组合，其他冷 index仍可淘汰。
- 后续新对象仍按纯 LRU决定是否淘汰 oversize object，不永久保护。
- 记录 `oversize_entry_admitted` / `oversize_index_admitted`、分项字节数和淘汰原因。
- soft 超限永远不能越过 hard limit。

### 4.4 Hard limit 错误

超过 hard limit 时停止构建，返回：

```text
ANALYSIS_MEMORY_LIMIT_EXCEEDED
recoverable: true
```

错误包含当前估算、hard limit、协议/config 非敏感摘要，并建议：

1. stream 显式改用 `cache_scope:"range"` 或缩小 `time_range`；
2. 仍无法满足时，使用 x-npi 提交一次性离线分析任务。

engine 不自动切换 scope、不自动调用 x-npi、不切换 backend。`std::bad_alloc` 尽力转换为同类错误；若 OS 直接 OOM-kill，进程可能无法返回响应。

## 5. APB 计划

### 5.1 保留 canonical layout

保留 `writes/reads` ownership 与 `all` pointer view，不实现 `ApbRef`。所有公开顺序保持：

- direction 内保持当前时间顺序；
- `all` 同时间戳保持 write-before-read；
- cursor、window、address bucket使用同一顺序，不依赖 pointer/hash 遍历顺序。

### 5.2 AddressIndex

- scan 时按当前 `parse_hex_value` 完全相同的语义写入 numeric address metadata；不顺便修复 mixed X/Z 或尾随字符行为。
- 第一次 address selector 构建完整 AddressIndex。
- bucket 保存对现有 read/write transaction vector 的轻量 ref，不复制 transaction。
- `first/index/last/line_limit` 直接读取 bucket，消除当前 `O(N × line_limit)` 重复扫描。
- index 淘汰后仅从 canonical result 重建。

### 5.3 Action 与 cursor

`apb.query`、`apb.cursor`、`apb.statistics`、`apb.transfer_window` 全部经 repository lookup。generation cursor按第 3.4 节执行；淘汰重建不得改变 1-based cursor state。

## 6. AXI 计划

### 6.1 保留 canonical layout 与协议状态机

本轮不修改 `AxiResult` 的 `writes/reads/all/pending/outstanding_samples` 结构，不修改 tracker pairing、payload ownership或 outstanding 表示。

必须保持：

- `writes/reads/all` 的 `addr_time -> seq` 顺序；
- response-time view 的既有输出顺序和稳定 tie-break；
- handshake index 的 `handshake_time -> seq -> beat_index` 顺序；
- bucket 顺序来自 canonical view，不依赖 hash迭代；
- 地址/ID 解析、`include_data`、pending diagnostics 和 public JSON 不变。

### 6.2 Lazy indexes

- AddressIndex：第一次 address selector 建立完整索引。
- IdIndex：第一次 ID selector 建立完整索引。
- HandshakeIndex：沿用首次 channel 使用才建，但迁入独立 index store 和统一记账。
- index 保存 direction/index 等轻量 ref，不复制 transaction 或 payload。

### 6.3 Action 与 cursor

`axi.query`、`axi.cursor`、`axi.analysis`、`axi.statistics`、`axi.export`、`axi.request_response_pair`、`axi.latency_outlier`、`axi.outstanding_timeline`、`axi.channel_stall` 必须经过同一 repository lookup；旧的重复 `ensure_axi_analyzed` 和旁路 result迁移完成后删除。

## 7. Stream 计划

### 7.1 公开 cache_scope 合同

三个 action 增加同名参数：

```json
"cache_scope": "full" | "range"
```

- 默认 `full`。
- `full`：构建完整 FSDB base entry；当前 action仍只返回请求 `time_range`。
- `range`：仅构建规范化请求闭区间对应的 entry。
- `range` 未给 `time_range` 时规范化为完整 FSDB范围，并复用 full entry。
- full entry 已存在时，即使请求 range 也从 full 派生，不重复扫描。
- full entry成功构建后，淘汰同 session/FSDB/config 的全部 range entries。
- full build失败时保留已有 range entries。
- 不同 range 不合并、不扩展、不按访问次数升级 full。

参数只公开于：

- `stream.query`；
- `stream.export`；
- `stream.validate`，且只在 `dynamic:true` 时有效。

`stream.validate(dynamic:false)` 携带 `cache_scope` 返回明确 `INVALID_ARGUMENT`，不能静默忽略；request schema 使用条件约束拒绝该组合，handler 同时保留防御性校验。APB/AXI 不接受该参数。

### 7.2 AI 选择规则

- 默认或预计连续执行 query/export/dynamic validate：使用 `full`。
- 一次性明确窄窗口，或已知完整 FSDB 很大：显式使用 `range`。
- 多个不同窗口优先 full，避免堆积大量 range entries。
- 收到 `ANALYSIS_MEMORY_LIMIT_EXCEEDED` 后可显式发起 range 新请求；这不是 engine fallback。
- range 仍失败时停止重试并建议 x-npi。
- schema 说明参数语义和默认值；详细决策规则写入 skill reference，不引入冗余同义参数。

### 7.3 StreamBaseAnalysis 数据模型

完整 field payload 只缓存 transfer 有效数据；非 transfer sample 不保存 data/beat/stable field value。

```text
StreamBaseAnalysis
  identity
    cache key, scope, normalized range, config/fsdb fingerprint
    scan/build/byte metrics, analysis_complete

  sample metadata                         // 所有被采样 clock edge
    times
    vld/stall/reset/control-XZ 等 summary/range 所需紧凑状态或区间统计
    data_xz_count                         // 保留非 transfer 上的 X/Z 计数语义
    stall ranges

  transfer table                         // 只含 transfer
    transfer -> sample_id
    field schema                         // field 名/描述/类型只保存一次
    field columns                        // 每列与 transfer ordinal 对齐
    channel value

  packet table
    packet -> transfer beat span
    channel, boundary, stable mismatch spans
```

- 不在每个 transfer 保存 `map<string, StreamValue>`。
- packet 不复制 `StreamBeat`、first/last/filter field maps；由 transfer field columns临时 materialize。
- 不做自定义四态 packing；`StreamValue` 必须可逆保留 0/1/X/Z。
- field columns只保存 transfer，但所有 sample time与 summary/stall 最小事实必须保留，否则 full→range 会重新扫描。

### 7.4 StreamQueryView 与外部语义

`StreamQueryView` 是请求级临时对象，不进入 LRU预算。它处理 time range、channel、filter、query、line_limit和局部编号。

必须保持：

- 每个请求窗口首个 sample 的 `cycle=0`；base sample ID 永不公开。
- 与窗口相交的 packet 按窗口时间序重新编号 `packet_index=0..N-1`。
- `packet_at.packet_index` 继续表示当前请求窗口内局部编号。
- stall 起止 time/cycle裁剪到窗口并按局部 cycle重建。
- 跨窗口 packet返回正确 `partial_begin/partial_end`。
- 窗口缺 SOP/EOP 或比较位含 X/Z 时保持现有 unresolved语义。
- `line_limit` 只限制 materialize/response，不改变完整 summary、matched count或 first/last evidence。
- `stream.query`、`stream.export`、dynamic validate使用同一 base lookup；show/config.load/static validate不构建 base entry。

### 7.5 原子 config replace

stream config持久化采用 temp + fsync + atomic rename。成功后 repository比较语义 fingerprint；相同语义复用，不同语义失效。该改造不改变成功 response。

## 8. Schema、skill 与可观测性

### 8.1 cache_scope 一致性

必须同步：

- `xdebug/specs/actions/actions.yaml`；
- `xdebug/specs/action_contracts.py` 与 `xdebug/tools/sync_runtime_request_schemas.py`；
- 三个 checked-in request schema；
- request examples；
- `skills/xverif/references/xdebug/action-reference.md`、生成引用和 `agents/openai.yaml`。

schema 对三个 action必须使用同一个名称、enum、默认值和核心描述，并明确它只控制 base analysis/cache 扫描范围，不改变响应 `time_range`。不得增加 `analysis_scope`、`scan_scope` 等同义字段。

可见性必须同时验证：

1. native `schema` action；
2. MCP `xverif_debug_get_schema(action, kind="request", view="mcp")` 的 `args_schema` 和 `constraints`；
3. runtime embedded Draft-7 validator；
4. checked-in schema/example 与 action catalog。

### 8.2 内部日志与 test-only probe

生产只写结构化内部日志：`hit/miss/build/evict/invalidate/index_build/oversize_admitted/build_failed`。日志包含协议、scope/range、非敏感 key摘要、字节数、耗时和原因，不打印完整 signal path。

test-only probe 提供 scanner调用次数、entry/index数、hit/miss/evict、resident/build bytes和access sequence；不注册 public action，不进入 schema/MCP/JSON/XOUT。

## 9. 测试策略

### 9.1 通用 cache 单元测试

- key/fingerprint版本、语义等价/差异、range边界；
- 单线程 building/ready、重入保护、失败完整回滚；
- lazy-index-first与跨协议纯 LRU；
- deterministic access sequence；
- generation cursor在evict/rebuild后的连续位置；
- soft oversize entry/index准入；
- hard limit与饱和记账；
- strict env解析及 soft/hard关系；
- fault-injected `bad_alloc`，不做真实 OOM测试；
- 不缓存任何 failure。

### 9.2 APB/AXI

- APB 地址 metadata/index前后结果等价，line_limit复杂度不再重复全表扫描；同时间戳 write-before-read。
- AXI Address/Id/Handshake index前后结果等价；排序严格保持 `addr_time/seq`、`resp_time`、`handshake_time/seq/beat_index`。
- active cursor不长期 pin；淘汰重建后 state与输出不变。
- 同一 session跨 query/cursor/statistics/export/window action只做一次 cold scan；淘汰后才重扫。
- 真实 `xdebug.apb_vip` / `xdebug.axi_vip` 使用独立 VIP oracle逐字段比较。

### 9.3 Stream 完整差分矩阵

Phase 0 固化当前实现的 normalized JSON/XOUT golden。Phase 4A保留 test-only legacy analyzer adapter；同一 sample/config/range同时走 legacy与新 QueryView逐字段比较。稳定后可删除或冻结为 test oracle，不能注册 public bypass。

至少覆盖：

- 默认 full、显式 full、显式 range、range未给time_range；
- range冷/热命中、full冷/热命中、full派生range；
- range→range、range→full→range及full清理range；
- 不同range不合并；不同config fingerprint隔离；
- 非零begin/end、空窗口、单点、begin/end落在sample前/上/后；
- cycle与packet_index局部重编号、packet_at、stall裁剪；
- partial packet、SOP/EOP、exact/range/mask、X/Z unresolved；
- reset、channel、interleaving、same timestamp、posedge before/after、negedge；
- 非transfer字段含X/Z时summary计数不变，但不缓存完整field value；
- query/export/dynamic validate共享scan；static validate/show/config.load不构建base；
- line_limit只截响应，不改变summary/evidence；
- soft LRU重建与hard limit错误；session/config/FSDB生命周期。

### 9.4 Batch 与 schema discovery

- `batch` 是xdebug builtin action；MCP仅通过通用 debug query提交。
- 同一batch内、同一session/engine的子请求共享cache；不同session隔离。
- 覆盖 query→export→dynamic validate、range→range、range→full→range以及子请求失败不发布半成品。
- 三个stream action的native/MCP schema可见性、默认值、描述一致性、dynamic:false拒绝及APB/AXI负向拒绝必须有测试。

### 9.5 性能方法

Phase 0在独立新engine中重复记录：cold/hot P50/P95、scanner次数、entry/index/working-set bytes、实际RSS、transaction/transfer/sample规模。

不可协商门禁：

- JSON/XOUT与oracle等价；
- hot hit scanner调用为0；
- budget/eviction/generation行为正确。

具体内存下降与延迟回归阈值由Phase 0实测后回填并冻结；未冻结前不能以“有改善”通过后续阶段。易抖动wall-time只进入benchmark gate，不直接作为普通功能测试阈值。

## 10. 分阶段实施与提交

### Phase 0：基线、oracle、probe与阈值

- 建立golden、legacy differential adapter、test-only probe和benchmark。
- 校准estimated bytes/RSS，冻结soft/hard默认值、安全系数及各阶段性能阈值。
- 不改变公共action输出或扫描行为。

建议提交：

```text
测试：建立xdebug分析缓存的基线、差分oracle与内存测量

固化APB、AXI、stream现有输出与扫描基线，增加仅测试可见的probe和非破坏性内存测量，为后续缓存迁移冻结正确性与性能门禁。
验证：<实际catalog suite和静态检查结果>
```

### Phase 1：AnalysisRepository与生命周期基础设施

- 实现engine-owned repository、typed stores、预算协调器、strict env、soft/hard合同、deterministic LRU、独立index store、generation cursor和结构化日志。
- 只使用fake entry验证，不迁移协议canonical layout。
- 完成stream config原子replace与语义fingerprint通知。

### Phase 2：AXI接入repository与lazy index

- 保留现有`AxiResult`和tracker。
- 所有AXI action统一lookup；迁移Address/Id/Handshake index与generation cursor。
- 运行`xdebug.cpp_unit`、沙箱外`xdebug.contract`与`xdebug.axi_vip`，做输出、排序、scan count、LRU与hard-limit差分。

### Phase 3：APB接入repository与AddressIndex

- 保留现有transaction/pointer layout。
- 增加兼容现有解析语义的numeric metadata、完整AddressIndex和generation cursor。
- 运行`xdebug.cpp_unit`、沙箱外`xdebug.contract`与`xdebug.apb_vip`。

### Phase 4A：Stream列式base与单请求QueryView

- 提取`StreamBaseAnalysis/StreamQueryView`。
- 所有sample仅保留time与summary/stall最小事实；完整field columns只保存transfer。
- 暂不启用跨请求cache；使用legacy adapter完成全矩阵差分。

### Phase 4B：Stream cache_scope与跨请求复用

- 三个动态stream action接入repository。
- 实现显式full/range、full清理range、LRU、hard-limit错误与AI/skill指导。
- 完成schema generator、examples、native/MCP get-schema测试。
- 运行`xdebug.cpp_unit`、沙箱外`xdebug.contract`与`xdebug.stream`。

每个phase必须独立构建、回归、提交和回滚；不得把future work混入当前提交。commit message必须使用中文，写明动机、范围、验证和未运行项。

## 11. 提交前通用门禁

每个源码提交至少运行：

1. `python3 xdebug/tools/sync_runtime_request_schemas.py --check`
2. `python3 xdebug/tools/sync_axi_response_schemas.py --check`
3. `python3 xdebug/tools/sync_action_schema_hints.py --check`
4. `python3 xdebug/tools/audit_runtime_schema_compatibility.py`
5. `python3 xdebug/tools/validate_schema.py`
6. `python3 xdebug/tools/validate_examples.py`
7. 对应的正式catalog suite；先用`pytest --xverif-gate <gate> --xverif-plan`确认选择。

`xdebug.contract`、`xdebug.apb_vip`、`xdebug.axi_vip`、`xdebug.stream`及任何真实FSDB/NPI/VIP动作整体在沙箱外运行。skill修改通过对应`skills.*` suite后，使用Makefile安装目标同步到`~/.codex/skills`和`~/.claude/skills`，并逐skill执行`diff -qr`。

提交前执行`git status --short`并显式暂存本阶段文件；发现无关baseline漂移时不得静默过滤或顺手修复。

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| config key遗漏语义字段 | 版本化规范化内容+强摘要+等值确认；schema/config差异单测。 |
| cursor长期pin导致预算失效 | generation cursor+request-scoped guard；evict/rebuild连续性测试。 |
| FSDB变化后继续使用旧handle | session直接stale，必须reopen；禁止仅清cache后重扫。 |
| full/range同时常驻造成重复 | full成功后清理同配置range；不同range不自动合并。 |
| full派生range改变局部编号 | QueryView重建cycle/packet_index/stall边界；legacy逐字段oracle。 |
| 只缓存transfer导致summary漂移 | 保留全部sample time与summary/stall最小元数据；非transfer X/Z测试。 |
| soft budget被误当硬上限 | 明确oversize准入；独立hard limit保护build working set。 |
| hard limit错误触发静默fallback | 只返回可恢复错误和建议；scope/x-npi必须显式新请求。 |
| lazy index改变顺序或解析 | bucket来自canonical view；复用现有解析与tie-break。 |
| schema文件可见但MCP投影缺字段 | native schema、MCP get-schema、runtime validator三层测试。 |

## 13. Future work（不属于本轮）

只有后续profile和独立合同评审证明必要时，才另立计划评估：

- AXI transaction arena/id views；
- AXI outstanding delta/checkpoint（必须保留完整sample time轴）；
- APB `ApbRef`；
- stream四态packing/interning；
- AXI payload sidecar；
- SQLite或其它显式disk-backed cache；
- range coalescing/automatic promotion；
- 多线程builder协调。

## 14. 结论

本轮先统一analysis cache生命周期、预算、失效、索引和cursor合同，再以显式`cache_scope`为stream建立可验证的full/range复用。APB/AXI只迁移cache管理与lazy index，不重构canonical数据；stream只对transfer field做列式存储，非transfer保留summary/stall所需最小事实。所有高级压缩和磁盘backend移出本轮，以golden、legacy differential oracle、正式catalog suite和schema discovery作为实施门禁。
