# xcov

`xcov` 是面向 AI/MCP 的 VCS/Verdi coverage database 查询工具。它读取
`simv.vdb`、`merged.vdb`，接受 `xcov.v1` JSON 请求，默认返回紧凑的
`xout`；需要机器 JSON 时设置 `output.response_format:"json"`，或使用
`tools/xcov --json -`。

xcov 只以 VDB/Verdi NPI coverage API 为数据源：2018使用 C++ `npi_cov.h` native
worker，2023使用 Python `pynpi.cov`。它不解析 URG HTML、`asserts.html`、
`mod*.html` 或 `session.xml`。只有 Verdi NPI文档、headers
和真实 VDB probe 证实可获取的字段才会进入公开 schema；拿不到的 URG 字段不
提供接口，也不会用 note 占位。

## 快速开始

一次性 JSON 查询：

```bash
printf '%s\n' '{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"fake"},"args":{"name":"cov0","fake":true}}' \
  | tools/xcov --json -
```

MCP/长会话使用 stdio-loop：

```bash
tools/xcov --stdio-loop
```

stdio-loop 启动后输出 `protocol:"xcov-stdio-loop"` ready 行，后续每行接收一个
JSON request，并返回包含 `xout` 和 `json` payload 的 JSONL envelope。NPI 诊
断输出会导向 stderr，stdout 保持机器可解析。

## 真实 NPI 运行

真实 VDB 查询需要 Synopsys Verdi NPI和 license。按项目规则，NPI、
VCS、VIP、真实 coverage probe 必须在沙箱外运行。

双版本 backend 选择规则：

- `XVERIF_EDA_PROFILE=verdi-2018`：使用常驻 C++ native NPI worker。
- `XVERIF_EDA_PROFILE=verdi-2023`：使用 Python `pynpi.cov` backend。
- `auto`：从版本化 `VERDI_HOME` 自动判断；无法判断时明确报错。
- `XVERIF_XCOV_BACKEND=native|python` 可显式覆盖；不会静默 fallback。

`tools/xcov` 会在当前子进程内把对应 NPI library 目录加入
`LD_LIBRARY_PATH`。2018 worker 需要先执行
`XVERIF_EDA_PROFILE=verdi-2018 make -C xcov native`。

## 可分发自检

仓库自带 `testdata/basic_coverage`，会用基础 VCS code coverage 生成包含两个
test 的真实 `simv.vdb`，不依赖外部工程或 VIP：

```bash
make -C xcov self-test-2018
make -C xcov self-test-2023
```

自检会依次运行纯单测、编译/运行 fixture、打开真实 VDB，并校验
line/toggle/branch、Verdi 等权 Score、raw weighted coverage 和 session close。
需要对应版本的 VCS、Verdi/NPI 和可用 license。

支持与验证状态：

| Profile | Coverage API | 状态 |
|---|---|---|
| `verdi-2018` / O-2018.09-SP2 | C++ `npi_cov.h` native worker | 已通过仓内2-test VDB、GPIO和xip实机验证 |
| `verdi-2023` / V-2023.12-SP2 | Python `pynpi.cov` | 原作者支持路径；待本兼容分支在2023机器运行自检 |

2018 coverage smoke已有证据要求 `Verdi` 和 `VCSTools_Net` feature可 checkout；
不同站点的 VCS compile/runtime feature名称应由 EDA管理员确认。

## MCP 工具

`xverif_mcp` 暴露 xcov stateful backend：

```text
xverif_cov_session_open
xverif_cov_session_list
xverif_cov_session_use
xverif_cov_session_close
xverif_cov_query
xverif_cov_raw_request
xverif_cov_list_actions
xverif_cov_get_schema
```

环境变量：

- `XVERIF_MCP_ENABLE_COV=0`：隐藏 coverage 工具。
- `XVERIF_XCOV_BIN`：覆盖 xcov 可执行文件。
- `XVERIF_XCOV_PYTHON`：覆盖 xcov Python runtime。
- `XVERIF_XCOV_VERDI_HOME`：覆盖 `VERDI_HOME`。
- `XVERIF_XCOV_LOG_DIR`：覆盖日志目录。
- `XVERIF_XCOV_LOG=0`：关闭日志。

## 常用请求

打开 session：

```json
{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"merged.vdb"},"args":{"name":"cov0"}}
```

查询 holes：

```json
{"api_version":"xcov.v1","action":"code_coverage.holes","target":{"session_id":"cov0"},"args":{"scope":"uart_tb","metrics":["line","toggle","branch","condition","fsm","assert"],"limits":{"max_items":100}}}
```

按通配过滤 code coverage hierarchy holes：

```json
{"api_version":"xcov.v1","action":"code_coverage.holes","target":{"session_id":"cov0"},"args":{"scope":"uart_tb","query":{"include_patterns":["*u_uart*"],"exclude_patterns":["*uvm*"],"match_field":"full_name"}}}
```

查询 function coverage holes：

```json
{"api_version":"xcov.v1","action":"function_coverage.holes","target":{"session_id":"cov0"},"args":{"levels":["bin"],"query":{"include_patterns":["*APB_accesses_cg*"],"match_field":"full_name"}}}
```

源码位置反查 coverage object：

```json
{"api_version":"xcov.v1","action":"source.map","target":{"session_id":"cov0"},"args":{"file":"rtl/ctrl.sv","line":123,"window":3}}
```

源码窗口加 coverage annotation：

```json
{"api_version":"xcov.v1","action":"source.annotate","target":{"session_id":"cov0"},"args":{"file":"rtl/ctrl.sv","line":123,"window":3}}
```

assert 汇总：

```json
{"api_version":"xcov.v1","action":"assert.summary","target":{"session_id":"cov0"}}
```

导出 code coverage 未达标项：

```json
{"api_version":"xcov.v1","action":"export.code_coverage","target":{"session_id":"cov0"},"args":{"scope":"uart_tb","threshold_pct":100.0,"output":{"path":"code_coverage.md"}}}
```

导出 function coverage 未达标 bin：

```json
{"api_version":"xcov.v1","action":"export.function_coverage","target":{"session_id":"cov0"},"args":{"covergroup":"*","threshold_pct":100.0,"output":{"path":"function_coverage.md"}}}
```

导出 assertion coverage：

```json
{"api_version":"xcov.v1","action":"export.assert","target":{"session_id":"cov0"},"args":{"scope":"uart_tb","threshold_pct":100.0,"output":{"path":"assert.md"}}}
```

## URG 对齐语义

`code_coverage.summary`、`code_coverage.holes`、`metrics.list`、`scope.summary`、
`source.map` 和 Markdown exports 使用与 URG HTML 报告一致的 score-bearing
object 层级：

- Line：`npiCovStmtBin`
- Condition：`npiCovConditionBin`
- Toggle：`npiCovToggleBin`
- Branch：`npiCovBranchBin`
- FSM：`npiCovTransBin`
- Assert：`npiCovAssert`、`npiCovCoverProperty`、`npiCovCoverSequence`

中间对象，例如 line block、toggle signal、branch/condition object、FSM state
container、assert Attempt/Success/Failure bin，会被遍历用于上下文和证据，但不
计入公开 summary 分母。

`function_coverage.summary` 的 covergroup score 按 URG group 页语义计算：优先取直接
coverpoint/cross coverage 百分比的平均值；交互输出不暴露 score_basis/raw count
等中间计算字段。

## Action 合同

- `scope.summary`：返回当前层次的扁平覆盖率字段，例如
  `coverage_pct`、`line_pct`、`toggle_pct`、`branch_pct`、`condition_pct`、
  `fsm_pct`、`assert_pct`、`functional_pct`，并带 module 对应的 `file/line`
  evidence（若 NPI 暴露）；不输出 parent/depth/type/def_name。`coverage_pct` 按
  Verdi GUI Score 语义对有效 metric 百分比等权平均；`raw_coverage_pct` 保留按
  全部 coverable 数量加权的原始比值，`score_basis` 明确为
  `average_metric_pct`。
- `scope.children` / `scope.search`：只返回 `name/full_name/coverage_pct`，用于定位
  hierarchy 名称和快速查看当前覆盖率。
- `code_coverage.summary`：按 metric、scope 或 source file 汇总代码覆盖率；不输出
  name/full_name/functional_pct。
- `code_coverage.holes`：按输入 hierarchy 输出当前层次和子模块的覆盖率概览，只保留
  `name/full_name/coverage_pct/*_pct`，不展开具体 signal、branch、condition 或 bin，
  也不输出 parent/depth/type/def_name/covered/coverable/missing/file/line。具体未覆盖项请使用
  `export.code_coverage`。
- `function_coverage.summary`：按 covergroup、coverpoint、cross 或 bin 汇总功能覆盖率，
  不输出 metric/name/full_name/score_basis/score_item_count/raw_* 字段，包括
  raw_coverage_pct。
- `function_coverage.holes`：输出未覆盖的 function coverage 项，支持 `levels` 和
  `query` glob 过滤；不输出 metric/name/full_name/score_basis/score_item_count/raw_* 字段。
- `source.map`：按源码 file/line/window 反查 coverage item。
- `source.annotate`：基于 NPI `file_name()/line_no()` evidence 和项目源码文件输出源码
  窗口。它可以挂接 line/branch/condition/toggle/assert object annotation，但不承诺
  URG HTML 专有展示标签，例如 `MISSING_ELSE`；除非后续 NPI API probe 证明这些标签
  可取。
- `assert.summary`：输出 assert/cover property/cover sequence 的基础覆盖率和
  attempts/real successes/without attempts；不输出 kind/category/severity/failures/
  incomplete/first_match/file/line。详细报告请使用 `export.assert`。

## Markdown 导出

`export.code_coverage`、`export.function_coverage`、`export.assert` 只输出 Markdown
文件，不保留 `output.artifact_format` 选择。响应的 `summary.note` 会提示：需要复杂
处理、二次统计或跨报告加工时，请调用 `x-npi` 学习 `pynpi` coverage API 并编写脚本。

## XOUT 输出

`xout` 中的 `items:` 使用对齐的纯文本表格：第一行是表头，后续每行对应一个 item。
它不是 Markdown 表格，不使用 `|` 分隔。JSON 响应结构不受影响。

导出路径使用 `args.output.path`：

- 相对路径写到 `.xverif/xcov_exports/`。
- 包含 `..` 的路径会被拒绝。
- 绝对路径必须显式设置 `output.allow_absolute_path=true`。

## 日志

xcov 日志默认写入：

```text
~/.xverif/xcov/sessions/<session_id>/session.json
~/.xverif/xcov/sessions/<session_id>/logs/actions.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/lifecycle.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/transport.ndjson
```

日志事件包含 `ts/event_id/pid/layer/component/session_id/action/phase/ok/context`，
不会记录完整大型 `items` payload。

## 审阅材料

- API 能力审计：[docs/coverage-api-capability.md](docs/coverage-api-capability.md)
- 所有 action 的 `xout` 样例：[docs/action-xout-examples.md](docs/action-xout-examples.md)

## 当前限制

- `test="each"` 尚未实现；使用 `test="merged"` 或具体 test name。
- `source.annotate` 不解析 URG HTML，不输出未证实的 URG 专有源码标注。
