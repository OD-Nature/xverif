# xdebug Action 返回全量 Replay 与修复计划（2026-07-09）

## 背景

本计划用于后续 goal 模式执行。目标不是继续按旧评审文档逐条猜测，而是以当前代码为基线，对 70 个 implemented xdebug action 做可复跑 replay 验收，再修复所有真实剩余缺陷。

当前基线：

- 2026-07-09 已完成一轮共性修复，覆盖公共错误合同、MCP 错误入口、handler 错误迁移、参数词典、表达式 alias、输出字段和 skill/docs 同步。
- 阶段 0 baseline fix 已提交：`c568c0d 修复：收紧波形表达式 action 请求合同`。
- `c568c0d` 已修复 `value.batch_at` / `verify.conditions` / `window.verify` 的已知 schema 缝隙，并通过：
  - `python xdebug/tools/sync_runtime_request_schemas.py --check`
  - `make -C xdebug schema-test`
  - 沙箱外 `make -C xdebug contract-test`
  - `python -m pytest xdebug/tests/contract/test_action_contract.py::test_waveform_expression_contract_schemas_are_strict -q`

## 已确认决策

1. 总目标：当前代码逐 action replay 验收优先，基于真实剩余缺口修复。
2. Replay 分为 L0/L1/L2/L3 四层矩阵。
3. repo 保存计划、矩阵、汇总报告；原始 per-action evidence 放 `/tmp`。
4. 所有 replay 发现的真实缺陷都必须修复，不做 P2/TODO 留存。
5. 允许分批实现、分批提交，但最终完成条件是全量缺陷清零。
6. 不要求 raw_request 和 stdio-loop 覆盖。
7. 每个 action 必须覆盖 native CLI JSON 与 native CLI xout。
8. 每个可通过 MCP 合理调用的 action 必须覆盖 MCP JSON 与 MCP xout 的成功路径。
9. MCP 错误路径按 family 代表 action 和问题 action 精准覆盖，不做全 action 错误矩阵乘法展开。
10. 第一批先做 replay harness + matrix spec，不先修单个 action。
11. Case registry 使用 repo 内 JSON 数据文件 + Python runner。
12. 每个缺陷必须保留 before/after replay evidence。

## Action 范围

当前 runtime catalog 为 70 个 implemented action：

- builtin：`actions`、`batch`、`schema`
- session：`session.open`、`session.list`、`session.doctor`、`session.gc`、`session.kill`、`session.close`
- design：`expr.normalize`、`signal.canonicalize`、`signal.resolve`、`source.context`、`trace.driver`、`trace.load`
- combined：`trace.active_driver`、`trace.active_driver_chain`
- waveform：其余 53 个 waveform/protocol/list/cursor/event/stream/value/signal/window action

所有 70 个 action 都必须进入矩阵。`session.*` 在 MCP 中不通过 `xverif_debug_query` 当普通 action 调用，使用 MCP session tools 覆盖，并验证 native session action guard。

## Replay 分层

### L0 静态合同层

目标：无需真实 session，证明 action catalog、schema、examples、docs 入口没有静态漂移。

必须检查：

- runtime `actions` catalog 与 `xdebug/specs/actions/actions.yaml` 一致。
- 70 个 action 都有 request/response schema 和 request/response example。
- request schema 顶层和 `args` 默认 `additionalProperties:false`。
- examples 全部通过 schema 校验。
- `sync_runtime_request_schemas.py --check` 和 `sync_action_schema_hints.py --check` 通过。
- `correct_example` 生成路径不得包含已废弃 alias，不得混入错误入口壳。

推荐命令：

```bash
make -C xdebug schema-test
make -C xdebug contract-test
python -m pytest xdebug/tests/contract/test_action_contract.py -q
```

### L1 Builtin / Session / Wrapper 层

目标：覆盖无 session action、session lifecycle、MCP wrapper 行为。

必须覆盖：

- `actions/schema/batch` native JSON + native xout。
- MCP `xverif_debug_list_actions`、`xverif_debug_get_schema`。
- MCP `xverif_debug_session_open/list/close`。
- `xverif_debug_query` 调 native `session.*` 时返回 `NATIVE_SESSION_ACTION_FORBIDDEN`。
- MCP `output_format` 支持 `json` 与 `xout`，错误路径保留当前入口 `correct_example`。

不要求：

- raw_request 全量覆盖。
- stdio-loop 全量覆盖。

### L2 成功路径层

目标：每个 action 至少一个成功样本，覆盖 native 和 MCP 的 AI 可读返回。

每个 action 必须产出：

- native CLI JSON success evidence。
- native CLI xout success evidence。
- MCP JSON success evidence，若 action 可通过 MCP 合理调用。
- MCP xout success evidence，若 action 可通过 MCP 合理调用。

成功路径检查：

- JSON `ok:true`。
- action 名称与请求一致。
- `summary` 包含第一屏可判定字段。
- compact xout 以 `@xdebug.<action>.v1` 或对应 MCP tool 返回格式开头。
- xout 第一屏能看出 action 结果状态、关键统计和是否 truncated。
- 对 partial success action，必须显式展示 `missing_count`、`failed_count`、`unknown_count`、`status` 或等价字段。

### L3 负例层

目标：每个 action 至少覆盖一个 schema 层错误和一个 handler/domain 层错误；MCP 错误按 family 代表和问题 action 覆盖。

每个 native 负例必须检查：

- `ok:false`。
- `error.code` 不使用泛化 code 承载明确错误。
- `error.error_layer` 为 `schema`、`handler`、`wrapper`、`transport` 或 `internal`。
- `error.invalid_arg` 指向真实错误字段。
- `error.expected` 或 `allowed_values` 可指导修复。
- `error.correct_example` 是当前入口形态，不回显本次坏值。
- 如适用，包含 `next_actions`、`available_values`、`missing_name`、`missing_resource`、`did_you_mean`。
- xout 错误也能看到上述核心字段。

MCP error 覆盖：

- 每个 action family 至少一个 schema error 和一个 handler error。
- 所有 replay 发现问题的 action 必须追加 MCP error case。
- MCP `correct_example` 必须是 MCP tool 参数形态，不能泄露 native envelope。

## 产物

Repo 内产物：

- `doc/xdebug_action_return_replay_full_fix_plan_2026-07-09.md`：本计划。
- `doc/xdebug_action_return_replay_matrix_2026-07-09.md`：70 action 人读矩阵。
- `doc/xdebug_action_return_replay_fix_report_2026-07-09.md`：最终修复报告。
- `xdebug/testdata/action_return_replay/cases.json`：replay case registry。
- `xdebug/tools/replay_action_returns.py`：replay runner。

`/tmp` 产物：

- `/tmp/xdebug_action_return_replay_<timestamp>/summary.json`
- `/tmp/xdebug_action_return_replay_<timestamp>/matrix.json`
- `/tmp/xdebug_action_return_replay_<timestamp>/evidence/<case_id>/...`

每个 case evidence 至少包含：

- `request.json`
- `response.json` 或 `response.xout`
- `metadata.json`，包含 command、entry、output_format、elapsed_ms、returncode、fixture、setup profile

每个缺陷必须包含：

- `before/<case_id>/...`
- `after/<case_id>/...`
- 修复 commit id
- 防回归测试路径和命令

## Case Registry 合同

`xdebug/testdata/action_return_replay/cases.json` 使用 JSON，不引入 YAML。

每个 action case 建议字段：

```json
{
  "action": "value.at",
  "family": "value",
  "requires": "waveform",
  "setup_profile": "ai_complex_wave",
  "mcp_applicable": true,
  "success": {
    "args": {
      "signal": "ai_complex_top.sig_a",
      "clock": "ai_complex_top.clk",
      "time": "75ns",
      "format": "hex"
    }
  },
  "schema_error": {
    "args": {
      "signal": "ai_complex_top.sig_a",
      "clock": "ai_complex_top.clk",
      "time": "75ns",
      "limit": 1
    },
    "expect": {
      "error_layer": "schema",
      "invalid_arg": "args.limit"
    }
  },
  "handler_error": {
    "args": {
      "signal": "ai_complex_top.no_such",
      "clock": "ai_complex_top.clk",
      "time": "10ns"
    },
    "expect": {
      "error_layer": "handler",
      "code": "SIGNAL_NOT_FOUND",
      "invalid_arg": "args.signal"
    }
  }
}
```

允许占位符：

- `${tmpdir}`
- `${wave_session}`
- `${design_session}`
- `${combined_session}`
- `${ai_complex_fsdb}`
- `${stream_fsdb}`
- `${design_daidir}`
- `${combined_fsdb}`
- `${combined_daidir}`
- `${apb_config}`
- `${event_config}`
- `${stream_config}`

占位符只能由 runner 解析，不能在 action runtime 中形成新兼容逻辑。

## Fixture Profiles

初始必须支持：

- `builtin`：无需 session。
- `ai_complex_wave`：`xdebug/testdata/waveform/ai_complex_wave/out/waves.fsdb`。
- `stream_v1`：`xdebug/testdata/waveform/stream_v1/out/waves.fsdb` + stream config。
- `design_uart`：`xdebug/testdata/design/uart/simv.daidir`。
- `combined_active_driver`：`xdebug/testdata/combined/active_driver/out/{simv.daidir,waves.fsdb}`。
- `combined_active_semantics`：`xdebug/testdata/combined/active_semantics/out/waves.fsdb`，如需 active semantics 特定信号。

APB/AXI/VIP 规则：

- APB 默认优先用 `ai_complex_wave/config/apb0.json`，避免真实 VIP 依赖。
- AXI 如需真实 VIP waveform，必须按 AGENTS 规则沙箱外执行；缺少 VIP/license 时标记 `blocked-by-env`，但必须保留复现命令。

## 分阶段任务书

### 阶段 0：Baseline Fix

状态：已完成。

提交：`c568c0d 修复：收紧波形表达式 action 请求合同`。

### 阶段 1：Replay Harness 与 Matrix Spec

目标：先建立统一判定器，不先修单个 action。

任务：

- 新增 `xdebug/tools/replay_action_returns.py`。
- 新增 `xdebug/testdata/action_return_replay/cases.json`。
- 生成 `doc/xdebug_action_return_replay_matrix_2026-07-09.md`。
- Runner 支持 native JSON、native xout、MCP JSON、MCP xout。
- Runner 支持 setup/teardown profile。
- Runner 输出 `/tmp/xdebug_action_return_replay_<timestamp>/summary.json`。
- Runner 对 L0/L1/L2/L3 case 统一打 case id。

验收：

- 70 action 全部出现在 matrix。
- 每个 action 至少有 success/schema_error/handler_error 计划位。
- 初始 runner 能跑 builtin、waveform value、design trace、combined trace、session tool 代表样本。
- 不修 action 逻辑。

### 阶段 2：全量 Replay 与缺陷归档

目标：跑出当前真实缺陷清单。

任务：

- 跑 L0/L1/L2/L3 全量 replay。
- 保存 before evidence 到 `/tmp`。
- 生成 `doc/xdebug_action_return_replay_fix_report_2026-07-09.md` 的初版缺陷清单。
- 每个缺陷归类为：
  - schema/runtime drift
  - schema error feedback
  - handler error feedback
  - MCP wrapper mismatch
  - success JSON usefulness
  - success xout usefulness
  - partial/empty semantics
  - path/security/noise
  - environment blocked

验收：

- 每个失败 case 有 evidence path。
- 每个缺陷有 action、entry、output_format、expected、actual、修复批次。
- 没有“观察到了但不修”的缺陷。

### 阶段 3：Schema / Runtime 漂移全修

目标：修复所有 schema 允许但 runtime 拒绝、runtime 接受但 schema 禁止、object union 内部约束弱的问题。

任务：

- 收紧 weak object/union schema。
- 修 runtime 对旧字段或不推荐字段的接受行为。
- 同步 `sync_runtime_request_schemas.py` 和 examples。
- 每个修复补 contract test。

验收：

- 所有 schema/runtime drift case 通过。
- `schema-test`、`contract-test`、相关 pytest 通过。
- before/after evidence 完整。

### 阶段 4：错误返回合同全修

目标：所有 schema/handler/MCP 错误路径都可由 AI 直接修复。

任务：

- 修缺失 `error_layer`、`invalid_arg`、`expected`、`allowed_values`、`did_you_mean`。
- 修 `correct_example` 回显坏值。
- 修 `correct_example` 入口壳错误。
- 修 not_found/config/resource/path 错误的 `available_values` 和 `next_actions`。
- 修 batch child failure 定位。
- 修 resource 前置条件错误仍使用 CLI usage 的路径。

验收：

- L3 native 全 action 通过。
- MCP family error cases 通过。
- 错误 xout 展示核心修复字段。
- 每个错误合同缺陷都有防回归测试。

### 阶段 5：成功返回与 XOUT 全修

目标：所有成功返回对 AI debug 有用，且不误导。

任务：

- 所有 compact xout 第一屏有 `summary` 或等价第一屏状态。
- 表格 section 不混 metadata。
- empty result 有 empty reason 和 next action。
- partial success 有显式 partial counters/status。
- path 和本机资源字段按 compact 策略脱敏或降噪。
- schema xout 对复杂 property/oneOf/conditional required 可读。
- verbose table 过宽问题收敛。
- config.list / export / query / time / line_limit 等成功返回做最终一致性检查。

验收：

- L2 native JSON/xout 全 action 通过。
- MCP success JSON/xout 全适用 action 通过。
- xout review 不再出现“看不出状态”“metadata 混行”“误以为成功/失败”的 case。

### 阶段 6：Docs / Skill / Mirror 同步

目标：文档和 skill 不重新引入旧合同。

任务：

- 更新 `doc/agents/xdebug/*.md`。
- 更新 `skills/xverif-cli/references/xdebug/*.md`。
- 更新 `skills/xverif-mcp/references/xdebug/*.md`。
- 检查 examples 中旧字段、旧入口、旧 output 形态。
- 如安装 mirror 有 Makefile target，按既有流程同步。

验收：

- 文档示例能通过 action-specific schema。
- skill 明确默认使用 MCP query / session tools，不推荐 native session action。
- `correct_example` 当前入口唯一原则写清楚。

### 阶段 7：最终全量 Replay 与交付

目标：证明所有缺陷清零。

任务：

- 重新跑全量 L0/L1/L2/L3 replay。
- 保存 after evidence。
- 更新 final fix report。
- 跑关联测试矩阵：
  - `make -C xdebug schema-test`
  - `make -C xdebug contract-test`
  - `make -C xdebug pytest-contract`
  - waveform/design/combined/MCP focused tests，按改动范围选择
  - VIP/LSF/realdata 相关项按 AGENTS 规则沙箱外执行
- 分批 commit，commit message 中文写清动机、范围、验证。

验收：

- replay summary 中无 unresolved defect。
- 仅允许 `blocked-by-env`，且必须包含复现命令、缺失环境和不阻塞原因。
- final report 中每个 defect 都有 before evidence、after evidence、修复 commit 和防回归测试。

## 缺陷完成定义

一个缺陷只有满足以下条件才算完成：

1. replay before evidence 能复现。
2. 修复后 replay after evidence 通过。
3. 有自动化防回归测试或明确说明为什么只能靠 replay case 覆盖。
4. 对应 docs/skill/schema/example 已同步。
5. `git status --short` 在提交前只包含相关文件。
6. commit message 中文说明动机、范围、验证。

## 环境阻塞规则

涉及 NPI、VCS、VIP、真实 license、真实 LSF、MCP stdio/port/file transport 的动作按 AGENTS 规则沙箱外执行。

如果失败：

1. 先判断是否 sandbox-vs-host 差异。
2. 不允许私自 fallback 到别的 backend、transport、数据源或测试层级。
3. 只有真实环境缺失时才标记 `blocked-by-env`。
4. `blocked-by-env` 必须记录：
   - action
   - case id
   - command
   - 缺失环境
   - stdout/stderr 摘要
   - 后续复现方式

## Goal 模式目标文本

后续可直接使用以下目标：

> 以 `doc/xdebug_action_return_replay_full_fix_plan_2026-07-09.md` 为任务书，实现 xdebug 70 个 action 的返回可用性全量 replay harness、case registry、矩阵和修复闭环。先完成 replay harness 与 matrix，再运行 L0/L1/L2/L3 全量 replay，基于当前代码真实缺陷逐批修复 schema/runtime 漂移、错误返回合同、MCP 返回壳、成功 JSON/xout 可用性、partial/empty/path/noise 问题。所有 replay 发现的真实缺陷必须修复并保留 before/after evidence、防回归测试、中文 commit 和最终报告；除真实环境阻塞项外不允许遗留 TODO。
