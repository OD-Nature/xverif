# xdebug AXI 时间查询、Schema 收口与 XOUT 一致性计划

日期：2026-07-14
状态：完成

## 1. Goal 与交付边界

本计划写入仓库后，以如下目标创建不设 token budget 的 goal：

> 按本计划完成 xdebug AXI channel/handshake_time 精确查询、valid_begin_time 与 beat
> 时间采集、pending 命名收口、include_data 公共合同、全部 AXI response schema
> 收紧、XOUT 对齐渲染、VIP/oracle 回归及性能验收。

实现不得增加第二遍 FSDB 扫描，不得对失败环境静默 fallback。所有 NPI、VCS、VIP、
FSDB、真实 EDA、contract runtime 和 regression 动作直接在沙箱外执行。

## 2. 公共接口

`axi.query` 新增精确握手查询：

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "axi0",
    "query": {"channel": "w", "handshake_time": "120ns"},
    "output": {"include_data": false}
  }
}
```

- `query.channel` 取值为 `aw|w|b|ar|r`，与 canonical 带单位字符串
  `query.handshake_time` 成对出现。
- 精确握手模式由 channel 推导方向，不得同时传 `direction`、`query.index`、
  `query.line_limit`、`address/addr`、`id` 或 `last`；时间只做精确匹配，不做邻近查询。
- 保留现有 transaction 查询模式；`args.id` 正式加入 schema。`address` 为推荐字段，
  `addr` 保留兼容，但同时出现时明确报错。
- `axi.query`、`axi.request_response_pair`、`axi.latency_outlier` 统一使用
  `output.include_data`，默认 `false`，删除 `output.verbose`，不保留 alias。
- `axi.analysis.analysis=outstanding` 改名为 `pending`，输出使用 `pending_count`、
  `returned_pending_count`、`pending_transactions`。`osd` 和
  `axi.outstanding_timeline` 保持原名。

## 3. 采集、索引与返回

- AW/AR 保存 payload 的 `valid_begin_time` 与 `handshake_time`。
- W/R 保存第一拍 `valid_begin_time`、`first_handshake_time`、
  `last_handshake_time`，并为每个 beat 保存握手时间。
- B 保存 `handshake_time`；读事务完成时间为 RLAST 握手时间。
- `valid_begin_time` 是当前 payload 首次被采样为 VALID 并持续到本 beat handshake 的
  时间，不是字面 VALID 上升沿。back-to-back VALID 连续为 1 时，前一 beat 握手后的
  下一采样点开始新 payload。
- W-before-AW 时，W beat 的 valid/handshake 时间随缓存保存，绑定 AW 后不得重算。
- 不增加 FSDB 信号或第二遍扫描。每笔事务保存紧凑 beat 时间数组；首次时间查询时
  延迟建立五通道排序索引，后续二分查询并复用缓存。
- 默认响应不序列化 beat payload；`include_data:true` 时，W beat 返回
  `index/handshake_time/data/wstrb/last`，R beat 返回
  `index/handshake_time/data/resp/last`。

query、cursor、pair、outlier 和 analysis slowest 统一使用 address/data/response 分组：

```json
{
  "direction": "write",
  "phase_order": "aw_before_w",
  "address": {
    "channel": "aw",
    "valid_begin_time": "90ns",
    "handshake_time": "100ns",
    "addr": "f0", "id": "1", "len": "3", "size": "2", "burst": "1"
  },
  "data": {
    "channel": "w",
    "valid_begin_time": "105ns",
    "first_handshake_time": "110ns",
    "last_handshake_time": "130ns",
    "beat_count": 4,
    "expected_beat_count": 4
  },
  "response": {"channel": "b", "handshake_time": "150ns", "resp": "0"}
}
```

精确查询额外返回 `data.match`；W/R 命中时含 1-based `beat_index`。未观察到的阶段
直接省略，不用 `0ns` 表示。AXI export 文件格式保持现有 TSV/CSV 合同。

## 4. Schema 与 XOUT

- 新增 AXI response schema 同步脚本，以公共 envelope、transaction、phase、beat 和
  diagnostics 定义生成全部十个独立 schema，并支持 `--check`。
- 十个 AXI response 的顶层、`summary`、`data`、嵌套对象和数组 item 全部关闭未知字段；
  成功与错误响应分别约束，并显式允许统一 envelope 字段。
- `axi.analysis` 按 `latency|osd|pending` 分支约束；`axi.query` 按 count、单笔、列表、
  精确命中和未命中分支约束。
- 同步 actions.yaml、request/response examples、action reference、response-fields、
  xdebug agent 说明和 xverif skill；不批量改写无关非 AXI baseline drift。
- XOUT 保持 `@xdebug.<action>.v1`、section、键值块和 table 风格。同一连续键值块按最长
  key 对齐冒号，不同 section 独立计算宽度；table 继续按列宽对齐。

默认紧凑查询示例：

```text
@xdebug.axi.query.v1

summary:
  name      : axi0
  query_mode: handshake
  found     : true

match:
  channel       : w
  handshake_time: 120ns
  beat_index    : 2

transaction:
  direction  : write
  phase_order: aw_before_w

address:
  channel         : aw
  valid_begin_time: 90ns
  handshake_time  : 100ns
  addr            : f0
  id              : 1
  len             : 3
  size            : 2
  burst           : 1

data:
  channel              : w
  valid_begin_time     : 105ns
  first_handshake_time : 110ns
  last_handshake_time  : 130ns
  beat_count           : 4
  expected_beat_count  : 4

response:
  channel       : b
  handshake_time: 150ns
  resp          : 0
```

`include_data:true` 追加：

```text
beats:
  index  handshake_time  data      wstrb  last
  1      110ns           11223344  f      false
  2      120ns           55667788  f      false
  3      125ns           99aabbcc  f      false
  4      130ns           ddeeff00  f      true
```

## 5. 测试与性能门禁

- C++ tracker 覆盖 AW/AR/W/R stall、back-to-back VALID、同周期、W-before-AW、整 burst
  先于 AW、reset、未完成事务和每 beat 时间保存。
- Schema contract 覆盖 channel/time 成对必填、selector 互斥、`id`、`verbose` 拒绝、
  `include_data`、全部 AXI response 合法分支和未知字段拒绝。
- 扩展现有固定 delay 与 seed `7/19/73` AXI VIP fixture；oracle 同时记录 valid begin
  和五通道握手，查询 AW/W/B/AR/R，并覆盖 W/R 首拍、中间拍、last、found-false、
  W-before-AW 与 back-to-back VALID。
- compact、include-data、read/write、found-false、pending 和错误响应均增加 XOUT golden
  test，固定分组、顺序、冒号位置、表头、空数组和截断提示。
- scanner invocation count 必须为 1；cold analysis 中位数退化不超过 10%，峰值 RSS
  不超过 15%，warm channel/time 查询中位数不超过同 session `query.index` 的 2 倍；
  AXI 连续工作流总耗时不得劣于既有验收基线。
- 最终执行 schema/example/hint 检查、fast gate、AXI C++ unit、沙箱外 contract、AXI VIP
  prepare/validation/nightly focused、全量 regression 和 clean build，并验收 Codex/Claude
  skill 镜像。

## 6. Git 交付

按“采集与索引”“公共查询和返回合同”“全 AXI schema/XOUT”“VIP与性能验收”
“文档与 skill”拆分中文详细提交。每次提交前检查 `git status --short`，显式暂存文件，
保留并纳入本轮已确认的 `AGENTS.md` 修改。

## 7. 实施与验收结果

已完成本计划全部公共合同与实现：

- 协议依据采用 Arm 官方
  [AMBA AXI and ACE Protocol Specification IHI 0022H](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/IHI0022H_amba_axi_protocol_spec.pdf)：
  A3.3 明确除规定依赖外通道间没有其它关系，写数据可以先于对应写地址出现在接口，
  也可以同周期出现；因此 W-before-AW 是合法顺序，不能当协议错误。
- AW/AR 记录 `valid_begin_time` 和 handshake，W/R 记录第一拍 valid begin、首末拍及
  每 beat handshake，B 记录 handshake；W-before-AW 与 back-to-back VALID 由 tracker
  和 VIP oracle 双重覆盖。
- `axi.query` 支持五通道精确 `channel + handshake_time` 查询，五通道索引首次使用时
  延迟建立；未命中不做邻近 fallback。
- AXI transaction 统一为 `address/data/response` 分组；`include_data`、`pending` 和
  全部十个 AXI response schema 已收口，XOUT 连续键值块按最长 key 对齐冒号。
- AXI VIP 固定 delay、随机固定 seed `7/19/73`、multi-ID stress fixture 已重新生成并
  通过全量 fixture validation；后续 schema、Python 和空格修改均复用缓存，没有再次
  生成波形。

性能在同一份 stress FSDB、独立 HOME/session、每版三次取中位数下比较：

| 指标 | HEAD | 当前实现 | 变化 | 门禁 |
| --- | ---: | ---: | ---: | ---: |
| cold `axi.analysis latency` | 6096.124 ms | 6091.012 ms | -0.08% | 不劣于 10% |
| 公共连续工作流总耗时 | 6576.523 ms | 6584.983 ms | +0.13% | 不劣于既有基线 |
| engine `VmHWM` | 796340 KiB | 798060 KiB | +0.22% | 不劣于 15% |

两版所有 run 的 `full_scan_count` 均为 1。当前 AXI VIP focused 回归还实际执行了五次
warm 精确握手查询与同 session `query.index` 的中位数比率断言，满足不超过 2 倍。

最终验证：

- `validate_schema.py`：152 个 schema 全部通过；`validate_examples.py`：145 个 example
  全部通过；AXI request/hint 定向同步和十个 AXI response generator `--check` 通过。
- fast gate：214 passed。
- xdebug action runtime catalog：1 passed；C++ unit catalog：1 passed。
- AXI VIP nightly focused：1 passed；stream XOUT focused：1 passed。
- clean build 通过；全仓 regression：523 passed，2 failed。两个失败均为实施前已存在且
  与本计划无关的 baseline drift：`session.open` schema hint，以及 16 个非 AXI runtime
  request schema；本计划按边界没有批量改写这些 action。
- `skills.xverif` 与 `skills.public_docs` 已包含在 fast gate 中通过；仓库 skill 已安装到
  Codex/Claude 两个目录，并分别通过 `diff -qr` 一致性验收。
