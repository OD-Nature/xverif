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

x-npi 的下降沿快路径扫描 clock VCT，再批量读取同一时刻的信号；上升沿 `before/after` 语义使用已安装 `pynpi.waveform.TimeBasedHandle` 按时间归并同 timestamp 的变化。

波形处理默认要求显式选定时钟边沿：

- 默认使用 `edge="negedge"`，且不得携带 `sample_point`。
- 只有接口规范、采样 monitor 或既有 scoreboard 明确要求上升沿时，才使用 `edge="posedge"`，并显式选择 `sample_point="before"` 或 `"after"`。
- `clock_edge`、布尔 `posedge` 等旧字段会被明确拒绝，不做兼容猜测。
- 不要用任意时间点、单个信号的变化点或多个信号各自的变化点直接构造协议结论。

```python
from x_npi.wave import iter_edge_samples

rows = iter_edge_samples(
    fp,
    clock="top.clk",
    signals=["top.valid", "top.ready", "top.data"],
    begin=0,
    end=100000,
    edge="negedge",
)
```

`iter_edge_samples` 是 single-use 流式 iterable，并在消费后通过 `rows.context`
提供 sample count、首末采样时间、是否完整和停止原因。`edge_samples` 保留为物化包装器。

每行结果格式：

```json
{"time": 1234, "values": {"top.valid": "1", "top.ready": "1"}}
```

对于很大的 FSDB，务必传入 begin/end 时间窗口和最大 edge 数。先用
`preflight_signals` 一次性检查所有必需信号；缺失时返回 requested path 和同层/有限层级候选，
不要扫描到一半才报错。

## 已知限制

- 下降沿 detection 基于 clock VCT 值变化扫描；上升沿使用当前安装版本公开的 `TimeBasedHandle`。
- 对 edge 敏感的协议脚本，在信任统计数字之前应先和 xdebug 或 monitor log 对齐；如果 posedge/negedge 结果不一致，优先调查采样边沿和 monitor clocking block，而不是先改协议状态机。
- handshake 相关 valid/ready/PREADY 出现 X/Z 时，不计为 transfer，并把 `analysis_quality` 标成 `ambiguous`，同时返回 unknown 计数与首个时间。
