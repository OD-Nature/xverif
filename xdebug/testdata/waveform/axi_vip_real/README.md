# AXI SVT VIP real-wave fixture

本 fixture 用真实 Synopsys SVT AXI VIP、真实 VCS 仿真和真实 FSDB/daidir
验证 xdebug 的 AXI 查询链路。环境代码来自 `AXI_REFERENCE_ROOT` 指向的
AXI 参考环境；编译拆分、宏、UVM、KDB 和 FSDB 选项参考 xring 的
`dv/cfg/Makefile`。

## 依赖

- `AXI_REFERENCE_ROOT`：包含 `tb/` 和 `tests/` 的 AXI 环境根目录。
- `SVT_VIP_INCDIR`：包含 `svt_axi_if.svi`、`svt_axi.uvm.pkg`。
- `SVT_VIP_SRCDIR`：SVT VIP 的 VCS SystemVerilog source overlay。
- VCS、Verdi/FSDB PLI 和 AXI VIP 运行环境。

仓库不依赖 svtref skill 或其 Python 依赖包；fixture 直接编译并运行真实
VIP 环境。

## 执行

```bash
pytest --xverif-gate nightly --xverif-suite xdebug.axi_vip
```

也可以只构建波形：

```bash
pytest --xverif-prepare xdebug.axi_vip
```

默认固定 seed 7，生成 16 个 ID、每个 ID 200 笔读和 200 笔写，允许每个
ID/方向 4 笔 outstanding，并注入 50–100 cycle 的 slave response delay。
如果参考环境或 SVT VIP 约束无法接受该 delay 区间，fixture/test 约束必须被
修正到真实跑通，不允许把该压力场景降级为可选门禁。

本地 overlay 的 AXI scoreboard 会从 SVT VIP master monitor observed transaction
打印机器可解析 golden log：

```text
AXI_EXPECTED_TXN_JSON {"dir":"WR",...}
```

pytest 会解析这些 JSON 行并与 `axi.export` 的 read/write 文件逐项对比。

输出位置由 `manifest.json` 定义，`out/` 不进入版本库。pytest 会检查：

- 仿真无 UVM error/fatal，scoreboard 通过；
- FSDB 和 daidir 均真实生成；
- `axi.config.load/list`、`axi.query/cursor/analysis`；
- request/response pairing、latency outlier、outstanding timeline；
- channel stall 采样；
- session 打开、复用和清理。
