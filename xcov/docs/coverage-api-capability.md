# xcov Coverage API 能力审计

本审计用于约束 xcov 公开接口：只有 Verdi NPI文档、headers和真实 VDB
probe 证实可获取的字段才能进入 schema。未证实字段不做 fallback，不解析 URG
HTML，不返回占位 note。

xcov现有两个 provider：O-2018.09-SP2使用 C++ `npi_cov.h` native worker，
V-2023.12-SP2使用 Python `pynpi.cov`。二者必须映射为同一 canonical coverage
item/action合同；backend差异只允许出现在 worker/provider诊断字段。

## 2023 Python provider依据

- Verdi 安装：`$VERDI_HOME=~/Synopsys/verdi/V-2023.12-SP2`
- Python Coverage 文档：`$VERDI_HOME/doc/Python_NPI_Coverage.pdf`
- 可检索文本：`$VERDI_HOME/doc/.Python_NPI_Coverage.txt.gz`
- Coverage C header：`$VERDI_HOME/share/NPI/inc/npi_cov.h`
- 真实 VDB probe：`~/uart_example/sim/merged.vdb`

真实 probe 已在沙箱外运行，原因是 pynpi/VDB/license 访问属于 NPI/EDA 动作。

## 2018 native provider依据

- Verdi/VCS：O-2018.09-SP2。
- API header：`$VERDI_HOME/share/NPI/inc/npi_cov.h`。
- Provider：`xcov/native/xcov-npi-worker.cpp`，通过 JSONL常驻 worker封装。
- 真实验证：仓内2-test VDB、GPIO 14-test VDB和 xip VDB。
- 已验证能力：test枚举/合并、instance递归、line/toggle/branch/assert对象、
  scope summary、Verdi等权 Score、raw weighted coverage和正常 close/checkin。
- 已有 license证据：`Verdi`、`VCSTools_Net`；站点别名由部署环境确认。

2018 provider启动前必须确认 `vdb/snps/coverage/db` 存在且包含普通文件；空壳 VDB
直接返回 `INVALID_VDB`。正常关闭必须执行 `npi_cov_close()` 和 `npi_end()`。

## 已证实能力

### score-bearing object

`npi_cov.h` 和 Python Coverage 文档证实以下 object type 存在，并已被 xcov 用于
URG score 对齐：

- line：`npiCovStmtBin`
- toggle：`npiCovToggleBin`
- condition：`npiCovConditionBin`
- branch：`npiCovBranchBin`
- fsm：`npiCovTransBin`
- assert：`npiCovAssert`、`npiCovCoverProperty`、`npiCovCoverSequence`

真实 VDB probe 已验证这些对象可通过 Python Coverage handle 遍历，并可读取
`covered()`、`coverable()`、`count()`、`status()`、`file_name()`、`line_no()`。

### toggle transition evidence

文档和 header 证实：

- `npiCovSignal`
- `npiCovSignalBit`
- `npiCovToggleBin`
- `npiCovIsPort`
- `npiCovToggleType`

Python method 映射后可用：

- `is_port(test)`
- `toggle_type(test)`
- `covered(test)`
- `coverable(test)`
- `file_name()`
- `line_no(test)`

真实 VDB probe 证实 `npiCovToggleBin.toggle_type()` 返回 `npiCovToggle01` 或
`npiCovToggle10`，可聚合为 `0 -> 1` 和 `1 -> 0`。

公开接口：`export.code_coverage` 中的 toggle Markdown 行，只表达 signal/bit、
`0 -> 1` 是否覆盖、`1 -> 0` 是否覆盖和 file:line。交互式 `code_coverage.holes`
只输出 hierarchy 覆盖率概览，不展开 bit 明细。

不公开字段：`direction`。当前 Python Coverage API 文档、`npi_cov.h` 和真实 VDB
probe 只证实 `is_port()`，未证实 coverage handle 可直接提供 port direction。

### assert report

文档和 header 证实：

- `npiCovAssert`
- `npiCovCoverProperty`
- `npiCovCoverSequence`
- `npiCovAttemptBin`
- `npiCovSuccessBin`
- `npiCovFailureBin`
- `npiCovIncompleteBin`
- `npiCovFirstmatchBin`
- `npiCovSeverity`
- `npiCovCategory`

Python method 映射后可用：

- `severity(test)`
- `category(test)`
- `count(test)`
- `covered(test)`
- `coverable(test)`
- `file_name()`
- `line_no(test)`
- `child_handles()`

真实 VDB probe 证实 assertion 对象可以读取 `severity/category`，子 bin 可以读取
`Attempt/Success/Failure/Incomplete` count。

公开接口：`assert.report`。

### source annotate

Python Coverage API 证实 coverage object 可读取：

- `file_name()`
- `line_no(test)`

因此 xcov 可以基于 NPI evidence 定位源码文件并读取源码窗口，生成
`source.annotate`。这不是 URG HTML 解析；源码文本来自项目文件，coverage
annotation 来自 VDB/NPI。

### branch/condition term与表达式树

Verdi 2018官方对象关系为`branch/condition -> bin -> term`。真实GPIO单case VDB验证：

- typed iterator可从每个bin取得term的name/value，建立`*_term_values[]`；
- `-`表示NPI返回的don't-care值，必须原样保留；
- `npi_pst_create_expr_tree`可把coverage expression解析为opcode/operator/children AST；
- term映射来自coverage对象，AST仅用于表达式结构，二者不能相互替代。
- `source.annotate`默认去重expression和term名称；每个bin只返回紧凑value数组。
  AST需显式`include_ast:true`，并且每个expression只返回一份。

### exclusion边界

Verdi 2018 `npi_cov.h`提供exclusion状态查询及exclude file的load/save/unload，未提供
reason、comment、author或source rule属性。因此当前接口只能报告`excluded`、
`partially_excluded`、`excluded_at_compile_time`、`excluded_at_report_time`等状态，
不能直接报告详细排除原因。

不公开字段：`MISSING_ELSE` 等 URG HTML 专有显示标签。当前 Python Coverage API
文档和 probe 没有证实这些标签可取。

## 实现边界

- 不读取 `urgReport/asserts.html`、`mod*.html`、`session.xml`。
- 不把 HTML 内容作为 xcov 输出的数据源。
- 不在 schema 中放未证实字段。
- 不用 `note/unavailable_fields` 伪装接口兼容；字段做不到就不暴露。

## 后续重新评估条件

以下情况出现时，可以重新审计并扩展接口：

- Verdi/Python Coverage API 新版本明确暴露 port direction。
- NPI Language/Netlist API 能稳定把 coverage signal 绑定到 design port handle。
- Coverage API 明确暴露 URG 源码页中的专有 annotation label。

重新评估必须先更新本文件，再更新 schema、README、skill 文档和测试。
