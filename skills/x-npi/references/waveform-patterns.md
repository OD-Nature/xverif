# 波形分析模式

## 单点取值

一次读取多个信号时使用 `waveform.sig_vec_value_at`，避免逐信号重复查找。
单点取值只适合 debug 快照或辅助核对；协议统计、事务提取、窗口验证和跨信号相关性判断必须使用同一个 clock 的 edge 采样结果。

```python
from x_npi.wave import open_fsdb, sample_values

fp = open_fsdb("waves.fsdb")
values = sample_values(fp, ["top.clk", "top.valid", "top.ready"], 1000)
```

## 时间转换

使用 FSDB 自身的 time scale，不要硬编码 ps/ns 换算：

```python
from x_npi.wave import time_in

t = time_in(fp, "20ns")
```

支持的字符串格式是数字加单位，例如 `10ps`、`20ns`、`3us`。

## 值变化统计

统计值变化时使用 VCT 遍历：

```python
from x_npi.wave import value_statistics

stats = value_statistics(fp, "top.u_dut.state", max_changes=100000)
```

helper 会返回 `change_count`、首次/末次变化，以及 value histogram。

## 时钟沿采样

xdebug C++ 侧有 L1 edge cursor。Python `pynpi.waveform` 暴露的是普通 VCT cursor，因此 x-npi 会扫描时钟值变化，并在 Python 中检测 `0->1` 或 `1->0`。

波形处理默认要求显式选定时钟边沿：

- 优先建议下降沿（`posedge=False` / `clock_edge: "negedge"`），更稳妥地避开 DUT 或 UVM monitor 在上升沿附近的同沿更新、clocking block skew 和 delta-cycle 竞争。
- 只有接口规范、采样 monitor 或既有 scoreboard 明确要求上升沿时，才使用 `posedge=True`。
- 不要用任意时间点、单个信号的变化点或多个信号各自的变化点直接构造协议结论。

```python
from x_npi.wave import edge_samples

rows = edge_samples(
    fp,
    clock="top.clk",
    signals=["top.valid", "top.ready", "top.data"],
    begin=0,
    end=100000,
    posedge=False,
)
```

每行结果格式：

```json
{"time": 1234, "values": {"top.valid": "1", "top.ready": "1"}}
```

对于很大的 FSDB，务必传入 begin/end 时间窗口和最大 edge 数。

## 已知限制

- Python edge detection 是基于值变化的扫描，不等同于 C++ L1 `npi_fsdb_goto_next_edge` API。
- 对 edge 敏感的协议脚本，在信任统计数字之前应先和 xdebug 或 monitor log 对齐；如果 posedge/negedge 结果不一致，优先调查采样边沿和 monitor clocking block，而不是先改协议状态机。
- 除非分析目标明确要求 unknown propagation，否则 X/Z 值应按 inactive 处理。
