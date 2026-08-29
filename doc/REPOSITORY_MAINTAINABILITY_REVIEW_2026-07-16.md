# xverif 全仓代码与维护性评审（2026-07-16）

## 结论

仓库已经具备较强的合同意识：xdebug 的 action/schema/source-of-truth、catalog 驱动的测试入口、skill 的链接与示例检查均已建立；本次正式 fast gate 也通过了 232 项测试。但当前不宜把这些通过结果等同于「运行结果可信」或「关键路径已充分覆盖」。

最优先修复的，是会把失败伪装成成功的 MCP 行为、SDK-free UDS 的并发/文件安全边界，以及没有进入正式 gate 的 xdebug action 语义 replay。对单人维护而言，先消除这些高杠杆问题，再减少兼容层、死代码和测试编排复杂度，收益最高。

## 范围、方法和限制

- 范围：受 Git 跟踪的 xdebug、xverif_mcp/xverif_loop、xbit、xentry、xcov、xloc、xsva、xwaveform、testinfra、skills、根构建/打包配置；第三方 `xdebug/third_party/` 只计入规模，不审查其实现。
- 方法：四个并行视角（架构/安全与生命周期、测试、skill/AI 可用性、主审的构建与重复代码核查），逐项阅读源码、catalog、schema、README 与测试；未运行真实 NPI/FSDB/VCS/LSF/VIP。
- 动态证据：`pytest --xverif-gate fast` 在沙箱内通过，`232 passed, 397 deselected`，耗时 11.13 秒；其 11 个 suite 均为 fast 的纯本地范围，不应外推为真实 EDA 集成已验证。
- 本报告是静态和 hermetic gate 审计；外部工具版本、license、真实波形和多用户主机上的运行行为需要按下文新增的 host-only 用例验证。

严重性定义：P1 为可能导致静默错误、资源泄漏或不安全破坏；P2 为高概率维护/诊断风险；P3 为发布、结构或长期成本问题。

## P1：先处理

### P1-01 MCP 的输出落盘失败被吞掉，调用方仍看到成功

`xverif_output_path` 的包装器在写文件失败时捕获所有异常并直接返回原 action 结果，[xverif_mcp/src/xverif_mcp/server.py](../xverif_mcp/src/xverif_mcp/server.py#L97) 和 [server.py](../xverif_mcp/src/xverif_mcp/server.py#L107)。现有测试还把「无效目录仍 pong」作为正确行为，[test_mcp_sdk_smoke.py](../xverif_mcp/tests/test_mcp_sdk_smoke.py#L422)。因此 AI 或脚本会认为分析结果已经写出，但指定文件不存在或不完整。

建议：写入失败返回结构化 `OUTPUT_WRITE_FAILED`（可保留原 action result），或删除这个公共参数；增加不可写目录、append 与部分写失败测试，并同步 MCP schema、skill 示例和错误说明。

### P1-02 batch 把错误类型的 `args` 静默替换成空对象

batch 读取到非 object 的 `args` 后直接改为 `{}` 并继续执行，[xverif_mcp/src/xverif_mcp/server.py](../xverif_mcp/src/xverif_mcp/server.py#L219)。例如字符串参数不会被定位成输入错误，可能变成另一个「缺参数」结果，甚至执行无参 tool。已有 batch 测试只覆盖 JSON 解析和缺 `tool`，未覆盖 `args` 类型和行号。

建议：拒绝该行，返回 `INVALID_BATCH_ARGUMENTS` 并带 batch 行号；禁止调用 tool。补齐 `args` 类型、未知 tool、结果文件不能打开的矩阵测试。

### P1-03 同名并发 open 可能遗失 session 和子进程

UDS server 为每个客户端创建 daemon thread，[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L315)；而 session manager 对「名称不存在→启动→写入 map」没有 map 级锁或 opening reservation，[session_manager.py](../xverif_mcp/src/xverif_loop/sessions/session_manager.py#L120)。两个 client 同时 open 同名 session 时，后写者会覆盖 map，先启动的 child 将无法由 close/gc 找到。现有并发测试只覆盖 query，不覆盖同名 open 或 open/close/gc race。

建议：为 manager 的 sessions/tombstones 引入 `RLock`，使用 opening reservation 保证一次 launch；新增两个 UDS client 同名并发 open 的 fake-loop 回归，断言一次 launch 与一次 `SESSION_ID_EXISTS`。

### P1-04/05 UDS 默认权限和 socket 路径处理不安全

默认 socket 在 `<repo>/tmp/xverif-loop-<uid>.sock`，[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L111)，bind 后没有 `chmod(0600)` 或 peer credential 验证，[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L301)。任一能连接的 client 都可无认证执行 `server.shutdown`，[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L362)。同时启动时只要路径存在就 `unlink()`，[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L295)；误把 `--socket` 指向普通文件会删除它，也可能抢占另一个 wrapper。

建议：仅清理当前用户拥有、`lstat` 确认的 stale socket；普通文件、symlink、异主路径、活动 socket 都报 `SOCKET_PATH_UNSAFE`。bind 后显式 `chmod(0600)` 并验证 owner/mode；若产品需要共享，再明确引入 `SO_PEERCRED` allowlist 或认证 token。补 socket mode、普通文件、symlink、活动 socket 和未授权 shutdown 的测试与 skill 文档。

## P2：可靠性、边界和维护负担

### P2-01 action return replay 已完整删除

经确认该 replay 体系不纳入任何门禁，因此已删除其 runner、registry/testdata、专用 pytest、矩阵与历史报告。后续 action 行为由公开 schema/contract 和对应功能测试维护，不保留无执行价值的人工索引。

### P2-02 fixture cache 未指纹化外部 VIP 和 effective default environment

fixture fingerprint 只包含 repo 源、builder/probe 声明和 `tool_env`，[fixtures.py](../testinfra/xverif_test/fixtures.py#L97)；随后 builder 才以 `setdefault` 注入 `default_env`，[fixtures.py](../testinfra/xverif_test/fixtures.py#L220)。AXI/APB fixture 依赖 `$HOME/axi_test/test` 与 SVT VIP 路径，却只声明 `VERDI_HOME`，[fixtures.v1.yaml](../testinfra/fixtures.v1.yaml#L88)。换机、切换 VIP 或修改外部参考工程后可能命中旧 cache。

建议：将 effective env、外部根目录的版本/manifest/digest 纳入 fingerprint，并在 prepare 前验证路径/命令；增加 override 改变、路径缺失、外部版本改变的纯 Python 测试。能力 snapshot 目前还把 `fsdb`/`daidir` 无条件声明为可用，[environment.py](../testinfra/xverif_test/environment.py#L43)，也应改为可操作的依赖诊断。

### P2-03 SDK-free shared layer 反向依赖 MCP 包

`xverif_loop` 标称 SDK-free shared layer，却直接 import `xverif_mcp.xdebug_errors`（[wrapper.py](../xverif_mcp/src/xverif_loop/wrapper.py#L29)；[loop_session.py](../xverif_mcp/src/xverif_loop/sessions/loop_session.py#L23)）。这使该层无法独立发布或最小安装，边界与命名承诺不一致。现有测试只 grep 是否导入 MCP SDK/server，并不验证可独立 import。

建议：把共享 lifecycle/error formatting 下沉到 `xverif_loop.errors` 或无 MCP 依赖模块，MCP 仅保留 tool 投影；新增隔离 `PYTHONPATH` import 和依赖方向静态检查。

### P2-04 服务退出时 cleanup 异常无统一诊断

MCP lifespan cleanup 对异常 `pass`，[server.py](../xverif_mcp/src/xverif_mcp/server.py#L43)，退出后无法判断哪个 backend/session 未清干净。建议记录结构化 shutdown event（backend、未清 session 数、错误摘要），并用 adapter `close_all` 抛错的测试固定该诊断合同。

### P2-05 已确认的死代码/旧抽象制造虚假路径

以下 header 通过精确符号和 include 检索仅命中自身定义（或彼此），不在生产 Makefile source list 中：

- [action_handler.h](../xdebug/src/waveform/service/action_handler.h#L1) 与 [action_context.h](../xdebug/src/waveform/service/action_context.h#L1)
- [command_builder.h](../xdebug/src/waveform/service/command_builder.h#L1)
- [router_actions.h](../xdebug/src/waveform/service/router_actions.h#L1)
- [summary_builder.h](../xdebug/src/core/output/summary_builder.h#L1)

建议先做一次外部 consumer 核实后删除，随后新增「public header 必须有 allowlist consumer」静态检查。不要与功能修复混在同一提交。

### P2-06 test report 的失败诊断路径未被验证

`ResultManager` 负责阶段、错误层、stdout/stderr 与结果汇总，但测试只验证最小 schema 和 setup-skip，[test_report_schema.py](../testinfra/tests/test_report_schema.py#L13)。失败 call/teardown、timeout、captured log、xdist 汇总、junit 与 report.json 的关联没有保护。

建议通过伪 pytest report 覆盖这些分支，并验证 `report.json`、junit 和 `pytest-captured.log` 能互相定位。这是单人排障最直接的成本控制。

### P2-07 真实跨层 MCP/UDS 测试不足，且测试编排覆盖面不可量化

wrapper 测试大量使用 echo 型 fake loop，无法证明真实 xdebug/xcov 的 ready、schema、退出和 cleanup 能协作。保留 fake 单测，但新增 host-only 最小真实二进制 suite（open/query/invalid/close/crash-or-timeout）。同时仓库没有 coverage 或 production-source-to-test manifest；xdebug 约 281 个 C++ 源/头文件，C++ runner 仅固定执行 20 个 unit binary，[run_xdebug_cpp_units.py](../testinfra/leaf/run_xdebug_cpp_units.py#L8)。

建议不先设覆盖率百分比，而是让每个公开 action/主要模块至少声明正向、参数拒绝、环境失败三类测试，并自动生成「catalog→测试→fixture→capability」表。catalog 重写 collection 的机制较复杂，当前完整性扫描主要只覆盖 `test_*.py` 与 unit C++，应扩展至脚本和生成测试。

## P3：skill、打包和长期一致性

### P3-01 skill 生成器声明 canonical source，却没有读取它

`generate_references.py` 把 `examples.yaml` 标为 canonical source，[generate_references.py](../skills/xverif/scripts/generate_references.py#L14)，但 `surface_examples()` 将 action/session/args 完全硬编码，[generate_references.py](../skills/xverif/scripts/generate_references.py#L60)。`--check` 只能检查这套硬编码输出，因此改 YAML 不会影响产物。

建议真实解析 YAML，或删除 canonical 宣称和无效文件；测试应编辑临时 source 后验证生成内容改变，而非只运行同一脚本的 `--check`。

### P3-02 xwiki 查询流程与写回授权自相矛盾

skill 前文规定未授权只能提出建议，[xwiki/SKILL.md](../skills/xwiki/SKILL.md#L15)；查询流程第 7 步却要求信息不足时「编译回 wiki」，[xwiki/SKILL.md](../skills/xwiki/SKILL.md#L40)。纯查询可能诱导 agent 越权写文件。

建议把第 7 步改为「仅在已有写回授权时编译回；否则在最终结果列出建议」，并增加文本合同测试防止反向漂移。

### P3-03 skill 安装镜像不可复现，路由 golden 保护弱

根 Makefile 直接 `cp -R` 整个 skill 到本地 Codex/Claude 目录，[Makefile](../Makefile#L66)，没有 exclude、manifest、版本或 copy 后 `diff -qr`；工作区已有忽略的 `__pycache__`，容易被带入镜像。另 `routing.yaml` 仅被字符串 split 测试，[test_xverif_skill.py](../skills/tests/test_xverif_skill.py#L99)，既不解析 YAML，也不验证 `SKILL.md` 的实际路由表。

建议使用 rsync/allowlist 排除缓存，写 manifest（commit/version/file digest）并验收 diff；用 YAML parser 读取 routing cases，且把它们与技能正文的 route/capability 约束关联，或删除没有消费方的 golden。

### P3-04 x-npi 公共示例覆盖不全，静态 trace 错误不可诊断

skill 列出 6 个示例，[x-npi/SKILL.md](../skills/x-npi/SKILL.md#L57)，真实测试只执行 AXI/APB/stream，[test_x_npi_real.py](../skills/tests/test_x_npi_real.py#L55)。`trace_driver_summary.py` 将所有异常压成 `FAILED + str(exc)`，[trace_driver_summary.py](../skills/x-npi/scripts/examples/trace_driver_summary.py#L22)，缺少 dbdir/signal/mode/stage 等结构化字段，弱于同包 `error_document`。

建议为 wave_stats、coverage_summary、trace_driver_summary 增加 fixture-backed host-only 测试；trace 示例复用结构化错误格式，使 AI 能区分 config、数据库、signal 与 NPI 生命周期错误。

### P3-05 根包的用途不清，干净安装无法证明可运行

根 distribution 名为 `xverif-testinfra`，仅声明 pytest/schema 依赖，却同时打包 `xverif_mcp`/`xverif_loop`，没有 console entry point；MCP 依赖由 README 另行手装，wrapper 依赖 checkout-relative `PYTHONPATH`。这使 `pip install -e .` 是否能从干净环境运行不明确。

建议选择一个边界：要么把它做成 runtime package，声明 MCP extra/entry points 并有 clean-venv `--help` smoke；要么只保留 testinfra，runtime 拆为独立 package。二者不要混合。

## 推荐实施顺序

1. 修 P1-01/P1-02，统一「公开参数失败必须可见」合同并同步 skill/schema/test。
2. 修 P1-03/P1-04/05；随后在 host-only suite 验证并发、socket mode 和 stale path。
3. 将 action replay 注册进 catalog，并修 fixture fingerprint/preflight；这两项决定真实回归可信度。
4. 整理依赖方向、shutdown 诊断、死 header；每个主题独立提交，避免误删和回归定位困难。
5. 最后处理 skill source-of-truth、安装镜像、x-npi 示例和 Python packaging，并将新的清洁环境 smoke 纳入 fast 或明确的 component gate。

## 已确认的正面基础

- fast gate 的 232 项通过，且 skill、catalog、xdebug static 与 MCP unit 都在其中。
- action/spec/schema 的 source-of-truth 和生成检查已经存在，修复重点是让真实执行路径也进入 gate。
- session/MCP 并非没有测试：已有 crash、resource change、fake process timeout 等覆盖；缺口是同名 open race、真实跨层最小链路和外部依赖漂移。
- `skills/xverif` 已有明确 capability router 与最小查询流程；当前最大 AI 风险来自运行时的静默成功，而不是 route 缺失。
