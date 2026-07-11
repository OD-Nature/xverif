---
name: x-npi
description: 当 AI agent 需要使用 Synopsys pynpi 编写 Python 脚本，进行批量 FSDB 波形统计、值扫描、APB/AXI/valid-ready stream 协议分析、VCS/Verdi coverage database 查询，或静态设计 driver/load 查询时使用。离线大规模分析脚本和报告优先使用本 skill；xdebug 风格的实时 active-driver 根因定位或 PVC active-driver 检查不要使用本 skill。
---

# x-npi

x-npi 用来教 AI agent 编写可复用的 Python `pynpi` 批量分析脚本。交互式会话查询和 active-driver 因果追踪继续使用 xdebug；当任务需要扫描大量信号、时间窗口、事务、coverage database 或设计 handle 时，使用 x-npi。

版本边界：coverage脚本要求目标 Verdi提供 Python `pynpi.cov`（例如2023路径）。
Verdi O-2018.09-SP2没有可用的 Python coverage API，2018 VDB查询必须使用 xcov
native worker；不得静默 fallback到 URG HTML。

## 任务路由

| 任务 | 优先阅读 |
| --- | --- |
| 配置 `VERDI_HOME`、导入 `pynpi`、管理 `npisys.init/end` | [references/pynpi-runtime.md](references/pynpi-runtime.md) |
| 读取 FSDB 值、变化、统计信息或时钟沿采样 | [references/waveform-patterns.md](references/waveform-patterns.md) |
| 提取 APB、AXI 或 valid-ready stream 摘要 | [references/protocol-patterns.md](references/protocol-patterns.md) |
| 查询 VCS/Verdi coverage database、coverage holes 或 functional coverage bins | [references/coverage-patterns.md](references/coverage-patterns.md) |
| 从 daidir/design DB 查询静态 driver/load 事实 | [references/design-trace-patterns.md](references/design-trace-patterns.md) |

## 可复用 helper

可 import 的 helper 包位于 `scripts/x_npi/`。

```python
from x_npi.runtime import pynpi_lifecycle
from x_npi.wave import open_fsdb, edge_samples
from x_npi.protocol import axi_summary
from x_npi.coverage import open_covdb, coverage_items
```

运行示例时，可以把 skill 的 `scripts` 目录加入 `PYTHONPATH`，也可以直接执行 `scripts/examples/` 下的文件。

## 决策规则

- 针对已经打开的 xdebug 会话做一次性 AI debug 时，使用 xdebug。
- 需要批量 FSDB 扫描、事务提取、coverage database 查询、值分布统计或报告生成时，使用本 skill 编写 Python 脚本。
- 做波形协议分析、事务统计、窗口验证或跨信号相关性判断时，必须基于同一个 `clock` 的上升沿或下降沿采样后再分析，不能用任意时间点或信号变化点直接下结论。默认建议使用下降沿（`clock_edge: "negedge"` / `posedge: false`），因为它通常避开 DUT/monitor 在上升沿附近的更新竞争；只有接口规范或 monitor 明确要求上升沿时才改用 `posedge`。
- 需要 active-driver、active-driver-chain、`activeTime`、PVC active check、force/root-cause 分类，或在某个症状时间点做接口因果追踪时，改用 xdebug/C++ NPI。当前 Python `pynpi` 不暴露这些 active trace 所需 API。
- 普通 coverage item百分比必须用 `covered / coverable` 计算；`count` 是
  hit/sample count，不是 coverage pct。跨 metric的 scope Score若要对齐 Verdi GUI，
  应对有效 metric百分比等权平均，并另存 raw weighted ratio。
- coverage hole 输出必须保留 `excluded`、`unreachable`、`illegal` 等 status flags；bin 缺 file/line 时继承最近父对象 evidence，并标记继承来源。
- 脚本输出优先使用 JSON。文本或 Markdown 报告应从结构化 JSON 派生，不要从临时终端输出拼接。
- 当环境需要 Synopsys license 访问时，真实 `pynpi`/FSDB/daidir 验证应在受限沙箱外运行。

## 示例入口

- `scripts/examples/wave_stats.py`
- `scripts/examples/apb_summary.py`
- `scripts/examples/axi_summary.py`
- `scripts/examples/stream_summary.py`
- `scripts/examples/coverage_summary.py`
- `scripts/examples/trace_driver_summary.py`
