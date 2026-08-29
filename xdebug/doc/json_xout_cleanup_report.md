# xdebug JSON 与 xout 清理验证报告

日期：2026-06-27

## 一、阶段一：JSON 冗余源头治理

本阶段先备份现有 JSON 返回，再从 action/dispatcher/engine 源头去掉重复字段，避免在后处理层屏蔽问题。

主要结果：

- 基础 response 不再默认输出空 `warnings/findings/suggested_next_actions`。
- `summary` 作为统计和结论入口，`data` 只保留证据、列表、对象和文件路径等展开数据。
- 不再从任意 `data` 顶层标量自动拼 summary，避免一个事实在 `summary` 和 `data` 同时出现。
- `meta.truncated` 只在真实截断时输出，不再默认输出 `false`。
- APB/AXI 查询类计数统一读 `summary.count`、`summary.transaction_count`、`summary.write_count/read_count`。

验证：

- `make -C xdebug schema-test contract-test`
- `make -C xdebug unit-test`
- `pytest -q xdebug/tests/contract/test_json_response_contract.py`
- `python3 xdebug/tools/compare_json_samples.py --before xdebug/doc/json_baseline --after xdebug/doc/json_after_cleanup`
- `python3 xdebug/tests/waveform/run_complex_wave.py --xdebug xdebug/xdebug --mode nonaxi`
- `regression/run_xdebug_regression.sh`
- `make test`

提交：`d8aea9c 治理 xdebug JSON 返回冗余`

## 二、阶段二：xout 渲染职责整理

本阶段把通用渲染器收敛为基础渲染，不再为具体 action 写特殊分支。具体 action 需要追加信息时，只能在自己的 handler 中完成。

主要结果：

- `xout_renderer.cpp` 删除 `value.at`、`value.batch_at`、`signal.changes`、`trace.active_driver`、`trace.active_driver_chain`、`scope.roots` 等 action-specific 分支。
- public renderer 只做 header、error、summary、data、warnings、suggested_next_actions 等基础渲染。
- `trace.active_driver` 在自己的 handler 追加 `root_cause`。
- `trace.active_driver_chain` 在自己的 handler 追加 `chain_path`。
- dispatcher 透传 engine handler 生成的 `text`，避免基础 renderer 重新包一层导致双 header 或 action 特判。
- 新增静态测试，禁止 `xout_renderer.cpp` 出现 action-specific 分支。

APB/AXI 补充验证：

- 按 `<xring-repo>/dv/cfg/Makefile` 设置：
  - `SVT_VIP_INCDIR=<legacy-axi-vip-root>/include/sverilog`
  - `SVT_VIP_SRCDIR=<legacy-axi-vip-root>/src/sverilog/vcs`
- APB nonaxi fixture 通过，覆盖 `apb.config.load/list/query/cursor/transfer_window`。
- APB VIP real 通过，覆盖真实 VIP 编译、仿真、FSDB 生成和 xdebug 查询。
- AXI real fixture 通过，覆盖 `axi.config.*`、`axi.query`、`axi.cursor`、`axi.analysis`、`axi.request_response_pair`、`axi.latency_outlier`、`axi.outstanding_timeline`、`axi.channel_stall`、`axi.export`。

验证：

- `make -C xdebug`
- `make -C xdebug unit-test`
- `pytest -q xdebug/tests/contract/test_json_response_contract.py xdebug/tests/combined/test_active_semantics.py`
- `python3 xdebug/tests/waveform/run_complex_wave.py --xdebug xdebug/xdebug --mode nonaxi`
- `python3 xdebug/tests/waveform/run_complex_wave.py --xdebug xdebug/xdebug --mode axi --skip-build`
- `SVT_VIP_INCDIR=... SVT_VIP_SRCDIR=... pytest -q xdebug/tests/synthetic/test_apb_vip_real.py`
- `SVT_VIP_INCDIR=... SVT_VIP_SRCDIR=... make test`

提交：`d4db418 整理 xdebug xout 渲染职责`

## 三、第三方 review：冷门 wave/design action

本轮 review 重点不是常用 `value.at`、`trace.driver`、`trace.active_driver`，而是平时较少关注、用户很可能不知道用途的 action。

结论：这些 action 大多不是无效 action，而是缺少面向用户的用途说明、诊断结论和下一步建议。当前 JSON 里能看到证据，但 xout 基础渲染后像内部结构 dump，用户不容易判断“我为什么要看它”。

| Action | 当前定位 | 保留建议 | 主要问题 | 建议改进 |
| --- | --- | --- | --- | --- |
| `sequential update view` | 从 RTL 静态 trace 推断寄存器/时序信号的 clock/reset/update rule | 保留 | `rule_count` 很多但缺少一句结论；`confidence low` 不解释影响 | handler 追加 `diagnosis`：clock、reset、更新规则类型、最关键 source line |
| `FSM explanation view` | 基于 sequential rules 抽取状态跳转 | 保留但应标 experimental 或输出更清楚 | 现在只是把 `rules/transitions` 展开，不能说明“这是 FSM 还是普通寄存器” | summary 增加 `fsm_like`、`state_count/transition_count`、`dominant_conditions` |
| `counter explanation view` | 静态判断某个 RTL 信号是否像计数器 | 保留 | `counter_like=true` 有价值，但 xout 没突出 increment/decrement/hold/reset | 追加 `counter_summary`，列出 reset、increment 条件、hold 条件 |
| `procedural assignment view` | 展开 always/assign 里的分支赋值和控制依赖 | 保留 | 信息量大，但容易和 `trace.driver` 重叠；缺少“为何需要单独调用” | 明确定位为 branch-level assignment view，突出 `branch_count/default_count` 和前几条 branch source |
| `control explanation view` | 只看控制条件，不看 data RHS | 保留 | 价值明确但输出太像 `trace.driver` 子集 | summary 增加 `top_conditions`；xout 追加 condition -> source line |
| `expr.normalize` | 把 signal driver RHS 或 raw expr 归一成 AST/信号依赖 | 保留为辅助 action | 对终端用户不直观，更像给 AI/后续 action 用 | 在 action 描述里标注“表达式规范化/调试辅助”，不要当主诊断入口 |
| `port.trace` | 实例端口连接 + 每个端口的 trace | 保留 | 与 `instance.map` 高度接近，但多了 trace；名字容易误解为“查单个 port” | 文档和 summary 改成 instance port trace；可考虑支持单 port 过滤 |
| `instance.map` | 查 instance 的端口 highconn/lowconn 映射 | 保留 | 输出足够，但 xout 表格化不足 | handler 可追加端口映射表 |
| `interface.resolve` | 查 interface/modport 端口连接 | 保留 | 对 modport 支持是否充分不明显；空 `modport_ports` 不解释 | 当 modport 为空时给 reason；突出 resolved object |
| `scope.roots` | 自动判断 waveform/design 的可查询根 | 保留 | 对用户有用，当前 limitations 能解释 design missing | xout 应突出 recommended_root 和 wave/design mismatch |
| `signal.canonicalize` | 把用户输入 signal 规整到 canonical RTL/FSDB 路径 | 保留 | 当前大量 null/empty 让人以为没做事 | 空字段不要输出；追加 canonical decision path |
| `counter.statistics` | 波形侧 clock-sampled counter min/max/avg/valid/unknown 统计 | 保留 | 功能明确，但 summary 字段过多、缺少单位说明 | time 字段统一带单位；xout 分组为 target/window/result |
| `sampled_pulse.inspect` | 查 valid 在 clock 采样下是否丢脉冲/有风险 | 保留但应加强样例 | 当前样本 `risk_count=0`，看起来像没用；实际适合检查短脉冲跨采样丢失 | 增加一个有风险 fixture；xout 明确 raw_valid_transition_count vs sampled_high_cycles |

## 四、是否存在“没用 action”

暂未发现必须删除的 action。

更准确的判断是：

- `expr.normalize` 是内部/AI 辅助价值更强，不适合作为普通用户主入口。
- `port.trace` 和 `instance.map` 有重叠，但 `port.trace` 多了 trace 信息，不应直接删除。
- `FSM explanation view`、`counter explanation view`、`sequential update view` 共享底层 sequential 推断，当前最大问题是输出没有告诉用户“该信不信”和“下一步看哪里”，不是功能完全无效。
- `sampled_pulse.inspect` 需要更好的正例，否则用户很难理解它和 `signal.changes`、`signal.statistics` 的区别。

## 五、后续 P0/P1 建议

P0：

- 给 `sequential update view`、`FSM explanation view`、`counter explanation view`、`procedural assignment view` 添加各自 handler 的 xout 追加信息，重点输出诊断结论，不在通用 renderer 做 action 特判。
- 给上述 action 的 JSON summary 增加必要的结论字段，例如 `fsm_like`、`counter_like`、`primary_clock`、`primary_reset`、`top_condition_count`。
- 修正 `sampled_pulse.inspect` 的 schema/spec required_args，目前实现要求 `clock` 和 `valid`，spec 中却写 `signal`。

P1：

- 为 `sampled_pulse.inspect` 增加有风险波形 fixture。
- `port.trace` 支持单 port 过滤，减少整实例端口列表噪音。
- `signal.canonicalize` 不输出 null/empty 决策字段，改为输出 canonical decision path。
- 在 help/spec 中把 `expr.normalize` 标为辅助 action，避免用户把它当终端诊断入口。

## 六、最终验证结论

本次修复满足：

- JSON 冗余从源头治理，不靠 fallback 或后处理屏蔽。
- 通用 xout renderer 不包含具体 action 特殊渲染。
- 特殊追加信息位于 action 自己的 handler。
- APB 与 AXI 均已纳入本次 goal 验证。
- 全仓库 `make test` 已在沙箱外通过；这是按用户要求执行，因为测试包含 license、NPI、FSDB、仿真和真实进程通信动作。
