# 协议分析模式

协议分析器建议分两阶段实现：

1. 在时钟沿采样所有相关信号。
2. 在采样行上运行纯 Python 状态机。

这样可以让 pynpi 访问逻辑保持简单，也让协议逻辑能够在没有 license 的情况下做单元测试。

所有协议脚本必须基于同一个 clock 的上升沿或下降沿采样行来判断 transfer、stall、latency 和 outstanding；不要直接用任意时间点、信号变化点或不同信号各自的变化时间拼协议事件。默认建议下降沿（`clock_edge: "negedge"` / `posedge: false`），因为它通常比上升沿更能避开 DUT/monitor 同沿更新竞争；只有协议规范或 monitor 采样点明确要求上升沿时才改用 `posedge`。

## APB

必需配置项：

```json
{
  "clk": "top.pclk",
  "rst_n": "top.presetn",
  "psel": "top.psel",
  "penable": "top.penable",
  "pwrite": "top.pwrite",
  "paddr": "top.paddr",
  "pwdata": "top.pwdata",
  "prdata": "top.prdata",
  "pready": "top.pready",
  "pslverr": "top.pslverr",
  "clock_edge": "negedge"
}
```

代码模式：

```python
def is_posedge(cfg):
    edge = str(cfg.get("edge", cfg.get("clock_edge", ""))).lower()
    if edge in {"posedge", "pos", "rising"}:
        return True
    if edge in {"negedge", "neg", "falling"}:
        return False
    return bool(cfg.get("posedge", False))

rows = edge_samples(fp, cfg["clk"], signals, posedge=is_posedge(cfg))
result = apb_summary(rows, cfg)
```

当配置了 `pready` 时，completion 条件是 `psel && penable && pready`。如果没有配置 `pready`，每个 enabled cycle 都计为一次事务。

## AXI

使用独立 channel handshake：

- AW: `awvalid && awready`
- W: `wvalid && wready`
- B: `bvalid && bready`
- AR: `arvalid && arready`
- R: `rvalid && rready`

helper 会跟踪 pending writes、pending reads、ID、latency 和 outstanding samples。

配置 key 与 channel 信号名保持一致，例如 `awaddr`、`awid`、`awvalid`、`awready`、`wdata`、`wlast`、`bid`、`bresp`、`araddr`、`rid`、`rdata`、`rlast`。

## Stream

必需配置项：

```json
{
  "clock": "top.clk",
  "clock_edge": "negedge",
  "valid": "top.valid",
  "ready": "top.ready",
  "data": "top.data",
  "sop": "top.sop",
  "eop": "top.eop",
  "fields": {"opcode": "top.opcode"}
}
```

transfer 条件是 `valid && ready`。如果没有配置 `ready`，则 valid 单独成立就表示 transfer。

使用 stall window 查找 backpressure：

```python
result = stream_summary(rows, cfg)
```

## 验证规则

协议示例的定位是脚本模板。对真实项目输出最终数字之前，第一次实现应先和下面任一来源对齐：

- xdebug protocol action 输出；
- UVM monitor log；
- 已知 transaction scoreboard。
