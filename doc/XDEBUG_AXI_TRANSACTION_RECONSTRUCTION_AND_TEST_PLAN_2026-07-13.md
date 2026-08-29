# xdebug AXI 配对修复与强化测试计划

日期：2026-07-13
状态：已实现并完成 AXI 专项验收

## 1. 启动与 Goal 约束

在任何源码修改、fixture 生成或测试执行前，以本计划创建不设 token budget 的 goal：

> 按 `doc/XDEBUG_AXI_TRANSACTION_RECONSTRUCTION_AND_TEST_PLAN_2026-07-13.md` 完成 xdebug AXI 事务重建核心统一、AW/W 任意先后支持、固定 delay 与固定 seed 随机 VIP 测试、AXI action 合同、XDTE 实机验收、skill 同步及中文 Git 交付。

Goal 创建后持续执行本计划。只有所有必需测试、文档同步和验收完成后才能标记
`complete`。环境或 license 临时失败不视为完成，也不允许静默 fallback。

## 2. 协议基线与目标

Arm AMBA AXI and ACE Protocol Specification 的 channel relationship 规定：

- AW、W 是独立通道，写数据可以在写地址之前出现，也可以同周期出现；
- AXI4 没有 WID，W burst 必须按对应 AW transaction 的顺序传输，不能在写事务之间交织；
- B 响应必须在对应 AW handshake 和最后一个 W handshake 完成后产生。

规范链接：
<https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/IHI0022H_amba_axi_protocol_spec.pdf>

本轮聚焦 AXI，不纳入 `window.verify/counter.statistics line_limit`、`list.diff`、
`sampled_pulse.inspect` 和 stream 通用合同问题。

## 3. AXI 核心实现

- 建立唯一事务重建核心，供 query、analysis、pair、timeline、outlier、cursor 和
  export 共用；删除 exporter 中重复的配对状态机。
- 每个采样点依次接收 AW/AR/W、缓存带 WLAST 边界的 W burst、按 AW 顺序绑定写数据、
  处理 B/R，最后记录 outstanding。
- 支持 AW 先、同周期 AW/W、W 先、整个 W burst 先于 AW，以及多个 W burst 在多个
  AW 前到达。
- 不同 ID 的 B 可以乱序返回；相同 ID 保持顺序；W 数据严格按 AW transaction 顺序绑定。
- 保存 `aw_time/first_w_time/last_w_time/b_time` 和
  `phase_order=aw_before_w|same_cycle|w_before_aw`。
- B 在本事务 AW 或 WLAST 同周期或更早发生时，保留事务并报告
  `response_dependency_violation`。
- 公开五通道 handshake、pending AW/AR、孤立 W/B/R、beat mismatch、reset-cleared、
  最终 outstanding 和扫描完整性。

## 4. 固定值与固定 Seed 测试

本机 SVT 文档已确认可使用 `data_before_addr`、`addr_valid_delay`、
`wvalid_delay[]` 及对应 reference event 精确控制 AW/W 相对时序。

### 4.1 固定 Delay 矩阵

| 场景 | 关键配置 | 必须观察到 |
| --- | --- | --- |
| AW 先、W 后 | AW delay=0；first W 以 AW handshake 为参考，delay=5 | `aw_time < first_w_time` |
| AW/W 同周期 | AW/W valid delay=0；AWREADY/WREADY delay=0 | `aw_time == first_w_time` |
| W handshake 先于 AW | `data_before_addr=1`；W delay=0；AW 在 first W handshake 后 delay=5 | `first_w_time < aw_time` |
| 整个 W burst 先于 AW | 4-beat 连续 W；AW delay=8 | `last_w_time < aw_time` |
| WVALID 先但 handshake 后 | WVALID delay=0；WREADY 固定延迟；AWREADY=0 | VALID 顺序与 handshake 顺序被分别记录 |
| 混合 outstanding | 4 ID、32 笔写，循环前三种顺序并设置不同 B delay | 配对正确、B 可跨 ID 乱序、最终 outstanding=0 |

固定矩阵在一个专用 UVM test 中执行，每类输出稳定 case tag、实际 delay 和期望事务数。

### 4.2 固定 Seed 随机 Delay

- 固定 seed：`7`、`19`、`73`，每个 seed 独立生成 FSDB 和日志。
- 每个 seed 执行 256 笔 write、64 笔 read：
  - ID 0--7；
  - burst length 1/2/4/8/16；
  - outstanding depth 8；
  - `data_before_addr` 随机；
  - AW/W valid delay 0--16 cycle；
  - beat 间 WVALID delay 0--8 cycle；
  - AWREADY/WREADY delay 0--12 cycle；
  - BVALID delay 0--32 cycle。
- 每个 seed 开头注入 AW-first、same-cycle、W-first 三笔 anchor transaction，保证覆盖
  不依赖随机碰运气。
- 日志记录 seed、transaction sequence、ID、地址、burst、全部 delay 和
  `data_before_addr`。
- 每个 seed 必须满足：
  - 三种 phase order 均非零；
  - 至少一笔完整 W burst 先于 AW；
  - 单拍、多拍、W beat gap 均有覆盖；
  - 不同 ID 的 B completion 乱序非零；
  - completed 等于 stimulus；
  - pending、unmatched、dependency violation 均为零。
- 固定 seed 未达要求时直接失败，不更换 seed 重试。

### 4.3 独立 Oracle

- 新增 SVT port-monitor callback，在 `write_address_phase_ended`、
  `write_data_phase_ended`、`write_resp_phase_ended` 记录真实 handshake。
- 输出 `txn_seq/id/address/beat/aw_time/w_time/b_time/case/seed` 结构化记录。
- Python 验证比较 callback oracle、VIP scoreboard、xdebug
  pair/analysis/timeline/export；禁止以 xdebug 自身结果作为期望值。
- fixture 只编译一次，运行现有 stress、固定矩阵和三个随机 seed，发布五组
  FSDB/log；普通 gate 只消费缓存。

## 5. AXI Action 合同

- `axi.config.load` 保存前验证 resolved path、dump/readability、width、clock edge 和
  关键位宽关系。
- `axi.analysis(latency)`：
  - read：AR handshake 到 RLAST handshake；
  - write：AW handshake 到 B handshake；
  - 返回 read/write 分项、phase-order 计数、completed/unmatched、端点及完整性。
- `axi.analysis(osd)` 返回 read/write current/final、peak、peak time、average 和增减
  事件定义。
- `axi.analysis(outstanding)` 返回窗口末未闭合事务，不再复用 OSD。
- pair、timeline、outlier 统一支持 `direction=all|read|write`：
  - pair 返回 phase timestamps、配对规则和 pending/unmatched；
  - timeline 返回 final、peak 和 change-point 原因；
  - outlier 分析完整集合后再限制展示，支持显式 `top_n` 或 `threshold`。
- 保持既有字段兼容；新增字段采用 additive 方式；实验性 action 暂不升级 stable。

## 6. 测试、验收与交付

- 性能是硬门禁：同一 session/config 只允许一次全量 FSDB AXI 扫描，后续
  query/analysis/pair/timeline/outlier/cursor/export 必须复用 canonical result；不得为
  正确性增加第二遍隐藏扫描。
- 使用现有 AXI VIP fixture 与固定 XDTE FSDB 各做 3 次 cold/warm 测量：单次 cold
  analysis 的 wall time 中位数退化不得超过 10%，峰值 RSS 退化不得超过 15%；连续
  `analysis -> pair -> timeline -> outlier -> export` 的总 wall time 不得比当前基线更慢，
  并记录 scanner invocation count=1。超过门限即视为失败，先优化再继续交付。
- 纯 C++ 单测覆盖固定矩阵及 seed 7/19/73 的模型级随机事件流，包括多 W burst 先于
  AW、同 ID 顺序、跨 ID B 乱序、reset、孤立响应、beat mismatch 和非法 B 依赖。
- 现有 AXI VIP 3200 write/3200 read stress 继续通过；新增 fixture 全部通过 VIP
  checker、scoreboard 和 oracle 对比。
- 沙箱外固定 XDTE FSDB 验收：
  - AR/R/AW/W/B=`2167/7175/958/2323/958`；
  - completed read/write=`2167/958`；
  - peak/final read=`4/0`、write=`2/0`；
  - max accepted latency read/write=`540ns/280ns`；
  - pending/unmatched 均为 0。
- 执行门禁：
  - fast：`xdebug.static`、`skills.xverif`、`skills.public_docs`；
  - 沙箱外 regression：`xdebug.cpp_unit`、`xdebug.action_runtime_catalog`、
    `xdebug.contract`，随后全量 regression；
  - 沙箱外重新 prepare 并 validation 扩展后的 `xdebug.axi_vip` fixture；
  - 沙箱外 nightly focused：`xdebug.axi_vip`；
  - 最终沙箱外执行 `make -C xdebug clean all`。
- 同步 schema、examples、actions.yaml、架构说明、catalog、fixture manifest 和
  xverif skill；安装 skill 后对 Codex/Claude 镜像执行 `diff -qr`。
- 按实现核心、公共合同、VIP/实机验收拆分中文详细提交。每次提交前执行
  `git status --short`，只显式暂存相关文件。

## 7. 实现与验收记录

- 独立 oracle 最终采用 testbench 顶层 raw-pin handshake sampler，而不是复用 VIP
  transaction callback；它按 AW/W/B/AR/R 引脚独立重建，因此与 xdebug 不共享配对逻辑。
- fixture 发布 stress、固定 delay、固定 seed 7/19/73 五组产物。随机组每个 seed 实际
  执行 256 write 和 256 read，读事务数高于原计划的 64；每组都覆盖 AW-first、same-cycle、
  W-first，且至少一笔完整 W burst 在 AW 前握手完成。
- 同一 stress FSDB、同一 `analysis -> pair -> timeline -> outlier -> export` 工作流各测
  3 次：HEAD 总 wall time 中位数 7.837 s，当前实现 6.887 s，改善约 12.1%；峰值 RSS
  中位数由 63,124 KB 变为 63,364 KB，增加约 0.38%；`full_scan_count=1`。
- XDTE 固定 FSDB 实测五通道 handshake、completed、peak/final outstanding、最大 read/write
  latency 和 pending/orphan 均与第 6 节期望完全一致。
- `xdebug.axi_vip` prepare、全量 fixture validation、nightly focused、最终 clean build、
  `xdebug.static`、`skills.xverif`、`skills.public_docs`、`xdebug.cpp_unit` 和
  `xdebug.action_runtime_catalog` 均通过。
- 全量 regression 为 521 passed、2 failed；两个失败均为 HEAD 独立归档可复现的既有
  schema sync 漂移（`session.open` hint 与 16 个非 AXI runtime schema），本次没有批量
  修改这些无关合同。
