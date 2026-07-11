# APB SVT VIP real-wave fixture

本 fixture 以 AXI fixture 的 package/env/test/sequence/top 分层为模板，并参考
xring 中已运行的 `svt_apb_system_env`、configuration、master sequence、
interface 连接和 `dv/cfg/Makefile` 编译选项，生成真实 APB VIP 波形。

环境包含：

- 5 笔写和 5 笔读；
- byte strobe 写；
- setup/access phase；
- 0–3 cycle wait state；
- back-to-back transfer；
- 一笔 `PSLVERR` response；
- 真实 VCS FSDB 和 daidir。

依赖 `SVT_VIP_INCDIR` 和 `SVT_VIP_SRCDIR`。仓库不依赖 svtref skill 或其
Python 依赖包。

```bash
pytest --xverif-gate nightly --xverif-suite xdebug.apb_vip
```

也可以只生成波形：

```bash
pytest --xverif-prepare xdebug.apb_vip
```

`manifest.json` 定义固定 seed、资源路径和预期 transfer 数。pytest 会同时
检查 UVM 结果与 xdebug 的 `apb.config.load/list`、`apb.query`、
`apb.cursor`、`apb.transfer_window`。

真实 wait-state 波形要求 APB 配置提供可选 `pready`。若还提供 `pslverr`，
transaction 输出会包含 `has_error`。不提供这两个字段时保留旧配置兼容
行为，但无法区分等待周期和完成周期，也无法报告 error response。
