# xverif 全仓测试体系迁移最终验证报告

- 验证时间：2026-07-11（Asia/Shanghai）
- 对应计划：`doc/XVERIF_TEST_ARCHITECTURE_MIGRATION_PLAN_2026-07-10_23-36-25.md`
- 目标分支：`master`
- 结论：迁移目标已实现；测试内容和范围未缩减，required 门禁全部通过；本机未启用 real LSF，nightly 按 catalog 的 optional 合同产生 2 个明确 SKIP，没有 fallback。

## 1. 交付结论

全仓测试已收敛到根级 catalog-driven pytest plugin：

1. `testinfra/catalog.v1.yaml` 是 41 个稳定 suite 的唯一身份和 gate 事实源，schema、语义校验和完整性测试共同保护它。
2. 根级 `pyproject.toml` 是唯一 pytest 配置；裸 `pytest` 返回 usage error，公开入口只有显式 `--xverif-*` 操作。
3. `fast`、`regression`、`nightly` 分别选择 7、28、41 个 suite，集合单调包含；focused suite 只能缩小既定 gate。
4. 19 个生成型数据库 fixture 由 `testinfra/fixtures.v1.yaml` 管理，使用源码、额外依赖和工具环境的内容指纹；cache miss 不自动生成、不降级、不把 required 变成 SKIP。
5. 普通 gate 只消费已发布 fixture；fixture prepare/validation 与测试执行分离。新资产先写入不可变 generation，通过结构和 semantic probe 后再原子替换 `current.json`，并保留旧 generation 供已有读者继续使用。
6. pytest、C++、Vim、MCP、VCS/NPI、VIP、active-trace、realdata/real-LSF 条件项均进入同一选择、preflight、timeout、报告和保留合同。
7. Makefile 只保留构建或显式 fixture builder；旧公共测试 target、两条重复 gate shell、局部 `pytest.ini` 和嵌套 pytest 配置已删除。
8. 没有新增 CI provider 配置。

## 2. 测试范围等价性

迁移没有通过删除用例、降低断言或把 required 改 optional 来获得绿色结果。

| 旧测试面 | 新 catalog suite / fixture | 等价性证据 |
|---|---|---|
| 各组件 Python unit/CLI | `xbit.unit`、`xentry.unit`、`xloc.unit`、`xcov.unit`、`xwaveform.*`、`xsva.*` | 原测试文件仍是业务断言所有者；catalog 只负责收集和门禁 |
| xdebug schema/example/runtime action 合同 | `xdebug.static`、`xdebug.action_runtime_catalog` | 原 schema、example、runtime catalog 检查改为 in-process pytest 或 command item，未减少 action 集合 |
| xdebug C++ unit | `xdebug.cpp_unit` | 16 个原二进制全部由 leaf runner 构建并执行；工作目录保持原 `xdebug/` 语义 |
| xdebug contract/session/MCP | `xdebug.contract`、`xdebug.session`、`xdebug.mcp_direct`、`xdebug.mcp_fake_lsf`、`xverif_mcp.process`、`xverif_mcp.action_smoke` | 原 pytest 文件、markers 和 handler/session 断言保留；数据库路径改由 fixture 注入 |
| waveform/design/combined 回归 | `xdebug.counter_statistics`、`xdebug.synthetic_existing`、`xdebug.stream`、`xdebug.active_semantics`、`xdebug.active_zero_evidence`、`xdebug.design_semantics` | 原真实 NPI 查询和计数断言保留；测试不再自行 clean/仿真 |
| active-trace | `xdebug.active_trace.{p0,composite,timing,phase4,phase5}` | 6 + 20 + 12 + 20 + 10，共 68 个历史 case 全部进入共享 builder/profile 和参数化 pytest |
| VIP / VCS 系统面 | `xdebug.apb_vip`、`xdebug.axi_vip`、`xdebug.xif_event`、`xsva.vcs`、`xloc.uvm` | 编译/仿真成为显式 fixture builder，原协议、事件、语义和日志断言由 nightly 消费 |
| 外部环境条件项 | `xdebug.realdata`、`xdebug.mcp_real_lsf`、`xverif_mcp.real_lsf_jobid` | 身份保留为 nightly optional；环境缺失只允许明确 SKIP，不允许 fake/backend fallback |

`testinfra/tests/test_completeness.py` 会失败于未被 catalog 或 leaf runner 所有的 `test_*.py`、重新出现的旧 gate shell、局部 pytest 配置、公共 Make `test/check/smoke` target，以及 active-trace case Makefile。它还核对 16 个 C++ test source 与 runner binary 清单完全相等，并要求每个 `testinfra/leaf` 脚本被 catalog 或 fixture registry 声明。

## 3. Fixture 迁移与缓存验证

已登记并强制重建验证以下 19 个 fixture：

- xdebug 基础数据库：active-driver、active-semantics、zero-evidence、interface-port-root、complex-wave、stream-v1、APB VIP、AXI VIP、design UART、design P3。
- active-trace：共享 runner，以及 p0、composite、timing、phase4、phase5 五组 case 数据库。
- 其它系统资产：xif-event、xsva VCS、xloc UVM。

最终证据：

1. `pytest --xverif-fixture-validation --xverif-all-fixtures -q` 在沙箱外从源强制重建，19/19 输出 `validated`。FSDB/daidir probe 会实际执行 `session.open` 和 `scope.roots`；JSON、UVM summary、VCS log 与 executable 资产执行对应的结构化语义检查。
2. 紧接着执行 `pytest --xverif-prepare all-generated -q`，19/19 输出 `cache hit`，总耗时约 1.4 秒；没有 VCS/simv 重跑，也没有重复 semantic probe。
3. 在此之前执行完整 `make clean all` 后，同一 prepare 也为 19/19 cache hit，证明源码 clean 不删除 fixture cache。
4. cache key 覆盖 fixture 源文件、公共 builder/profile、probe 脚本与参数、额外脚本输入和声明的工具环境；输出发布前检查类型、存在性、最小尺寸和 backend-aware semantic probe。

因此，普通 regression/nightly 的职责是验证 xverif 对数据库的查询行为，不再重复验证 RTL 仿真本身。

## 4. 最终门禁结果

| 门禁 | 执行位置 | 结果 | 说明 |
|---|---|---|---|
| `make clean all` | 沙箱外 | PASS | 全仓 clean 后重新构建 xdebug、xbit、xentry、xloc、xwaveform |
| `pytest --xverif-gate fast -q` | 沙箱内 | PASS，216 passed | 无外部 EDA 进程的 hermetic 快速门禁 |
| `XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate regression -n auto -q` | 沙箱外 | PASS，519 passed | 含 NPI、FSDB、MCP 进程与 C++ unit；required 全通过，environment 明确记录 host |
| `XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate nightly -n auto -q` | 沙箱外 | PASS，596 passed，2 skipped | 全部 VIP/active-trace/VCS 系统面通过；两个 SKIP 均为未启用的 optional real-LSF capability |
| `pytest --xverif-fixture-validation --xverif-all-fixtures -q` | 沙箱外 | PASS，19 validated | 强制重建全部生成型 fixture |
| fixture 二次 prepare | 沙箱外 | PASS，19 cache hit | 明确证明普通消费路径不重复仿真 |

每次 gate 在 `.xverif-test-results/` 下生成独立 run 目录，包含 `report.json`、`junit.xml`、`environment.json` 和 suite 日志；失败 run 不会被后续成功 run 改写。结果保留策略为成功最近 20 份、失败 30 天，并受 10 GiB 总量上限约束。

## 5. 迁移过程中发现并修复的问题

### 5.1 MCP backend 配置进程内污染

统一进程测试发现 `xverif_loop.config` 和 logging 的可变全局状态会让先运行的 backend 配置污染后续 xdebug/xcov MCP adapter。xdebug 与 xcov adapter 现在都在初始化时显式调用公共 MCP environment/logging 配置 helper，并有回归测试保护。该修复没有改变 action 语义，也没有增加 fallback。

### 5.2 xdist 资源合同未实际生效

首轮 `-n auto` 暴露 NPI suite 并发后 engine session transport 中断。根因有两层：只添加了 `xdist_group` marker，却没有启用 `--dist=loadgroup`；plugin hook 又晚于 xdist worker 的 nodeid 分组 hook。

修复后：

- 根配置固定使用 `--dist=loadgroup`。
- 公共 resource helper 从 `npi` capability 对称派生 `verdi_npi` token，避免同语义 suite 漏写显式 token。
- collection hook 使用 `tryfirst=True`，确保 xdist 生成调度 nodeid 前已看到 marker。
- 四个曾冲突的 suite 在 `-n auto` 联合 focused run 中 5/5 通过，随后完整 regression 512/512 通过。

这不是降低并发或串行重跑 fallback；非 NPI suite 仍由 xdist 并行，受限资源按 catalog capability 串行所有权执行。

### 5.3 外部 command item 的失败和 SKIP 报告

- `ExternalSuiteFailure` 原先是 frozen dataclass，pytest/contextlib 附加 traceback 时会产生 `FrozenInstanceError`，遮蔽原始 command 错误；现允许标准异常 traceback 写入。
- custom item 的 `reportinfo()` 原返回空行号，optional real-LSF 在 setup-skip 时触发 pytest internal error；现返回合法 catalog 行号。定向 `-n auto` 验证得到 1 个正常 SKIP，完整 nightly 也正确记录 2 个 optional SKIP。

### 5.4 C++ unit 工作目录漂移

leaf runner 最初从仓库根执行 C++ 二进制，改变了历史相对 schema 路径语义，导致 action registry 断言失败。runner 现仍从统一入口启动，但二进制 cwd 恢复为 `xdebug/`，16 个二进制完整执行通过。

### 5.5 历史测试细节校正

- active-trace timing 共享 helper 显式保留历史 `--stop-on-temporal` 边界语义。
- phase5 以当前可执行 C++ helper 的真实断言为准；旧说明文档中的个别时间示例与当前实现不一致，未据旧文字降低或改写现行断言。
- xsva VCS fixture 修正了旧脚本的 include/UCLI 构建问题；xif-event staging 修正绝对运行路径。二者保持原要验证的语义，不引入替代 backend。

### 5.6 独立复审后补齐的范围与报告合同

- 删除 xif-event Makefile 残留的 `check` 测试入口，并让完整性守卫禁止重新引入 `check`。
- 恢复 xentry 兼容 CLI 的 `explain --config ... --json` 与 `validate --config ... --input ... --json` 两项 smoke 断言；JSON envelope 测试不再被当成兼容参数入口的替代品。
- JSON report 现在记录 setup 阶段 optional SKIP；最终 nightly 的 terminal、JUnit 和 `report.json` 都是 596 passed、2 skipped。
- environment snapshot 不再根据继承的 Codex 环境变量猜测执行位置；沙箱外 gate 显式设置并校验 `XVERIF_TEST_EXECUTION_ENV=host`。
- fixture 从“同 fingerprint 原地删除再替换”改为不可变 generation 与原子 current 指针；失败发布不会删除上一个有效资产，并且普通 resolve 不执行 builder/probe。

### 5.7 xdist 生命周期竞争修复

完整门禁进一步发现两类只有并行时出现的 SIGTERM：

- MCP E2E helper 原来每次 tool call 新建 AnyIO event loop，FastMCP lifespan 的延迟清理可能关闭下一次调用仍需复用的 session；现在同一 server 使用持久 blocking portal，符合真实 MCP client 生命周期。
- xdebug pytest session 结束时曾按全局 PID 差集清理 engine；某个 xdist worker 提前结束会误杀其它 worker 的 live session。现在每个 worker 注入唯一 owner token，只清理继承自身 token 的 engine，同时保留按 isolated HOME 的逐测试精确清理。

修复后 focused contract 65/65、direct MCP 4/4、完整 regression 519/519、nightly 596 + 2 optional skip 均通过。

## 6. 约束核对

- 无 fallback：通过。没有自动切换 backend、transport、数据源、fake LSF 或低层级测试。
- 同语义一致：通过。gate、capability preflight、NPI resource group、fixture cache、timeout、结果报告均由公共 helper 实现。
- 普通测试不重复仿真：通过。clean 后及强制重建后的两次 19/19 cache-hit 均有实测。
- 测试范围保持：通过。41 suite 全部有 catalog 身份；68 个 active-trace case 和全部 C++/MCP/VIP/组件测试保留。
- CI：按用户决定不新增。
- Git：实施分批中文提交；最终验证提交将在独立复审修正后创建并推送 `origin/master`。

## 7. 已知环境状态

本机没有按 real-LSF 合同同时满足 `XDEBUG_ENABLE_REAL_LSF=1` 与 `bsub/bjobs/bkill` 可用条件，因此：

- `xdebug.mcp_real_lsf`：optional SKIP。
- `xverif_mcp.real_lsf_jobid`：optional SKIP。

`xdebug.realdata` 在本机可用并通过；没有 required suite 因环境缺失而 SKIP。

## 8. 独立复审

独立 reviewer 首轮结论为“存在阻断项，暂不应提交/推送”，主 agent 核对后确认全部意见成立：

1. 阻断：xif-event `check` target 残留——已删除并扩充 guard。
2. 阻断：xentry compat explain/validate 漏迁——已恢复两项原 CLI 断言。
3. 阻断：fixture 缺少 semantic probe，重建同 fingerprint 存在非原子空窗——已增加 registry probes、实际 xdebug database query、不可变 generation 和原子 current 指针。
4. 高：JSON 漏记 setup skip——已修复并用定向 optional suite 与最终 nightly 验证三种报告计数一致。
5. 高：host 测试被 environment.json 误标为 sandbox——已改为显式、校验后的执行环境合同，最终 regression/nightly 均记录 host。
6. 中：完整性守卫范围被报告夸大——已增加 C++ source/binary parity、leaf declaration 和 `check` target 守卫，并相应精确描述保护范围。

复审还确认 41 suite、7/28/41 gate 选择、68 active-trace case、16 C++ unit、no fallback、no CI 均与仓库证据一致。所有有效 finding 已在最终 clean 与全仓门禁前修复，不保留已知阻断项。

修复完成后又由第二个独立 reviewer 做 closure review。它逐项检查上述 6 个 finding、immutable generation/current 切换、正常 cache-hit 路径、xdist loadgroup、MCP persistent portal 和 worker owner-token cleanup，并额外执行 Python compile、`testinfra.unit` focused 与 `git diff --check`。结论为全部关闭，未发现新的阻断或高优先级问题，可以提交和推送。
