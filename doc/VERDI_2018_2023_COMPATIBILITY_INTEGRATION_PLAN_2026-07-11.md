# xverif Verdi 2018 / 2023 双版本兼容整合计划

> 日期：2026-07-11
> 状态：讨论稿，尚未开始兼容代码实施
> 基线仓库：`OD-Nature/xverif`（fork 自 `BLANK2077/xverif`）
> 上游同步策略：长期 merge，不使用 rebase 重写兼容提交

## 1. 背景与目标

原作者持续维护的 xverif 当前以 Synopsys Verdi **V-2023.12-SP2** 为主要开发和测试环境。本项目需要在持续吸收原作者更新的同时，支持现场使用的 Verdi **O-2018.09-SP2**。

`xverif_2018` 是从旧版 xverif 派生的 2018 适配工程。它已经验证了部分关键兼容路径，但没有持续跟进上游后续的 unified engine、runtime schema validation、action contract、MCP session 和公共组件重构。因此，本项目不把两套源码直接拼接，也不长期维护两个完整 engine，而是：

> 以当前上游架构为唯一产品主线，将 `xverif_2018` 中已经验证的 2018 专用能力重新实现为集中、可测试、可替换的兼容层。

最终交付应满足：

1. 同一个仓库、同一套 CLI、MCP、JSON schema 和 XOUT 合同同时支持 Verdi 2023 与 2018。
2. 原作者更新可以定期 merge，2018 兼容改动尽量不侵入上游核心业务代码。
3. 版本或 backend 选择明确、可诊断，不在失败后静默 fallback。
4. 两个版本的差异限制在构建 profile、capability、NPI adapter/provider 和真实环境测试中。
5. 所有 coverage 结果必须来自 Verdi NPI/VDB 事实，不解析 URG HTML，不构造假字段或假分母。

## 2. 当前事实基线

### 2.1 Git 关系

当前本地仓库配置为：

```text
origin    git@github.com:OD-Nature/xverif.git
upstream  git@github.com:BLANK2077/xverif.git
```

首次同步已使用 fast-forward 将本地 `master` 更新到 `upstream/master` 的 `0f6e281`。后续使用 merge 保留上游同步边界和兼容提交历史。

### 2.2 已确认的版本差异

| 项目 | Verdi 2023 主线路径 | Verdi 2018 已验证路径 |
| --- | --- | --- |
| xdebug design/FSDB | C/C++ NPI unified engine | 大部分 API 主链相同，需在当前 engine 上重新编译和实测 |
| xcov coverage | Python `pynpi.cov` | 无可用 Python coverage NPI，使用常驻 C++ worker 和 `npi_cov.h` |
| NPI 库目录 | `share/NPI/lib/LINUX64` | 需兼容 `LINUX64` / `linux64` |
| C++ ABI | 工具链默认 ABI | 已有适配使用 `_GLIBCXX_USE_CXX11_ABI=0` |
| coverage worker | Python 3.11 session | C++17 native JSONL worker |
| 公共合同 | 当前 `xdebug.v1` / `xcov.v1` | 必须复用当前合同，不复制旧 action/schema |

### 2.3 2018 coverage 已有实机证据

`xverif_2018/xcov/docs/coverage-api-capability.md` 记录的真实 probe 已证明 2018 C++ worker 可以：

- 打开并合并多个 coverage tests；
- 递归 instance 和 coverage object；
- 遍历 line、toggle、branch、condition、FSM、assert 和 functional coverage 对象；
- 读取 `covered`、`coverable`、`count`、status、file 和 line；
- 继承父对象的源码 evidence；
- 正常 close/checkin 后释放 license。

这些结果证明 native worker 路线可行，但固定 VDB 的覆盖率数字只作为 smoke evidence，不进入公共 API 合同。

## 3. 设计原则

### 3.1 上游优先

- 当前 `upstream/master` 是架构和公共合同的唯一基线。
- 不把 `xverif_2018` 的旧双 session、旧 handler、旧 schema 或预编译二进制带回主线。
- 上游新增 action 时，默认同时进入两个版本；只有底层 NPI capability 不支持时才显式声明差异。

### 3.2 差异集中

- 不在每个 action handler 中散布 `if Verdi == 2018`。
- 业务代码判断 capability，例如 `python_coverage=false`，而不是直接比较版本字符串。
- ABI、include、lib、rpath 和 worker 选择集中在 profile/build/provider 层。

### 3.3 合同一致

- `xdebug.v1`、`xcov.v1`、MCP tool 参数和 XOUT 结构不按版本复制。
- 允许诊断字段显示实际 backend，例如 `npi_python` 或 `npi_native_2018`。
- coverage item、summary、filter、limit、truncation、status 和 evidence 的语义必须一致。

### 3.4 显式选择、禁止静默 fallback

- 用户可显式选择 `verdi-2018` 或 `verdi-2023` profile。
- backend 失败时返回明确错误，不自动切换到另一版本、URG、假数据或其他 transport。
- 如果未来需要 fallback，必须由用户显式配置，并在响应中可见。

## 4. 目标架构

```text
CLI / MCP / SDK-free wrapper
             │
    xdebug.v1 / xcov.v1 schema
             │
    Session + Capability Registry
             │
    ┌────────┴─────────┐
    │                  │
 xdebug unified     xcov canonical
 engine             coverage model
    │                  │
 NPI compatibility   CoverageBackend
 shim               ┌──┴──────────────┐
    │                │                 │
 2018 / 2023      Python pynpi     C++ native worker
 profiles         Verdi 2023       Verdi 2018
```

### 4.1 EDA profile

建议新增集中式 profile，至少描述：

```yaml
name: verdi-2018
version_family: "2018"
npi:
  python_coverage: false
  native_coverage: true
  cxx11_abi: 0
  library_dirs:
    - share/NPI/lib/LINUX64
    - share/NPI/lib/linux64
capabilities:
  coverage_port_direction: false
```

2023 profile 则声明 Python coverage、默认 ABI 和对应库目录。具体文件格式和位置在实施阶段结合现有 Python/Makefile 入口确定，不预先绑定不必要的新框架。

建议的选择优先级：

```text
XVERIF_EDA_PROFILE
  > 项目配置文件
  > VERDI_HOME 版本探测
  > 无法确定时明确报错
```

### 4.2 xdebug 兼容边界

xdebug 保留当前 unified engine。实施顺序是先用 Verdi 2018 headers/libs 编译当前源码，再使用已知 daidir/FSDB 做最小查询；只有实际编译错误或运行证据证明 API 不兼容时才添加 shim。

兼容层可承担：

- header、enum、函数签名差异；
- NPI/FSDB handle 生命周期差异；
- API capability 探测；
- 版本相关错误归一化；
- target-local ABI 和 link flags。

不承担：

- 复制 trace、APB、AXI、stream 或 active-driver 业务逻辑；
- 恢复旧 design/waveform 双 session；
- 用旧 action schema 覆盖当前 schema。

### 4.3 xcov 双 backend

xcov 是已确认需要双 backend 的子系统：

```text
xcov actions/filter/summary/export/XOUT
                  │
          canonical coverage item
            ┌─────┴─────┐
            │           │
   PythonNpiBackend  NativeNpiBackend
       2023              2018
```

2018 worker 返回 canonical JSON，不直接承担最终 XOUT 排版。Python 层继续负责：

- action 参数与 schema；
- include/exclude 查询；
- limit、truncation 和 overflow；
- coverage 汇总；
- XOUT/JSON renderer；
- Markdown/JSON/NDJSON/CSV export。

### 4.4 MCP 与 LSF

- MCP 只面对公共 `xdebug.v1` / `xcov.v1`，不建立 2018 专用 MCP tools。
- direct 和 LSF backend 均需显式传递 EDA profile、`VERDI_HOME`、动态库和 license 环境。
- MCP/IDE 子进程不能假设继承交互 shell；所需环境必须显式注入。
- 真实 EDA 命令按仓库规则通过 xeda-runner 或已定义的测试入口执行。

## 5. 依赖与环境要求

### 5.1 通用依赖

| 依赖 | 要求 | 用途 |
| --- | --- | --- |
| Linux x86_64 | 需与 Synopsys 安装支持的平台一致 | Verdi/NPI 动态库运行 |
| Git | 支持 remote、fetch、merge | 持续同步 upstream |
| GNU Make | 仓库 Makefile 入口 | C++ 构建和测试 |
| C++ compiler | xdebug 当前文档要求 GCC 5.0+ | xdebug engine 与 unit tests |
| Python | 通用包要求 Python 3.10+ | xbit、xcov、xsva、测试脚本 |
| Python 3.11 | 建议用于 MCP 和 2023 pynpi 路径 | MCP SDK、xcov Python backend |
| pytest | 与仓库测试环境一致 | Python/contract tests |
| MCP Python SDK | 仅 MCP server 和 SDK smoke 需要 | `xverif_mcp` |
| numpy、Pillow | 仅 xwaveform 需要 | 波形渲染 |
| matplotlib | xwaveform 可选依赖 | 可选绘图 |

具体依赖版本以各子目录 `pyproject.toml`、Makefile 和 README 为准，不在兼容层重复维护一套包版本。

### 5.2 Verdi 2023 依赖

| 项目 | 计划要求 |
| --- | --- |
| Verdi | V-2023.12-SP2 作为上游已知基线 |
| C/C++ NPI headers | `$VERDI_HOME/share/NPI/inc` |
| L1 C headers | `$VERDI_HOME/share/NPI/L1/C/inc` |
| NPI libraries | `$VERDI_HOME/share/NPI/lib/LINUX64` |
| Python NPI | `$VERDI_HOME/share/NPI/python/pynpi` |
| Coverage API | Python `pynpi.cov` / `pynpi.npisys` |
| 数据 | 有效 daidir、FSDB、VDB fixtures |

### 5.3 Verdi 2018 依赖

| 项目 | 计划要求 |
| --- | --- |
| Verdi | O-2018.09-SP2 |
| C/C++ NPI headers | `$VERDI_HOME/share/NPI/inc`，包含 `npi.h`、`npi_cov.h` |
| L1 C headers | `$VERDI_HOME/share/NPI/L1/C/inc` |
| NPI libraries | 探测 `share/NPI/lib/LINUX64` 与 `share/NPI/lib/linux64` |
| C++ ABI | native NPI target 使用 `_GLIBCXX_USE_CXX11_ABI=0`，实施时重新验证作用范围 |
| xdebug compiler mode | 当前主线 C++11；需在 2018 headers/libs 下完整编译 |
| xcov native worker | C++17；旧工具链若缺 `<filesystem>`，按已验证方式链接 `-lstdc++fs` |
| Coverage API | C/C++ `npi_cov.h`，不依赖该版本没有的 Python `pynpi.cov` |
| 数据 | 已知有效的 daidir、FSDB、完整 VDB；不能使用空壳 VDB |

### 5.4 关键环境变量

| 变量 | 说明 |
| --- | --- |
| `XVERIF_HOME` | 必须指向当前工作树，不能残留指向 `xverif_2018` |
| `XVERIF_EDA_PROFILE` | 计划新增，显式选择 `verdi-2018` / `verdi-2023` |
| `VERDI_HOME` | 当前 profile 的 Verdi 安装根目录 |
| `XVERIF_XCOV_VERDI_HOME` | 可选，仅覆盖 xcov 使用的 Verdi 安装 |
| `LD_LIBRARY_PATH` | 包含当前 profile 的 NPI library dir；只在当前 session/process 注入 |
| `PATH` | 包含 xverif wrappers、Verdi/LSF 必需入口 |
| `PYTHONPATH` | MCP/本地开发模式下包含 `xverif_mcp/src` 等必要路径 |
| `SNPSLMD_LICENSE_FILE` | Synopsys license server/file 配置，值属于敏感环境信息，不写入仓库 |
| `SNPS_LICENSE_FILE` | 部署环境需要时设置，值不写入仓库 |
| `LM_LICENSE_FILE` | 部署环境需要时设置，值不写入仓库 |

环境变量应在 MCP、LSF job 或 xeda-runner session 中显式、局部设置，不修改全局 shell 配置，不在日志和文档中记录真实服务器、端口或 license 文件内容。

## 6. License feature 要求

### 6.1 已有证据支持的要求

2018 实机调试记录明确要求以下 feature 能成功 checkout：

| Feature | 适用场景 | 要求 |
| --- | --- | --- |
| `Verdi` | Verdi/NPI 初始化、设计/波形调试 | Verdi 2018 环境必须可 checkout |
| `VCSTools_Net` | coverage/NPI 相关访问 | Verdi 2018 coverage smoke 前必须可 checkout |

2018 native coverage worker应在一个 session 内只初始化和 checkout 一次；正常关闭时必须执行：

```text
npi_cov_close(db)
npi_end()
```

验收时需要确认 close/checkin 后 license server 上的占用回落。异常 kill 不能被当作正常释放路径。

### 6.2 需要部署前确认的 feature

仓库现有材料没有给出足够证据证明以下 feature 在所有 license server 上的精确名称，因此计划中不猜测或硬编码：

- VCS 编译使用的 feature；
- VCS 仿真运行使用的 feature；
- 不同合同包或地区安装中 Verdi/NPI feature 的别名；
- Verdi 2023 coverage Python NPI 是否额外占用独立 feature。

实施前由 EDA 管理员或实际 `lmstat`/checkout 日志确认，并把结果记录成不含服务器地址和完整唯一 ID 的环境矩阵。确认内容包括：

1. feature 名称；
2. 用于 compile、simulation、GUI、design NPI、waveform NPI 或 coverage NPI 中的哪一类；
3. checkout 数量；
4. session close 后的 checkin 行为；
5. LSF 计算节点是否能访问同一 license 服务。

### 6.3 License 诊断顺序

遇到 NPI open 卡住或失败时，按以下顺序排查：

1. 确认目标 daidir/FSDB/VDB 真实有效；
2. 确认加载的是所选 profile 对应的 NPI 动态库；
3. 确认必要 feature 可 checkout；
4. 查看 worker/engine stderr 和生命周期日志；
5. 关闭 session 后确认 feature 已 checkin。

不能因为 `npi_cov_open()` 卡住就直接判断为 license 故障。2018 已确认空壳 VDB 也会表现为长时间 hang。

## 7. 2018 coverage preflight 与生命周期

### 7.1 启动前检查

native worker启动前必须快速检查：

1. VDB 路径存在且是目录；
2. `vdb/snps/coverage/db` 存在；
3. coverage db 目录至少包含一个普通文件；
4. worker 二进制存在且可执行；
5. `VERDI_HOME`、headers 和 NPI library dir 有效；
6. worker 的 profile/ABI 与目标 Verdi 匹配。

建议错误码：

```text
INVALID_VDB
EMPTY_COVERAGE_DB
WORKER_NOT_FOUND
INVALID_VERDI_HOME
NPI_LIBRARY_NOT_FOUND
WORKER_ABI_MISMATCH
```

### 7.2 分阶段超时

至少区分：

- preflight timeout；
- worker spawn/handshake timeout；
- NPI/VDB open timeout；
- query timeout；
- close/checkin timeout；
- kill grace period。

错误响应必须包含 phase，避免把配置错误、初始化慢、license 等待和查询卡死混成同一类问题。

### 7.3 Worker 状态机

```text
NEW
 → PREFLIGHT_OK
 → SPAWNED
 → NPI_INITIALIZED
 → VDB_OPEN
 → READY
 → CLOSING
 → CLOSED
```

NPI 诊断进入 stderr；stdout 只允许 JSONL 机器协议，避免污染 MCP/stdio-loop。

## 8. 分阶段实施计划

### 阶段 0：建立可持续上游同步基线

任务：

- 固化 `origin` / `upstream` remote 约定；
- 记录当前 upstream commit；
- 采用 merge 工作流；
- 建立 `UPSTREAM_DELTA` 文档，记录所有对上游核心文件的修改及原因；
- 修复当前上游 `xdebug/Makefile` 中 `unit-test` 未声明 `trace_source_path_formatter.o` 依赖的问题，并验证测试从干净构建目录可重复运行。

验收：

- 工作树干净；
- `master...upstream/master` 关系可解释；
- 上游同步步骤可由另一位开发者复现；
- 通用快速测试在正确 `XVERIF_HOME` 下通过。

### 阶段 1：EDA profile 与构建兼容

任务：

- 增加 `verdi-2023`、`verdi-2018` profile；
- 集中 NPI include/lib 探测；
- 把旧 ABI flag 限制在 2018 native targets；
- 增加 profile/capability 的可观测输出；
- 为缺失路径、错误版本和混用动态库提供明确错误。

验收：

- profile 可显式选择；
- 无法识别版本时失败而非猜测；
- 2023 构建行为保持不变；
- 当前 xdebug 在 2018 headers/libs 下完成全量编译。

### 阶段 2：当前 xdebug 在 2018 上的最小实机验证

按能力逐步扩大，不从旧 engine 移植业务逻辑：

1. engine start/ping/quit；
2. daidir-only `session.open`；
3. FSDB-only `session.open`；
4. `value.at`、`value.batch_at`、`signal.changes`；
5. `trace.driver`、`trace.load`、`source.context`；
6. combined `trace.active_driver`；
7. APB/AXI/stream 基础查询；
8. session close、资源释放和 license checkin。

每个失败必须先记录编译错误、NPI symbol、运行 phase 和最小 fixture，再决定是否新增 shim。

验收：

- 当前公共 action/schema 不退化；
- 2018 smoke 返回真实 signal/path/time/value/file:line evidence；
- session close 后无残留 engine 和 license 占用。

### 阶段 3：移植 2018 native coverage backend

任务：

- 从 `xverif_2018` 提取 native worker的有效逻辑；
- 按当前 xcov backend 接口重新接入，不直接复制旧 session；
- 实现 VDB preflight、JSONL、stderr 隔离和状态机；
- 实现 canonical coverage item；
- 显式配置 backend/profile；
- 保证 close/checkin。

验收：

- 2018 使用 native backend；
- 2023 继续使用 Python pynpi backend；
- 两边共享当前 18 个公开 xcov actions；
- 不解析 URG HTML；
- backend 失败不静默 fallback。

### 阶段 4：跨 backend 合同等价

建立三类 fixtures：

1. fake canonical fixture：无 EDA、每次 CI 可跑；
2. provider fixture：分别模拟 Python 和 native 原始对象；
3. 真实 VDB smoke：在对应 Verdi/license 环境运行。

比较时只允许忽略明确的诊断字段，例如 worker/backend 名称；coverage item、summary 和 evidence 必须一致。

重点覆盖：

- tests/metrics list；
- scope summary/children/search；
- code coverage summary/holes；
- functional coverage summary/holes；
- source map/annotate；
- assertion summary；
- export；
- limit、filter、truncated 和 output path。

### 阶段 5：MCP、direct、LSF 双版本验证

任务：

- direct MCP 分别打开 2023 和 2018 session；
- LSF job 显式传递 profile、Verdi、library、PATH 和 license 环境；
- 验证同一 session 串行、不同 session 并行；
- 验证 timeout、worker crash、session close 和 stale session；
- 验证输出文件能力不因 backend 改变。

验收：

- MCP tools 不暴露版本专用副本；
- backend/capability 在 session status 或诊断中可见；
- 真实 LSF 失败能区分排队、环境、license、worker 和产品错误。

### 阶段 6：旧 action 与独立功能审计

`xverif_2018` 独有的旧 action 和 `xberif` 不属于第一阶段兼容范围。完成基础兼容后逐项判断：

- 是否已被当前 action 替代；
- 是否仍有实际用户；
- 底层能力是否仍存在；
- 应作为 engine action、MCP workflow 还是不再恢复。

优先审计 `port.trace`、`interface.resolve`、`trace.path` 和 `trace.graph`。不得直接复制旧 schema 覆盖当前合同。

### 阶段 7：上游同步演练与收口

任务：

- 在兼容开发完成后再次 fetch/merge upstream；
- 记录冲突文件和解决方式；
- 如果冲突集中在上游核心文件，反向调整兼容层边界；
- 将通用抽象整理成可考虑回馈 upstream 的独立提交。

理想状态下，私有差异最终主要剩下：

- 2018 profile；
- 2018 native coverage worker；
- 少量 NPI compatibility shim；
- 2018 实机 fixtures 和环境文档。

## 9. 测试矩阵

| 测试层 | 无 EDA | Verdi 2023 | Verdi 2018 | 执行位置 |
| --- | --- | --- | --- | --- |
| schema/example | 是 | 不需要 | 不需要 | 沙箱内 |
| fake backend contract | 是 | 不需要 | 不需要 | 沙箱内 |
| C++ unit | 是/需 headers | 可编译 | 可编译 | 普通主机；不访问真实数据 |
| xdebug full compile | 否 | 是 | 是 | 对应 EDA 环境 |
| daidir/FSDB smoke | 否 | 是 | 是 | 沙箱外，真实 NPI/license |
| xcov provider contract | fake | Python NPI | native worker | fake 沙箱内；真实查询沙箱外 |
| 真实 VDB smoke | 否 | 是 | 是 | 沙箱外，真实 license |
| MCP direct | fake | 是 | 是 | 真实查询沙箱外 |
| MCP LSF | fake LSF | 是 | 是 | 沙箱外，真实 LSF/license |
| close/checkin | 否 | 是 | 是 | 沙箱外，观察 license 状态 |

仓库现有主要入口包括：

```text
make -C xdebug schema-test
make -C xdebug unit-test
make -C xdebug contract-test
make -C xdebug test-fast
make -C xdebug test-regression
make -C xdebug test-nightly
make -C xdebug test-mcp-real-lsf
make -C xcov test
make test
make full-test
```

涉及 NPI、FSDB、daidir、VDB、VCS、VIP、真实 LSF 或 license 的目标必须从一开始就在沙箱外执行。不得把沙箱内失败直接判定为产品回归。

## 10. Git 与上游同步流程

每次同步建议：

```text
1. git fetch upstream --prune
2. 检查工作树与当前测试基线
3. 创建 sync/upstream-YYYYMMDD 临时分支
4. git merge upstream/master
5. 解决冲突并记录 upstream commit
6. 运行 common / 2023 / 2018 分层测试
7. merge 到兼容主线
8. 推送 origin，并记录验证矩阵
```

兼容实现提交应保持小而独立，例如：

1. profile/capability；
2. build flags；
3. coverage backend factory；
4. native worker；
5. preflight；
6. lifecycle/timeout；
7. contract tests；
8. 真实 smoke；
9. 文档。

不使用 `git add .`，不把构建产物、真实数据库、license 配置或用户环境路径提交到仓库。

## 11. 风险与控制措施

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 上游重构冲突 | 同步成本升高 | 新增兼容文件、缩小核心接入点、维护 UPSTREAM_DELTA |
| 旧 ABI 污染 2023 | 链接或运行异常 | ABI flag 仅作用于 2018 native target |
| 动态库版本混用 | 随机 crash、错误符号 | profile preflight、记录实际 library path |
| 空壳 VDB 卡住 | 误判 license 或 hang | checkout 前检查 `snps/coverage/db` |
| worker 异常退出 | license 未及时 checkin | 状态机、正常 close、独立 close timeout 与告警 |
| backend 输出漂移 | MCP/agent 行为不一致 | canonical model 和跨 backend golden |
| 静默 fallback | 返回不可信数据 | backend 显式选择，失败即明确报错 |
| MCP 环境不完整 | CLI 能跑、agent 不能跑 | 显式注入 env，增加 session doctor/capability |
| 真实 EDA 测试成本高 | CI 难以覆盖 | fake contract 常规跑，真实矩阵分层/定期跑 |
| 旧 action 被误当兼容需求 | 恢复过时代码 | 基础兼容完成后独立审计 |

## 12. 交付物

计划完成后应交付：

1. Verdi 2018/2023 profile 与 capability registry；
2. 集中的 NPI build compatibility 配置；
3. 当前 xdebug 在两个版本下的编译和 smoke 结果；
4. 2018 native coverage worker及 Python adapter；
5. VDB preflight、timeout、状态机和明确错误码；
6. 两个 coverage backend 的 canonical contract tests；
7. direct/MCP/LSF 分层验证报告；
8. license feature 与 checkin 验证矩阵；
9. `UPSTREAM_DELTA` 和上游同步操作说明；
10. 用户安装、profile 选择和排障文档。

## 13. 完成判定

只有同时满足以下条件，才能认为双版本兼容完成：

- 当前 upstream 功能和公共合同没有因 2018 适配退化；
- 2023 Python coverage backend 保持可用；
- 2018 native coverage backend 在真实完整 VDB 上通过；
- 当前 xdebug unified engine 在 2018 daidir/FSDB 上通过核心 smoke；
- 两个版本的 schema、XOUT、MCP tool 和 canonical coverage contract 一致；
- backend/profile 选择明确，无静默 fallback；
- session close 后 engine/worker退出，license 正常 checkin；
- 完成至少一次后续 upstream merge 演练，兼容层没有造成不可接受的冲突扩散；
- 所有已知限制、未支持 capability 和环境要求均有文档证据。

## 14. 建议的第一批实施任务

建议确认本计划后按以下顺序启动：

1. 修复并验证当前上游 `test-fast` 的 Makefile 依赖问题；
2. 建立 `UPSTREAM_DELTA` 和 EDA profile 最小骨架；
3. 在不运行真实数据库的前提下完成 2018 全量编译探针；
4. 整理编译/API 差异清单；
5. 再实施 xcov native worker前向移植；
6. 最后进入真实 2018 xdebug 和 coverage smoke。

在进入第 5、6 项前，应先确认测试数据、沙箱外执行权限、Verdi 2018 动态库、LSF 路径及 `Verdi` / `VCSTools_Net` feature 可用性。
