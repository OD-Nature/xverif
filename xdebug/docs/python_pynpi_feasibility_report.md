# Python pynpi 重写 xdebug 可行性报告

日期：2026-06-22

## 结论

不能只用当前 Verdi V-2023.12-SP2 自带的 Python `pynpi` 无损、完全实现现有 xdebug 的所有功能。

更准确的判断是：

- 设计静态查询类能力可以用 Python `pynpi.lang` 大体重写。
- 波形基础值查询、层次遍历、VCT 顺序扫描可以用 Python `pynpi.waveform` 大体重写。
- xdebug 自己实现的 APB/AXI/event/stream/verify/counter 等协议和窗口分析逻辑可以移植成 Python，但这是重写业务逻辑，不是 pynpi 自动提供。
- `trace.active_driver` 和 `trace.active_driver_chain` 不能用当前 Python `pynpi` 等价实现，因为 Python 层没有暴露 C++ L1 的 active trace API，也没有暴露 `npi_get_pvc_time()` / `npi_check_active_handle()`。
- 部分 edge-based FSDB cursor API 在 C++ L1 有、Python wrapper 中没有同名接口；可能能用 Python value evaluator 或普通 VCT 扫描绕过，但需要实测证明边界语义一致。

因此推荐路线不是“一次性纯 Python 替换 xdebug”，而是：

1. Python 化 coverage/报表/协议后处理/轻量 waveform query。
2. 保留一个很薄的 C++ NPI worker，用于 active-driver、active-chain、PVC active check、必要的 edge cursor。
3. 如果确实要纯 Python，先把目标降级为“功能近似”，并明确 `trace.active_driver*` 的结论质量会退化。

## 调研范围

本报告基于以下本地事实：

- xdebug public action 清单：`xdebug/docs/action-inventory.md`。
- xdebug C++ 实现：`xdebug/src/combined/`、`xdebug/src/engine/`、`xdebug/src/waveform/`。
- Verdi Python NPI：`$VERDI_HOME/share/NPI/python/pynpi`，本机路径为 `<verdi-install>/share/NPI/python/pynpi`。
- Verdi C/C++ NPI headers：`$VERDI_HOME/share/NPI/inc` 和 `$VERDI_HOME/share/NPI/L1/C/inc`。
- x-npi skill 实施期间补跑的真实 FSDB/daidir 示例验证。

本报告首先是 API/代码级能力评估；后续 x-npi skill 实施阶段已用现有 fixture 补充验证 Python `pynpi` 的 FSDB 值统计、APB/AXI/stream 离线分析和静态 driver trace 示例可运行。该补充验证不改变“active-driver 不能纯 Python 无损替代”的结论。

## 现有 xdebug 功能面

`xdebug/docs/action-inventory.md` 把当前 public action 分成四类：

| 类别 | 代表 action | Python 重写判断 |
| --- | --- | --- |
| builtin/session | `schema`、`actions`、`batch`、`session.*` | 可纯 Python 实现，主要是 JSON/schema/session 管理。 |
| design | `trace.driver`、`trace.load`、`trace expansion view`、`source.context`、`interface.resolve` 等 | 底层大多可用 `pynpi.lang` 重写，但要重建 xdebug 的图展开、source/context、interface alias 规则。 |
| waveform | `value.at`、`event.find`、`signal.statistics`、`apb.query`、`axi.analysis`、`stream.query` 等 | 基础 FSDB API 可用；协议/窗口/统计逻辑要移植；edge cursor 语义需验证。 |
| combined | `trace.active_driver`、`trace.active_driver_chain` | 当前 Python `pynpi` 缺关键 API，不能无损重写。 |

其中 action inventory 明确列出 `trace.active_driver` 和 `trace.active_driver_chain` 属于 combined action；设计 action 覆盖 `trace.driver/load/expand/graph/path/explain` 等；波形 action 覆盖 `value.*`、APB/AXI、event、verify、signal、counter、stream 等。

## Python pynpi 已具备的能力

### 1. NPI lifecycle 和 design load

Python `pynpi.npisys` 暴露：

- `init(pyArgvList)`
- `load_design(pyArgvList)`
- `end()`

这对应 C++ 的 `npi_init()`、`npi_load_design()`、`npi_end()`。现有 xdebug engine server 也是一次 session 内构造 `-dbdir ... -ssf ...` 参数，再调用 `npi_init()`、`npi_load_design()`、`npi_fsdb_open()`。

结论：`npisys.init/load_design/end` 生命周期本身可以 Python 化，但这不是 xdebug/xcov 那种长期 session 模型。

### 2. 设计静态 trace/load

Python `pynpi.lang` 暴露：

- `handle_by_name()`
- `trace_driver2()`
- `trace_driver_by_hdl2()`
- `trace_load2()`
- `trace_load_by_hdl2()`
- `get_hdl_info()`
- `TrcOption`
- `DrvLoadStmt`

`DrvLoadStmt` 包含 `src_hdl`、`scope_hdl`、`is_pass_thr`、`num_sig_use`、`use_hdl`、`sig_hdl_list`，与 C++ L1 `drvLoadStmt_s` 的核心结构一致。`TrcOption` 也包含 edge/data/control/statement 相关配置。

这足够重写 xdebug 的静态 driver/load 基础层。需要注意的是，xdebug 现有 design action 不只是返回原始 driver list，还做了：

- statement 分类；
- signal normalize；
- trace graph / expand / explain；
- control dependency；
- interface/modport alias 解析；
- source context 合并；
- 输出 contract 和 limit/truncation 处理。

这些属于 xdebug 业务逻辑，Python 可以移植，但不是 `pynpi.lang` 现成能力。

### 3. 波形基础查询和 VCT 扫描

Python `pynpi.waveform` 暴露：

- `open()` / `close()` / `is_fsdb()`
- `FileHandle.min_time()` / `max_time()` / `scale_unit()`
- `FileHandle.scope_by_name()` / `sig_by_name()`
- `SigHandle.create_vct()`
- `VctHandle.goto_first()` / `goto_time()` / `goto_next()` / `goto_prev()`
- `waveform.convert_time_in()` / `convert_time_out()`
- `waveform.sig_value_at()` / `sig_hdl_value_at()`
- `waveform.sig_vec_value_at()` / `sig_hdl_vec_value_at()`

这些覆盖了 xdebug `value.at`、`value.batch_at`、基础 scope/signal resolve、普通变化遍历、统计类扫描的大部分底层需求。

### 4. Coverage 已经证明 Python pynpi 可用于产品能力

当前 xcov v1 已使用 Python `pynpi.cov` / `pynpi.npisys` 作为真实 coverage backend。这说明 Python worker 架构在 xverif 里是可接受路线，但 coverage 的成功不能外推到 xdebug active-driver，因为 coverage 使用的是 `cov` API，不依赖 active trace。

## Python pynpi 相比 C++ NPI 缺少的关键内容

### 缺口 A：active trace API

C++ L1 header 暴露：

- `npi_active_trace_driver(...)`
- `npi_active_trace_driver_by_hdl(...)`
- `npi_active_trace_driver_by_hdl_dump(...)`
- `actTrcRes_t.activeTime`
- `actTrcRes_t.isForce`
- `actTrcRes_t.drvLoadStmtVec`

现有 xdebug `trace.active_driver` 在核心循环中直接调用 `npi_active_trace_driver_by_hdl(signal_hdl, active, time, options)`，并依赖 `active.drvLoadStmtVec`、`active.activeTime` 形成 `resolved/control_only/unresolved/ambiguous` 的用户可见结论。

Python `pynpi.lang` 暴露了 static `trace_driver_by_hdl2()`，但没有在 `pynpi` 包里发现 `active_trace`、`active_driver` 对应函数，也没有 Python 版 `actTrcRes_t`。

影响：

- `trace.active_driver` 不能无损重写。
- `trace.active_driver_chain` 不能无损重写。
- 无法保留 xdebug 当前最重要的 “requested time -> active causal statement -> activeTime” 证据链。

是否可绕过：

- 只能近似绕过，不能等价绕过。
- 可用 `trace_driver_by_hdl2()` 得到候选 driver，再读取相关 RHS/control signal 在时间点附近的值，尝试模拟 active branch 判断。
- 这种方法对 if/case/default/X、nonblocking active time、force/release、alias/modport、multi-driver、pass-through root cause 都可能退化。
- 如果产品 contract 仍要求 active causal statement，必须保留 C++ worker 或为 Python 新增 SWIG/binding。

### 缺口 B：PVC active check

C++ `npi_hdl.h` 暴露：

- `npi_get_pvc_time(npiHandle object, const char* time)`
- `npi_check_active_handle(npiHandle object, const char* time)`

xdebug 的 parity path 使用这两个 API：先把 requested time 转成 PVC time，再对 `trace_driver_by_hdl2()` 的候选 use handle 做 active/inactive/unknown 分类。

Python wrapper 没有发现对应函数。

影响：

- 即使不用主 active trace，也缺少候选 statement active check。
- Python 只能做启发式解释，不能提供 C++ 当前 parity 证据。

是否可绕过：

- 无可靠等价绕过。
- 可以用 waveform 值和 AST 条件求值近似判断，但这相当于实现一个小型 RTL active evaluator，覆盖面和 NPI 内部语义不会等价。

### 缺口 C：C++ L1 edge cursor

xdebug 的 FSDB 扫描工具使用：

- `npi_fsdb_goto_time_edge()`
- `npi_fsdb_goto_next_edge()`
- `npi_fsdb_goto_prev_edge()`

这些在 `$VERDI_HOME/share/NPI/L1/C/inc/npi_L1.h` 中存在。Python `pynpi.waveform` 有普通 VCT cursor 和 `sig_value_get_posedge/negedge/edge/dualedge` 一类 helper，但没有看到 VCT 上同名 `goto_*_edge` API。

影响：

- event/stream/protocol 中依赖 clock edge 精准定位的路径，需要重新实现扫描。
- 普通 VCT 扫描可以找变化点，但 edge helper 的边界语义、性能和 X/Z edge 规则要用真实 FSDB 验证。

是否可绕过：

- 可能可以绕过，但必须针对现有回归 fixture A/B 对比。
- 最低要求是验证 `event.find`、`stream.query/export`、AXI/APB analysis、`counter.statistics` 在 posedge/negedge、X/Z、同时间多变化、窗口边界上的行为一致。

### 缺口 D：transaction FSDB 和低层 L1 细节

C++ NPI headers 暴露 `npi_fsdb_trans.h`、C++ L1 FSDB helper、force tag、reason code、transaction traverse 等较低层接口。Python `pynpi.waveform` 和 `waveformw` 有部分 transaction/stream wrapper，但 xdebug 当前主要协议分析是用 signal-level FSDB 扫描自己实现。

影响：

- 当前 xdebug action 未必都依赖 transaction FSDB，但如果未来要扩展 `axi.export` 或 transaction-level evidence，Python 可用性需要另行实测。

是否可绕过：

- 现有 signal-level APB/AXI 可重写。
- transaction FSDB 能力不要在没有实测前承诺纯 Python 等价。

## xdebug action 级可行性矩阵

| action 类别 | 纯 Python 可行性 | 主要依据 | 风险 |
| --- | --- | --- | --- |
| `schema/actions/batch` | 高 | 不依赖 NPI 特殊能力 | 需要保持 JSON/schema contract。 |
| `session.*` | 高 | `npisys.init/load_design/end`、`waveform.open/close` 可用 | 长生命周期、stderr/stdout 隔离、license failure handling 需重建。 |
| `trace.driver/load` | 高 | `pynpi.lang.trace_driver*_2/trace_load*_2` 可用 | 输出字段和 C++ handle lifetime 要 A/B。 |
| `trace expansion view/graph/path/explain/control explanation view` | 中高 | 基础 trace API 可用 | xdebug 图算法和控制依赖逻辑要完整移植。 |
| `source.context/expr.normalize/procedural assignment view/sequential update view/fsm/counter` | 中 | `pynpi.lang` 有 AST/handle/get_hdl_info 能力 | 需要逐个确认当前 C++ 用到的 property/relationship 在 Python wrapper 中可访问。 |
| `signal.resolve/canonicalize/interface.resolve/port.trace/instance.map` | 中 | `handle_by_name`、`handle/iterate/scan/get/get_str` 可用 | interface/modport 规则复杂，必须 fixture 回归。 |
| `value.at/value.batch_at` | 高 | `waveform.sig_value_at/sig_vec_value_at` 可用 | 四态/X/Z 格式要对齐 xdebug `LogicValue` contract。 |
| `scope.list/list.*` | 中高 | waveform scope/sig traversal 可用 | `rc.generate` 和 list registry 是业务逻辑。 |
| `signal.changes/statistics/stability/trend` | 中 | VCT cursor 可用 | 性能和 edge/window 边界需要实测。 |
| `event.find/export/window.verify/verify.conditions/expr.eval_at` | 中 | 值查询和 VCT 可用 | 表达式 evaluator 与 edge semantics 需要重写和验证。 |
| `apb.*`、`axi.*`、`stream.*` | 中 | signal-level sampling 可用 | C++ 协议分析器要移植；edge cursor 缺口可能影响一致性。 |
| `trace.active_driver` | 低，不能无损 | Python 缺 `npi_active_trace_driver_by_hdl` | 只能启发式模拟或保留 C++。 |
| `trace.active_driver_chain` | 低，不能无损 | 依赖 active trace + alias/root-cause BFS | 同上，并且链式误差会累积。 |

## 可绕过方案

### 方案 1：纯 Python，但降级 active-driver

做法：

- 用 `pynpi.lang.trace_driver_by_hdl2()` 取静态候选。
- 用 `pynpi.waveform` 读取 requested time 附近的 data/control 值。
- 用 Python AST traversal 和表达式 evaluator 尝试筛选 active candidate。

优点：

- 进程、部署、调试更统一。
- 能覆盖很多简单 assign/if/case 场景。

缺点：

- 不能证明等价于 NPI active trace。
- 对 default/X、force、非阻塞调度、port/interface alias、multi-driver、control-only 场景会不稳。
- 需要在用户可见输出中降低置信度，不能继续声称 “NPI active driver resolved”。

结论：不适合作为现有 xdebug 的无损替换。

### 方案 2：Python 主体 + C++ active-trace worker

做法：

- Python 实现 JSON API、session、schema、波形基础查询、协议分析、report/export。
- C++ 保留一个最小 worker，只暴露：
  - active trace；
  - active chain；
  - PVC active check；
  - 必要 edge cursor helper。

优点：

- 最大限度降低 C++ 面积。
- 保住当前 xdebug 最有价值的 causal evidence contract。
- Python 可以快速迭代 action 层和报表层。

缺点：

- 仍然不是“完全 Python”。
- 需要定义 Python/C++ worker 间 JSON contract。

结论：推荐。

### 方案 3：为 Python pynpi 补 SWIG/binding

做法：

- 给 `npi_active_trace_driver_by_hdl`、`actTrcRes_t`、`npi_get_pvc_time`、`npi_check_active_handle`、`npi_fsdb_goto_*_edge` 增加本地 Python binding。

优点：

- 最接近纯 Python 上层实现。

缺点：

- 实质上仍要维护 C++ extension。
- Python ABI、Verdi 版本、link flags、license/runtime 环境都要管理。
- 比保留薄 C++ worker 更脆。

结论：只有在强制要求 Python API 外观时才值得考虑。

## 建议的验证路线

如果下一阶段要继续推进，建议按风险从低到高做 A/B：

1. 写 Python proof-of-concept：`npisys.init/load_design` + `lang.trace_driver_by_hdl2()`，对比现有 `trace.driver` JSON。
2. 写 Python waveform proof-of-concept：`waveform.open` + `sig_vec_value_at` + `VctHandle`，对比 `value.batch_at`、`signal.changes`。
3. 对 edge 行为做最小 fixture：posedge/negedge、X/Z、同一 timestamp 多信号变化，对比 C++ `npi_fsdb_goto_*_edge` 路径。
4. 对 active-driver 做不可替代性实测：同一 combined fixture 上比较 C++ `trace.active_driver` 与 Python static-trace heuristic；重点看 if/case/default/X/force/interface/modport。
5. 如果 active-driver 不能接受降级，直接转向“Python 主体 + C++ active worker”。

## 最终判断

当前 Python `pynpi` 足以支撑 xdebug 的一大部分重写，但不足以完全替代 C++ NPI 版本。阻塞点不是 Python 语言本身，而是 Verdi 当前 Python wrapper 没有暴露 C++ L1 active trace/PVC active check/部分 edge cursor 能力。

可以绕过的部分：

- static driver/load；
- FSDB value/scope/VCT；
- 大多数 xdebug 自有协议和窗口分析逻辑。

不能可靠绕过的部分：

- active causal driver；
- active driver chain；
- PVC candidate active check；
- 未经验证的 edge cursor 等价语义。

所以，如果目标是“现有 xdebug 所有功能和证据 contract 不退化”，答案是否定的：不能完全用当前 Python `pynpi` 实现。工程上可行的方案是混合架构，把 C++ 收缩到 active/edge 事实 worker，其余逻辑逐步 Python 化。
