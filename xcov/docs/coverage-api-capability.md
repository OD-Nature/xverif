# xcov Coverage API 能力审计

本审计用于约束 xcov 公开接口：只有 Verdi/Python NPI 文档、headers 和真实 VDB
probe 证实可获取的字段才能进入 schema。未证实字段不做 fallback，不解析 URG
HTML，不返回占位 note。

## 本地依据

- Verdi 安装：`$VERDI_HOME=~/Synopsys/verdi/V-2023.12-SP2`
- Python Coverage 文档：`$VERDI_HOME/doc/Python_NPI_Coverage.pdf`
- 可检索文本：`$VERDI_HOME/doc/.Python_NPI_Coverage.txt.gz`
- Coverage C header：`$VERDI_HOME/share/NPI/inc/npi_cov.h`
- 真实 VDB probe：`~/uart_example/sim/merged.vdb`

真实 probe 已在沙箱外运行，原因是 pynpi/VDB/license 访问属于 NPI/EDA 动作。

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
