# xverif 全仓测试体系统一迁移计划

- 生成时间：2026-07-10 23:36:25（Asia/Shanghai）
- 状态：已获用户授权并完成实施；最终验收与独立复审见 `XVERIF_TEST_ARCHITECTURE_MIGRATION_VERIFICATION_2026-07-11_02-16-19.md`
- 目标：在本次任务内把全仓分散测试全部迁移到 catalog 驱动的 pytest plugin，统一 fixture、选择、执行、并行、错误语义和报告
- 关键约束：不做 fallback；普通测试不隐式仿真；所有 NPI/VCS/VIP/真实 license/进程通信测试在沙箱外执行
- CI：不在本次范围内；只交付 provider-neutral 的仓库测试合同和机器可消费报告

## 1. 当前问题与证据

当前测试不是单纯“目录多”，而是存在多套事实源和执行合同：

1. 顶层 `Makefile` 的 `test` 与 `full-test` 分别手工组合组件和 shell regression，二者不是严格包含关系。
2. `xdebug/Makefile` 同时维护 `test-fast`、`test-regression`、`test-nightly`、大量 `pytest-*`、`mcp-*` 和静态检查 target，选择集合与 pytest markers 重复。
3. `regression/run_xdebug_regression.sh` 与 `regression/run_full_regression.sh` 再次拥有 fixture 条件、SKIP、suite 选择、日志和汇总逻辑。
4. pytest markers 混合测试层级、测试意图、能力域、环境依赖、成本和 gate，例如 `contract`、`waveform`、`vip`、`slow`、`nightly` 同处一层。
5. fixture 生命周期不一致：AXI/APB VIP 已能在资源存在时复用，`active_semantics`、`active_zero_evidence`、stream 等仍执行 `make clean fixture/run`；部分 full regression 无条件重建 active-driver 和 UART daidir。
6. fixture 有的只检查路径存在，无法判断 RTL、TB、filelist、生成脚本、工具 ABI 或 schema 变化，存在陈旧数据库假通过风险。
7. suite 在 `xdebug/tests`、`xverif_mcp/tests`、各组件 `tests/`、`regression/` 和大量 fixture Makefile 中分散；active-trace 单独包含大量 case Makefile。
8. 当前顶层常规门禁没有统一纳入 `xsva`，全仓“通过”的含义不完整。
9. 环境缺失有时由 shell `exit 0`、pytest skip 或调用者条件分支处理，required 覆盖可能退化为绿色 SKIP。
10. full regression 主要把日志放在 `<repo>/tmp`；不同 runner 对 timeout、process cleanup、stderr/stdout 和 artifact 路径的处理不一致。

## 2. 已确认的架构原则

1. 顶层 YAML catalog 是 suite 身份、正交属性、环境和 gate 归属的唯一事实源。
2. catalog 记录稳定 suite，不逐 pytest node/参数/case 建总表；高成本且合同不同的子集可拆分。
3. pytest plugin 是唯一公开测试入口；迁移完成后删除全部 Makefile 测试 target，不保留兼容 fallback。
4. 测试文件和 fixture 源码可以继续靠近组件存放；统一测试体系不要求物理搬到单一目录。
5. 测试层级为 `static/unit/component/integration/system`；`contract` 是测试意图，不是层级。
6. 能力域、环境依赖、成本、并行资源与测试层级正交。
7. FSDB、daidir、VDB 是数据库 Fixture 输入资产；普通测试消费资产，不把仿真生成当成测试本体。
8. fixture 使用内容指纹缓存到仓库本地 `.xverif-test-cache/`；测试结果写入独立 `.xverif-test-results/`。
9. fixture prepare 与 test execution 严格分离；cache miss 不自动仿真、不自动 SKIP。
10. `make clean` 只清源码构建；fixture/results 分别由 pytest plugin 的显式操作清理。
11. 失败不自动 retry；显式 rerun 生成独立诊断报告，不能改写原 gate 结论。
12. 正式 regression/nightly 不按 Git diff 裁剪；changed-only 只用于本地和快速预检。
13. 不新增 CI provider 配置。

详细决策见 `CONTEXT.md` 与 `docs/adr/0001` 至 `0028`。

## 3. 目标目录与所有权

```text
/
├── pyproject.toml                    # 唯一 pytest 配置与 testinfra 开发依赖
├── testinfra/
│   ├── xverif_test/
│   │   ├── plugin.py                 # pytest hooks/options/collection
│   │   ├── catalog.py                # catalog loader + semantic validation
│   │   ├── gates.py                  # gate query 与选择理由
│   │   ├── items.py                  # external suite pytest items
│   │   ├── runners/                  # pytest/python/cpp/command/make/vcs/mcp adapters
│   │   ├── fixtures/                 # fingerprint/cache/prepare/publish/prune
│   │   ├── environment.py            # capability preflight
│   │   ├── resources.py              # xdist token/lock
│   │   ├── reports.py                # terminal/JUnit/JSON/artifact
│   │   ├── impact.py                 # conservative changed-only
│   │   └── errors.py                 # FAIL/ERROR/SKIP/error_layer
│   ├── schemas/
│   │   ├── catalog.v1.schema.json
│   │   ├── fixture-manifest.v1.schema.json
│   │   ├── environment-snapshot.v1.schema.json
│   │   └── execution-report.v1.schema.json
│   ├── catalog.v1.yaml               # 唯一 suite/gate catalog
│   └── tests/                         # testinfra 自身 fast tests
├── .xverif-test-cache/               # gitignored 数据库 Fixture
├── .xverif-test-results/             # gitignored 运行报告
└── <component>/tests/                 # 组件继续拥有业务断言和局部 fixture manifest
```

根级 `pyproject.toml` 定义 testinfra package 与 pytest plugin entry point，开发环境以 editable install 加载；不同时保留手工 `PYTHONPATH`、root conftest 偷加载和安装包多套路径。

## 4. Catalog v1 合同

### 4.1 Suite 记录

每条 suite 至少包含：

```yaml
id: xdebug.waveform.stream
owner: xdebug
level: integration
intent: [contract, semantics]
domains: [waveform, stream]
runner:
  kind: pytest
  path: xdebug/tests/synthetic/test_stream_v1_real_waveform.py
fixtures: [xdebug.stream_v1]
capabilities: [npi, fsdb]
cost:
  class: medium
  estimate_sec: 20
resources:
  cpu: 1
  memory_mb: 1024
  tokens: [verdi_npi]
parallel: read_only_fixture
timeouts:
  prepare_sec: 600
  execute_sec: 120
  cleanup_sec: 20
impact:
  owns: [xdebug/src/waveform/stream/**, xdebug/tests/synthetic/test_stream_v1_real_waveform.py]
  depends_on: [xdebug.core, xdebug.fixture.stream_v1]
```

语义规则：

- `id` 全仓唯一、稳定、与路径解耦。
- `level` 单值；`intent/domains/capabilities` 多值。
- runner command 不允许 shell 拼接；使用 argv、cwd、去敏 env allowlist。
- suite 不永久声明 optional；required/optional 由 gate policy 决定。
- 未声明资源 claim 的 external suite 默认不能并行，不假设无限资源。
- suite 引用的 fixture、依赖和路径必须存在；未知字段、重复 ID、循环依赖直接 schema/semantic ERROR。

### 4.2 Gate 查询

- `fast`
  - 选择 `static/unit/component` 中声明 `hermetic=true` 且不启动 child process/NPI/VCS/VIP/license 的 suite。
  - testinfra 自身、纯 Python unit、迁移为进程内调用的 schema/static 检查进入该 gate；需要启动 C++ test binary 的 suite 进入 regression。
- `regression`
  - 选择全部 required deterministic suite。
  - 可读取有效缓存的 FSDB/daidir；需要 NPI、direct MCP、fake LSF 时集中 preflight。
  - 不进行 fixture prepare，不因 cache miss 自动仿真。
- `nightly`
  - 包含完整 regression，并增加 slow、active-trace、AXI/APB VIP。
  - 仓库可生成的 VIP Fixture 和对应查询 required；外部项目 realdata、real LSF optional。
  - 仍只消费缓存，不自动重建。
- `fixture-validation`
  - 不是产品测试 gate。
  - 按 fingerprint input 变化重建受影响 fixture，并提供周期性全量模式。
  - staging 生成、验证后原子 publish；失败不覆盖已发布资产。

### 4.3 公开 pytest 命令

```bash
pytest --xverif-plan --xverif-gate fast
pytest --xverif-gate fast
pytest --xverif-gate regression -n auto
pytest --xverif-gate nightly -n auto
pytest --xverif-prepare xdebug.active_driver
pytest --xverif-prepare all-generated
pytest --xverif-fixture-validation --xverif-changed <base>
pytest --xverif-fixture-validation --xverif-all-fixtures
pytest --xverif-changed <base> --xverif-gate fast
pytest --rerun-failed .xverif-test-results/<run>/report.json
pytest --xverif-fixture-clean
pytest --xverif-results-clean
```

裸 `pytest`、未知 gate、冲突 operation 或未知 fixture 在 collection 前 usage ERROR；不得隐式选择 fast/regression。

## 5. 数据库 Fixture 体系

### 5.1 Fixture manifest

每个可生成 fixture 声明：

- 稳定 fixture ID 与 schema version。
- RTL/TB/filelist/生成脚本输入。
- 关键 compile/sim/FSDB/KDB 选项。
- VCS/Verdi/PLI compatibility identity；完整版本写 provenance。
- 输出资源清单：FSDB、daidir、VDB、simulation log、辅助 manifest。
- 完整性检查：文件非空、目录关键文件、FSDB 可读、daidir 可 open。
- semantic probe：固定 top/signal/transaction/coverage anchor，避免“文件存在但内容错误”。
- consumer suite 列表与资源只读/独占属性。

### 5.2 指纹与布局

```text
.xverif-test-cache/
└── fixtures/
    └── <fixture-id>/
        ├── current.json               # 原子指向已发布 fingerprint
        ├── <fingerprint>/
        │   ├── manifest.json
        │   ├── provenance.json
        │   └── resources/...
        └── .staging/<run-id>/...
```

- fingerprint 基于文件内容与规范化生成合同，不使用 mtime。
- 同一 fingerprint prepare 使用跨进程 lock 去重。
- 已发布 fingerprint 不可变；重建写新目录并原子更新 current。
- 默认不自动淘汰 fixture，避免测试中途消失；提供显式 prune/clean。
- `make clean` 不触碰 cache；最终删除 Makefile 测试 target 后，源码 clean 仍由 build Makefile负责。

### 5.3 迁移重点

- AXI/APB VIP：复用现有 manifest 内容，但统一为版本化 fixture schema 和缓存路径；移除 pytest 内 `make clean run`。
- active-driver/active-semantics/active-zero-evidence/interface-port-root/stream/ai-complex-wave/xif-event：移除测试内隐式 prepare。
- UART/P3 design：由 fixture builder 统一生成 daidir，不在 shell semantics runner 中临时调用 VCS。
- active-trace：用公共 builder profile 加 case descriptor 替代大量重复 Makefile；按 p0/composite/timing/phase4/phase5 建 suite，case 仍由 suite 内发现。
- 外部 realdata：不复制到 cache；使用 external fixture manifest 记录来源 identity、路径和 semantic probe，nightly 中 optional。
- xcov VDB：纳入相同 fixture 抽象，backend capability 与 FSDB/daidir 区分，不写专用旁路。

## 6. 统一执行与错误合同

### 6.1 Collection/plan

- 读取并 schema 校验 catalog。
- 创建稳定 suite item/node ID。
- 解析 gate/changed-only 查询并记录每个 suite 的 include/exclude 理由。
- `--collect-only`/`--xverif-plan` 不运行 environment probe、不启动 child process、不触碰 license、不 prepare fixture。

### 6.2 Preflight

- 一次性探测具名 capability，生成去敏 environment snapshot。
- probe 只读、有 timeout；不提交 LSF job、不生成数据库、不长时间持有 license。
- required 缺失：相关 suite 在启动前 ERROR。
- optional 缺失：明确 SKIP 并进入三种报告。
- 不切换 fake backend、其它 transport、其它数据源或较低测试层级。

### 6.3 Execution

- Python suite 使用正常 pytest collection。
- C++、shell、command、MCP、VCS leaf runner 使用自定义 pytest item。
- 外部命令使用 argv/cwd/env allowlist，禁止 shell 隐式展开。
- suite 分阶段 timeout：prepare/execute/cleanup。
- timeout 或 Ctrl-C 终止完整 process group/owned LSF job，报告 cleanup/unresolved。
- pytest-xdist 管 worker；plugin 用资源 token/lock 限制 VCS、Verdi、VIP、端口和 cache 写者。

### 6.4 结果语义

- FAIL：产品或合同断言不成立。
- ERROR/fixture：required fixture 缺失、失效或不可读。
- ERROR/environment：required capability/license/tool/transport 缺失。
- ERROR/runner：leaf runner 启动或协议错误。
- ERROR/timeout：阶段超时或清理未确认。
- SKIP：当前 gate 明确 optional 且 capability/fixture 不可用。
- DESELECT：未被 gate/changed-only 查询选中。
- 不自动 retry；diagnostic rerun 保留父 report 引用但不修改原结果。

### 6.5 报告保留默认值

- 自动保留最近 20 个成功 run；FAIL/ERROR run 保留 30 天。
- results 默认容量上限 10 GiB，按“最旧成功、过期失败”顺序清理；活动 run、被 rerun 引用的父报告和用户显式 pin 的 run 不回收。
- 达到容量上限但没有可安全回收对象时，新 run 在执行前 ERROR，不删除 fixture、不覆盖旧报告、不改写到 `<repo>/tmp` fallback。
- fixture cache 默认不自动回收；仅显式 fixture prune/clean 改变已发布资产。

## 7. 全仓 Suite 迁移台账

以下是 catalog 的最低 suite 集合；实施阶段允许在不改变边界的前提下细分，但不得合并掉不同环境/成本合同。

| Suite ID 族 | 当前来源 | 目标 gate/属性 | 迁移动作 |
| --- | --- | --- | --- |
| `testinfra.*` | 新增 | fast/static+unit | catalog/schema/gate/item/cache/report/resource 自测 |
| `xbit.unit` | `xbit/tests/test_xbit.py` | fast/unit | 直接 root pytest 收集 |
| `xbit.cli` | `xbit/Makefile` smoke | regression/component | 将 CLI smoke 迁成 pytest/command item |
| `xentry.unit` / `xentry.cli` | `xentry/tests` + Make smoke | fast/regression | 分离纯逻辑与 child CLI |
| `xloc.unit` / `xloc.vim` | `xloc/tests`、vim smoke | fast/regression | Vim 作为 external item，保留独立日志 |
| `xcov.unit_contract` | `xcov/tests/test_xcov.py` | fast | 纳入 root config |
| `xwaveform.unit` / `xwaveform.cli` | unittest + Make smoke | fast/regression | 删除 Make test target |
| `xsva.parser` / `lowering` / `semantics` / `golden` / `cli` | `xsva/tests` | fast/regression | 统一 root collection 与 golden artifacts |
| `xsva.vcs` | `xsva/tests/vcs` | nightly/system | 生成 fixture 与断言执行分离 |
| `xverif_mcp.import_contract` | import/adapter tests | fast/component | 无外部进程集合 |
| `xverif_mcp.session_unit` | capability/error/backend wiring | fast/component | 统一 pytest config |
| `xverif_mcp.direct` | loop/UDS/SDK/direct output | regression/integration | external process + timeout/cleanup |
| `xverif_mcp.fake_lsf` | fake LSF tests | regression/integration | 独立 capability，不冒充 real LSF |
| `xverif_mcp.real_lsf` | optional marker tests | nightly/system optional | real LSF 缺失显式 SKIP |
| `xdebug.static` | schema/example/consolidation/audit | fast/static+contract | Python item，明确不启动 session |
| `xdebug.cpp_unit` | `xdebug/tests/unit/*.cpp` | regression/unit | 公共 C++ build/run adapter；因需 child process 不进入 fast；删除 Make unit-test 编排 |
| `xdebug.cli_contract` | contract pytest | fast/regression | 纯 schema/CLI child/runtime 按边界拆 suite |
| `xdebug.runtime_contract` | unified/action runtime contract | regression | 缓存 fixture + NPI，沙箱外 |
| `xdebug.waveform.core` | complex wave/counter/existing | regression | 移除 runner 内 build/skip，统一 fixture 引用 |
| `xdebug.stream` | stream real waveform | regression | 缓存 stream fixture |
| `xdebug.combined.active` | active semantics/zero/driver | regression/nightly | 多个稳定 suite，共享只读 fixture |
| `xdebug.design` | `run_semantics.sh` | regression | shell 降为 leaf 或改 pytest，移除临时 VCS build |
| `xdebug.session` | session pytest | regression | process/UDS/NPI capability 明确化 |
| `xdebug.mcp_e2e` | xdebug tests/mcp | regression | 与 xverif_mcp unit 分开，完整系统链路 |
| `xdebug.apb_vip` | APB VIP pytest | nightly required | 消费缓存；prepare 独立 |
| `xdebug.axi_vip` | AXI VIP pytest | nightly required | 消费缓存；prepare 独立 |
| `xdebug.active_trace.p0` | p0 case Makefiles | nightly | 公共 builder profile + suite case discovery |
| `xdebug.active_trace.composite` | composite case Makefiles | nightly | 同上 |
| `xdebug.active_trace.timing` | timing case Makefiles | nightly | 同上 |
| `xdebug.active_trace.phase4` / `phase5` | phase Makefiles | nightly | 同上 |
| `xdebug.realdata` | realdata manifests/system wave/AXI external | nightly optional | external fixture identity + semantic probe |
| `repo.catalog_completeness` | 新增 | fast/static | 扫描所有 test/runner/fixture，防止未登记 suite/旧入口回流 |

## 8. 分批实施计划

### 阶段 0：冻结基线与完整台账

- 记录当前所有 test 文件、Make target、pytest marker、shell runner、fixture generator、环境条件和实际 gate 覆盖。
- 生成 machine-readable legacy inventory，仅用于迁移 parity，不成为新事实源。
- 为每个旧入口标注 `migrate/delete/leaf-runner`。
- 建立“未登记测试源”静态扫描，防止迁移过程中遗漏 xsva、active-trace case。

退出条件：每个现存测试或 fixture builder 都有目标 suite/fixture ID 与迁移批次。

### 阶段 1：testinfra 骨架、schema 与无副作用 plan

- 建 root package、唯一 pytest config、plugin 加载、catalog/schema。
- 实现显式 options、裸 pytest usage error、catalog semantic validation。
- 实现 gate query、stable node ID、collect-only/plan 与 JSON plan。
- 先登记但不执行全部 suite，验证 inventory/count/ownership parity。

退出条件：`--xverif-plan` 可以展示全仓 suite、选择理由和缺失声明，且零外部副作用。

### 阶段 2：fast gate 与纯测试迁移

- 迁移 testinfra 自测、xbit/xentry/xloc/xcov/xwaveform/xsva 纯 unit/static。
- 迁移 xdebug schema/static；完成 C++ unit catalog/item 迁移，但把执行归入 regression。
- 迁移 xverif_mcp import/capability/error 纯测试。
- 统一 root pytest config，删除已迁移组件的测试 Make target/局部 pytest.ini。

退出条件：fast gate 覆盖所有 hermetic 测试；沙箱内可全通过；旧 fast 入口与新 gate 断言 parity 后删除。

### 阶段 3：external item、报告、timeout 与资源调度

- 实现 command/C++/shell/MCP custom item。
- 实现 process group ownership、分阶段 timeout、Ctrl-C/worker crash cleanup。
- 引入 pytest-xdist 和资源 token/lock。
- 实现 terminal/JUnit/JSON 与 suite artifact 目录。
- 迁移 CLI/Vim/SDK-free 等无需数据库但需 child process 的 suite。

退出条件：external item 的 PASS/FAIL/ERROR/timeout/interrupt 均有确定性自测，日志可定位。

### 阶段 4：Fixture cache 与 builder 全量迁移

- 实现 fingerprint、tool identity、manifest、staging、atomic publish、lock、integrity/semantic probes。
- 迁移 active-driver、active-semantics、active-zero、interface-root、stream、complex-wave、UART/P3、xif-event。
- 用公共 profile/descriptor 替代 active-trace 重复 Makefile。
- 迁移 AXI/APB VIP builder，但测试执行仍不自动 prepare。
- 实现 fixture-clean/prune/results-clean；确认源码 clean 保留 cache。

退出条件：连续两次 prepare，第二次零仿真 cache hit；任一 fingerprint input 改变只重建受影响 fixture；失败 staging 不污染 current。

### 阶段 5：regression gate 全量迁移

- 迁移 xdebug runtime/waveform/design/combined/session/MCP suite。
- 迁移 xverif_mcp direct/fake-LSF。
- 建 centralized preflight 与 environment snapshot。
- 删除 `regression/run_xdebug_regression.sh` 和 `run_full_regression.sh` 的选择/汇总/prepare 职责；有价值断言迁入 pytest suite。
- 删除已替代的 xdebug `test-*`、`pytest-*`、`mcp-*` Make targets。

退出条件：有效 fixture 条件下 regression 全通过且不调用 VCS/simv；cache miss 明确 ERROR 并给 prepare 命令。

### 阶段 6：nightly、VIP、active-trace 与 optional 外部能力

- 迁移 APB/AXI VIP 消费测试、active-trace 全 case、xsva VCS。
- 迁移 external realdata 与 real LSF optional suite。
- 验证 required/optional preflight、SKIP 统计和无 fallback。
- 运行 fixture-validation 的受影响模式和全量模式。

退出条件：nightly required 全通过；外部 realdata/real LSF 缺失仅形成可解释 optional SKIP；普通 nightly 不重做仿真。

### 阶段 7：changed-only、文档和旧体系删除

- 实现保守 impact mapping 与 unknown/global 扩大规则。
- 删除全部 Makefile 测试 target、局部公共 pytest.ini、重复 marker/gate 选择、旧汇总脚本与隐式 SKIP。
- 更新根 README、各组件 README、`doc/agents/xdebug/README.md`、AGENTS.md、CLI/MCP skills。
- 加静态 guard：禁止新增 Makefile test target、独立 gate shell、未 catalog suite、suite 内隐式 fixture build。

退出条件：repo 只有 pytest plugin 公开测试入口，文档/skill 无旧命令，静态 guard 全通过。

### 阶段 8：最终 clean build 与全仓验收

- 源码 `make clean all`，确认 fixture cache 未删除。
- 运行 fast、regression、nightly 和 fixture-validation required 路径。
- 第二次 regression/nightly 验证 cache hit、无 VCS/simv 调用。
- 运行 catalog completeness、JSON/JUnit schema、xdist 并发、timeout/orphan audit。
- 独立 agent 对 suite 台账、删除清单、报告和门禁语义做最终只读复审。

退出条件：第 11 节全部 acceptance criteria 满足，工作树只含本任务文件；是否 commit/push 由用户实施指令决定。

## 9. 必须删除或降级的旧职责

- 顶层 `make test`、`make full-test`、`xcov-test`。
- 各组件 `test/unit-test/smoke/vim-test` 测试 target。
- xdebug `test-fast/test-contract/test-synthetic/test-vip/test-regression/test-nightly`。
- xdebug `pytest-*` 与 `mcp-test*`/`mcp-session-test`/`mcp-sdk-test` 公开 target。
- regression shell 的 gate 选择、fixture 检测/生成、SKIP 与 summary。
- 测试函数中的 `make clean run/fixture`。
- suite 自己读取环境后 `exit 0`/skip required 覆盖。
- 多份 pytest.ini 中重复 markers/addopts/testpaths。
- active-trace case 重复 fixture Makefile；用公共 builder profile 和描述文件替代。

允许保留的 leaf runner 必须满足：单一 suite、无 gate 选择、无隐式 prepare、无 fallback、结构化退出、stdout/stderr 由 plugin 捕获。

## 10. 测试与验证规划

### 10.1 testinfra fast tests

- catalog JSON schema：合法/未知字段/重复 ID/非法 enum/悬空引用/循环依赖。
- gate query：正交属性、required/optional、unknown/global impact 扩大。
- CLI options：裸 pytest、冲突 operation、unknown gate/fixture、plan 无副作用。
- item mapping：稳定 node ID、命令 argv/cwd/env 去敏、result mapping。
- report：JSON schema、JUnit 属性、artifact 相对路径、父子 rerun 关系。
- timeout：prepare/execute/cleanup、process group kill、worker crash token 回收。
- resource scheduler：token 容量、exclusive lock、无资源时明确等待/ERROR，不换 backend。

### 10.2 Fixture tests

- 同输入同指纹；内容变化触发；mtime 变化不触发。
- compatible tool identity 命中；ABI/主次版本不匹配失效；未知版本 ERROR。
- staging 失败不覆盖 current；原子 publish；并发同指纹只构建一次。
- FSDB/daidir/VDB 完整性和 semantic probe 失败不发布。
- `make clean all` 保留 fixture；pytest fixture-clean 明确删除。
- cache miss 的 regression/nightly 不调用 VCS，直接 ERROR 并提供 prepare 命令。

### 10.3 Parity 验证

- 每批迁移前后对比 suite inventory、实际 assertions、fixture 与结果，不只比较测试数量。
- 旧入口只在其区域切换前用于一次 parity；切换后删除，不作为 fallback。
- 对原来由 shell 内嵌的 Python assertions 建独立 pytest 断言并审阅字段语义。
- xdebug action 测试不得调用仓库 70-action replay runner。

### 10.4 沙箱边界

- 沙箱内：catalog/schema、testinfra unit、纯 Python/C++ unit、plan/collect-only。
- 沙箱外：任何 NPI/FSDB/daidir engine、MCP stdio/UDS/process、VCS/simv、VIP、license、realdata、real/fake LSF 系统动作。
- 沙箱内失败不能判产品回归；外部执行结果必须在 JSON environment snapshot 中标明执行环境类别。

## 11. 最终验收标准

- [x] catalog 覆盖所有现有 Python、C++、shell、Make/VCS、VIP、MCP、realdata、active-trace suite。
- [x] 顶层 YAML catalog 与 schema 是唯一 suite/gate 事实源。
- [x] 裸 pytest usage ERROR；所有当前文档使用显式 `--xverif-*`。
- [x] fast/regression/nightly/fixture-validation 选择与 required/optional 合同稳定。
- [x] 普通 regression/nightly 在 cache hit 时不运行 VCS/simv。
- [x] cache miss 不自动 prepare、不 SKIP required、不 fallback。
- [x] fixture 指纹、完整性、semantic probe 和 atomic publish 全覆盖。
- [x] pytest-xdist 并行不破坏 license/token/cache/process cleanup。
- [x] FAIL/ERROR/SKIP/DESELECT/error_layer 可从终端、JUnit、JSON 一致解释。
- [x] 无自动 retry；rerun 不改写原 gate。
- [x] `.xverif-test-results` 保留完整可移动 run evidence。
- [x] 所有 Makefile 测试 target、重复 gate shell、局部公共 pytest 配置已删除。
- [x] `xsva` 纳入全仓 gate。
- [x] README、xdebug agent 文档、AGENTS.md、skills 与新入口一致。
- [x] clean build 后 fast、regression、nightly required 全通过。
- [x] 外部 realdata/real LSF 缺失仅形成明确 optional SKIP，无 fake fallback。
- [x] 第二次全量运行证明 fixture cache 命中且无重复仿真。
- [x] 独立 reviewer 确认无 suite 丢失、无旧编排残留、无结果语义夸大。

## 12. Commit 规划

提交均使用详细中文 subject/body，显式写明动机、范围、验证和未运行环境项：

1. `计划：记录全仓测试体系统一迁移决策`
   - CONTEXT、ADR、完整计划。
2. `测试基础设施：建立 catalog schema 与 pytest 统一入口`
   - testinfra package、root config、plan/collect-only、usage error。
3. `测试：迁移全仓 fast suite 并统一静态合同`
   - 纯组件测试、xdebug static/C++ unit、MCP import/unit。
4. `测试基础设施：统一外部 suite 执行并增加结构化报告`
   - custom items、xdist resources、timeout、JSON/JUnit/artifacts。
5. `测试基础设施：建立内容寻址数据库 Fixture 缓存`
   - fingerprint、manifest、builder、atomic publish、clean/prune。
6. `测试：迁移 xdebug regression 与 MCP 生命周期门禁`
   - waveform/design/combined/session/direct/fake-LSF。
7. `测试：迁移 VIP active-trace 与外部可选门禁`
   - AXI/APB、active-trace、xsva VCS、realdata/real LSF。
8. `重构：删除旧 Make 测试入口与重复回归编排`
   - Make targets、shell selection/summary、局部 pytest config、旧 marker。
9. `文档：统一 pytest 测试入口与 Fixture 工作流`
   - README、agent docs、skills、AGENTS.md。
10. `测试：完成 clean build 与全仓新门禁验收`
    - 最终报告、cache-hit 证据、独立复审修正。

每个提交前执行 `git status --short` 并显式 `git add` 文件；不得把 cache/results/EDA 产物加入版本库。

## 13. 非目标与停止条件

非目标：

- 不新增 GitHub Actions、GitLab CI、Jenkins 或其它 provider 配置。
- 不把组件测试物理搬到统一 tests 目录。
- 不测试 RTL/VIP 功能正确性；仿真只准备 xverif 查询输入资产。
- 不新增 backend/transport/data fallback。
- 不借本任务修改产品 action 语义；若迁移揭示产品 bug，单独记录并按用户确认处理。

必须停止并与用户重新对齐的情况：

- 发现某旧测试无法映射到稳定 suite，且删除会损失独立产品语义。
- fixture semantic probe 无法证明旧缓存与新生成资产等价。
- pytest-xdist 无法在不改 pytest 核心的情况下满足 license/job 资源所有权。
- 必须保留某个 Make test target 才能完成迁移，与 pytest-only 决策冲突。
- regression/nightly parity 需要降低断言、把 required 改 optional 或引入 fallback。

## 14. 实施授权与完成状态

用户已明确要求以本计划为目标进入 goal 模式，完成全量迁移、保持测试内容和范围一致，并在最终门禁通过后推送远端。实施按第 12 节分批提交；最终验证报告记录 clean build、三层 gate、19 个 fixture 的强制重建与 cache-hit 复验，以及独立 reviewer 的结论。
