# AXI SVT VIP real-wave fixture

本 fixture 用真实 Synopsys SVT AXI VIP、真实 VCS 仿真和真实 FSDB/daidir
验证 xdebug 的 AXI 查询链路。仓库内的 pin-level bridge 连接 SVT master/slave
agent，slave sequence 提供 memory 行为；编译拆分、宏、UVM、KDB 和 FSDB
选项与 xuvm_gen 生成的 `cfg/Makefile` 保持一致。

## 依赖

- `SVT_AMBA_VIP_HOME`：SVT AMBA VIP release 根目录。
- `SVT_COMMON_HOME`：SVT common release 根目录。
- `DESIGNWARE_HOME`：包含 `vip/svt` 的 Synopsys VIP 安装根目录。
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

写通道每四笔事务固定覆盖 AW 先握手、W 先握手、AW/W 同周期以及固定 seed
随机 delay；slave response 每四笔覆盖 0、4、17 cycle 固定 delay 和固定
seed 的 50–100 cycle 随机 delay。pin 级 AW/W/B/AR/R 握手写入独立的
`axi_handshake.jsonl`，避免大规模 oracle 日志拖慢仿真 stdout；pytest 直接从
该文件独立重建事务并与 xdebug 的 `phase_order`、beat count 和响应依赖诊断核对。
oracle 同时记录 AW/AR/W/R 当前 payload 的 `valid_begin_time_ps`，并用五通道的
握手时间逐项测试 `axi.query(query.channel, query.handshake_time)`；W/R 覆盖首拍、
中间拍和 last，另有精确时间未命中用例，禁止 nearest-time fallback。

输出位置由 `manifest.json` 定义，`out/` 不进入版本库。pytest 会检查：

- 仿真无 UVM error/fatal，scoreboard 通过；
- 固定 delay 与固定 seed 随机 delay profile 均命中，且 W-before-AW 被实际观察；
- FSDB 和 daidir 均真实生成；
- `axi.config.load/list`、transaction query、五通道精确 handshake query、cursor；
- `axi.analysis` 的 latency、osd 和 pending 三种模式；
- request/response pairing、latency outlier、outstanding timeline；
- channel stall 采样；
- session 打开、复用和清理。
