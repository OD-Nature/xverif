# xdebug Unified Engine Runtime 重构计划

日期：2026-06-25

来源：本计划基于 `xdebug/docs/XDEBUG_THIRD_PARTY_REVIEW_2026-06-25.md` 中关于 action 双实现、旧 router、session 边界和测试断层的发现，并吸收后续架构讨论结论。

目标：xdebug 只保留一个 action runtime。public CLI、MCP、stdio-loop、raw JSON、session daemon 都通过 unified engine 的 handler registry 执行 action。`design`、`waveform`、`combined` 目录只保留领域能力，不再拥有公共入口、公共响应 envelope、资源生命周期或 standalone router。

## 硬性规则

实施过程中必须满足以下规则。若在改造中发现新的遗漏，只要违反这些规则，就必须在同一轮计划实施中一并修复，不能留下“后续再清”的半废弃路径。

1. 只有 unified engine 可以作为 action runtime。
   - public action 只能通过 `src/engine/service/engine_action_registry.cpp` 注册并执行。
   - `src/design`、`src/waveform`、`src/combined` 不得再提供 standalone action router、action catalog、CLI query 入口或 public JSON envelope。

2. 资源生命周期只能由 unified engine 拥有。
   - `npi_init`、`npi_load_design`、`npi_end`、`npi_fsdb_open`、`npi_fsdb_close` 只能出现在 engine session daemon 的资源生命周期层，例如 `src/engine/server.cpp` 或后续抽出的 `src/engine/runtime/resource_manager.*`。
   - `design` helper 只能消费 engine 已加载的 design DB。
   - `waveform` helper 只能消费 engine 持有的 `npiFsdbFileHandle`。
   - `combined` helper 只能消费 engine 传入的 daidir/fsdb path 和已打开 FSDB handle，不能自行 init/load/open。

3. 通用 runtime 不能散落在 domain 目录。
   - JSON stdin/file 读取、request parse、response/error envelope、verbosity、session target 解析、endpoint transport、session path/registry 真源都必须在 `src/engine` 或 `src/core`。
   - `src/design` 和 `src/waveform` 只能保留领域算法、manager、parser、storage、analyzer、exporter 等能力代码。

4. 删除旧入口，不保留 compatibility router。
   - standalone design router 不保留。
   - standalone waveform router 不保留。
   - 若有旧 `.xdebug/design` 或 `.xdebug/waveform` 状态，只能通过显式 cleanup/gc 处理，不允许 silent fallback 到旧 runtime。

5. 完成标准包括全仓库验证和远端同步。
   - 计划实施完成后必须跑完整验证矩阵。
   - 验证通过后按阶段 commit，并推送至远端。
   - git commit 信息使用中文并写清楚改动范围和验证命令。

## 当前已知问题面

### 旧 runtime 入口

- `src/engine/main.cpp` 当前非 `--server` 查询路径仍 include 并调用 `design/commands/cmd_ai`。
- `src/design/commands/cmd_ai.cpp` 与 `src/design/service/router.cpp` 仍提供 design standalone action envelope。
- `src/waveform/main.cpp`、`src/waveform/commands/cmd_ai.cpp`、`src/waveform/service/router.cpp` 与 `src/waveform/service/action_registry.cpp` 仍提供 waveform standalone action envelope。
- `src/waveform/service/actions/*.cpp` 是旧 waveform action wrapper，和 engine waveform handlers 存在双实现风险。

### 公共 runtime 散落

- `src/design/service/action_support.cpp` 包含 JSON I/O、response/error envelope、verbosity、session JSON、target session 解析和 engine socket forwarding。
- `src/waveform/service/action_support.cpp` 包含 JSON I/O、session resolve、server command capture 等公共入口辅助。
- `src/design/session/session_transport.cpp` 与 `src/waveform/session/session_transport.cpp` 重复实现 endpoint 文件读写、connect、ping、quit。
- `src/design/common/xdebug_design_paths.cpp` 与 `src/waveform/common/xdebug_waveform_paths.cpp` 分别维护 session namespace；统一 runtime 后需要一个 canonical engine namespace。

### 资源生命周期散落

- 正确方向：`src/engine/server.cpp` 已集中执行 `npi_init`、`npi_load_design`、`npi_fsdb_open`，并持有 `g_has_design`、`g_has_waveform`、`g_fsdb_file`。
- 需要删除：`src/waveform/server/server.cpp` 仍自行 `npi_init` 和 `npi_fsdb_open`。
- 需要删除：`src/combined/active_trace_service.cpp`、`src/combined/active_trace_chain.cpp` 的旧入口仍自行 `npi_init`、`npi_load_design`、`npi_fsdb_open`。
- 需要收口：`src/combined/active_trace_common.h` 里的 `NpiSessionGuard` 与 `FsdbFileGuard` 不应存在于 product runtime 路径。

## 目标架构

```
public xdebug CLI / stdio-loop / MCP
  -> src/api/dispatcher.cpp
  -> EngineAdapter
  -> libexec/xdebug-engine ai query -        # short-lived open/dispatch query
  -> libexec/xdebug-engine --server ...      # long-lived session daemon
  -> EngineActionRegistry
  -> EngineActionHandler
  -> domain helper/service only
```

目录职责：

- `src/api`：public request validation、public response、schema/actions/batch/session dispatch。
- `src/engine`：唯一 action runtime、engine CLI query、session daemon、resource manager、engine handler registry、XOUT rendering。
- `src/core`：通用 session types、path utilities、transport utilities、file exchange、process/logging。
- `src/design`：design-only analysis helpers，例如 trace、AST、source、semantic、port、control dependency。
- `src/waveform`：waveform-only helpers，例如 FSDB value/time、list/cursor/event/APB/AXI/stream/export。
- `src/combined`：combined-only algorithms，只消费 engine 已初始化资源。

## 实施阶段

### 阶段 0：基线与保护

- 记录当前工作区状态，保留用户或其他任务已有改动，不回退无关文件。
- 跑最小基线：
  - `PYTHON=python3 make -C xdebug clean all`
  - `PYTHON=python3 make -C xdebug test-fast`
- 若基线已有失败，先记录失败和归因；如果失败来自沙箱、license、UDS、FSDB、VCS/Verdi 环境，按沙箱内/外 A/B 排查。

### 阶段 1：建立 engine 自有 query 入口

- 新增 engine 非 server query 入口，替代 `engine/main.cpp` 对 `design/commands/cmd_ai` 的依赖。
- 该入口只负责：
  - 读取 stdin/file JSON。
  - 校验 `api_version`。
  - 对 `session.open` 这类需要创建 daemon 的请求调用 engine session runtime。
  - 对普通 action 通过 engine handler registry 转发到已打开 session daemon。
- 删除 `engine/main.cpp` 中 include `design/commands/cmd_ai.h` 的路径。
- 保持 `xdebug-engine --server` 行为不变。

### 阶段 2：抽出公共 runtime

- 新增或整理以下公共模块：
  - `src/engine/runtime/request_io.*`：engine internal JSON stdin/file 读取与 parse。
  - `src/engine/runtime/response_builder.*`：internal response/error/meta/text envelope。
  - `src/engine/runtime/session_runtime.*`：target/session id 解析、transport options、session JSON、resource args。
  - `src/core/session/endpoint_transport.*`：endpoint 文件读写、UDS/TCP/file transport、ping、quit、version。
  - `src/engine/runtime/resource_manager.*`：NPI/design/FSDB 资源生命周期封装。
- 迁移 `design/service/action_support.cpp` 和 `waveform/service/action_support.cpp` 中的通用函数到上述模块。
- domain 侧只保留真正的领域 helper，例如 string/AST/trace/value/config 解析；不得保留 public response envelope。

### 阶段 3：统一 session namespace

- 将 canonical session state 收敛到 `xdebug-engine` namespace。
- design/waveform 旧 path facade 不再作为 session 真源：
  - `xdebug_design_*_path` 只在迁移过渡中服务 engine session manager，最终收敛为 engine path helper。
  - `xdebug_waveform_*_path` 中 list/APB/AXI/event/stream/cursor 文件路径改为 engine session dir 下的 domain artifact path。
- 移除 `.xdebug/waveform` registry/session 作为 runtime fallback。
- `session.gc` 可显式清理历史遗留目录，但普通 action 不得 silently reuse 旧目录。

### 阶段 4：资源生命周期唯一化

- 只保留 engine daemon 的资源初始化：
  - `npi_init`
  - `npi_load_design`
  - `npi_fsdb_open`
  - `npi_fsdb_close`
  - `npi_end`
- 删除 standalone waveform server 中的 NPI init/open server path。
- 删除 `ActiveTraceService::run()`、`ActiveTraceService::run_engine()` 这类 service/action 入口；combined 目录只保留无生命周期的 helper payload builder。
- `ActiveTraceChainService` 同样删除；`trace.active_driver_chain` 只能由 engine handler 调用 combined helper。
- `active_trace_common.h` 删除 `NpiSessionGuard`、`FsdbFileGuard`，或移动到测试专用代码；product runtime 只允许轻量 handle guard。
- 增加源码 contract：生产代码除 engine resource manager/server 外不得出现上述 NPI lifecycle 调用。

### 阶段 5：删除 standalone design runtime

- 从构建中移除并删除：
  - `src/design/commands/cmd_ai.cpp`
  - `src/design/commands/cmd_ai.h`
  - `src/design/service/router.cpp`
- 迁移仍有价值的 design action helper 到 engine handler 或 design helper 模块。
- `trace.*`、`source.*`、`expr.normalize`、`procedural assignment view`、`sequential update view`、`FSM explanation view`、`counter explanation view`、`port.trace`、`instance.map`、`interface.resolve` 必须全部只通过 engine handler registry 可达。

### 阶段 6：删除 standalone waveform runtime

- 从构建中移除并删除：
  - `src/waveform/main.cpp`
  - `src/waveform/commands/cmd_ai.cpp`
  - `src/waveform/commands/cmd_ai.h`
  - `src/waveform/service/router.cpp`
  - `src/waveform/service/action_registry.cpp`
  - `src/waveform/service/action_registry.h`
  - `src/waveform/service/actions/*.cpp`
- 保留并复用：
  - `src/waveform/server/service/*` 中非 server-envelope 的 value/scope/signal/event helper。
  - `src/waveform/list`、`cursor`、`event`、`apb`、`axi`、`stream`、`common`、`value`、`export`。
- 若删除旧 wrapper 时发现 engine handler 缺行为，必须先补 engine handler，再删除旧 wrapper。

### 阶段 7：构建图与文档收口

- 修改 `xdebug/Makefile`：
  - `DESIGN_SRCS` 只包含 design helper/session 能力，不再包含 command/router。
  - `WAVEFORM_SRCS` 只包含 waveform helper/server-service/domain 能力，不再包含 standalone main/router/action registry。
  - `UNIFIED_OBJS` 不再需要过滤 `waveform/main.o`。
- 更新 README、`CLAUDE.md`、xdebug docs 和 skill 中关于 “design engine / waveform engine / standalone internal engine” 的旧描述。
- 保留用户可见入口为 `xdebug`、MCP 和 stdio-loop，不引入新的 standalone binary。

## 防回归 contract

### Registry contract

- `EngineActionRegistry` 暴露稳定的只读 `list_names()`。
- `actions.yaml` 中所有 `status != removed` 且 `handler_kind: engine_forward` 的 action 必须在 engine registry 可达。
- removed action 不得在 engine registry 中注册。

### 源码 contract

新增测试脚本检查生产代码：

- `src/design` 和 `src/waveform` 下不得出现 standalone action envelope 符号：
  - `cmd_ai`
  - `run_query`
  - `handle_request`
  - `base_response`
  - `error_response`
  - `finalize_response`
  - `response_verbosity`
  - `action_known`
  - `print_actions`
- `src/combined` 下不得出现 `run_engine`、`ActiveTraceService`、`ActiveTraceChainService`、`NpiSessionGuard`、`FsdbFileGuard`。
- `src/design`、`src/waveform`、`src/combined` 下不得调用资源 lifecycle API：
  - `npi_init`
  - `npi_load_design`
  - `npi_end`
  - `npi_fsdb_open`
  - `npi_fsdb_close`
- 允许例外只限 `tests/`、`tools/` 或 engine resource manager/server 文件。

### 构建 contract

- Makefile 不再编译 design/waveform standalone main/router/action registry。
- `libexec/xdebug-engine` 是唯一 internal engine binary。
- `xdebug-engine ai query -` 和 `xdebug-engine --server` 都走 engine runtime，不走 domain router。

## 验证计划

实施中每个大阶段至少跑对应快速 gate；最终必须跑全仓库验证。

### 分阶段验证

- 入口和构建图阶段：
  - `PYTHON=python3 make -C xdebug clean all`
  - `PYTHON=python3 make -C xdebug schema-test`
  - `PYTHON=python3 make -C xdebug contract-test`
  - `PYTHON=python3 make -C xdebug unit-test`
- session/runtime 阶段：
  - `PYTHON=python3 make -C xdebug pytest-session`
  - `PYTHON=python3 make -C xdebug pytest-mcp`
  - `PYTHON=python3 make -C xdebug combined-test`
- waveform/design 行为阶段：
  - `PYTHON=python3 make -C xdebug test-synthetic`
  - `PYTHON=python3 make -C xdebug test-realdata-smoke`
  - 必要时补跑现有 waveform non-AXI smoke 和 design semantics smoke。

### 最终全仓库验证

最终完成后必须执行：

```bash
PYTHON=python3 make clean all
PYTHON=python3 make test
PYTHON=python3 make full-test
PYTHON=python3 make -C xdebug test-nightly
PYTHONPATH=xverif_mcp/src:. python3 -m pytest xverif_mcp/tests -q
```

如需真实 LSF：

```bash
PYTHON=python3 XDEBUG_ENABLE_REAL_LSF=1 make -C xdebug test-mcp-real-lsf
```

涉及 NPI、VCS/Verdi、FSDB、UDS、MCP、license、真实 LSF 的测试必须在沙箱外运行；若沙箱内失败，先确认是否为沙箱限制，再判断是否是产品回归。

## 交付与推送要求

- 大重构按阶段 commit，避免一个超大 commit 难以审查。
- 每个 commit 信息使用中文，说明：
  - 本阶段改动范围。
  - 删除了哪些旧入口或公共散落代码。
  - 跑过哪些验证命令。
- 推送前检查：
  - `git status --short`
  - `git diff --stat`
  - `git log --oneline -5`
- 验证全部通过后推送到当前分支的远端。
- 若存在与本计划无关的用户本地改动，不纳入提交、不回退；只提交本计划相关文件。

## 验收标准

- `src/design`、`src/waveform`、`src/combined` 不再拥有 action runtime 或资源 lifecycle。
- `npi_init/load/open/close/end` 只存在于 engine resource lifecycle 层。
- 所有 public action 都在 unified engine handler registry 中可达。
- 旧 standalone design/waveform router、cmd、action registry 从构建图和源码中移除。
- 全仓库验证命令通过。
- 所有计划相关改动已按阶段 commit 并推送至远端。
